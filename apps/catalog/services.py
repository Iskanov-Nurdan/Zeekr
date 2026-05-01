import re
from dataclasses import dataclass
from decimal import Decimal

import pytesseract
import requests
from django.conf import settings
from django.db import transaction
from openai import OpenAI
from openai import OpenAIError
from PIL import Image
from pytesseract import TesseractNotFoundError

from .constants import DOUBTFUL, HALAL, HARAM, UNKNOWN
from .models import Brand, ExternalProductCache, Ingredient, OCRIngredientResult, Product, ProductAlternative, ProductIngredient

SEPARATORS_RE = re.compile(r"[,;\n]+")
INGREDIENTS_HEADER_RE = re.compile(r"ingredients?\s*[:\-]\s*", re.IGNORECASE)


@dataclass
class IngredientDecision:
    raw_name: str
    normalized_name: str
    ingredient: Ingredient | None
    status: str
    reason: str
    confidence_score: Decimal


class IngredientAnalyzer:
    HEURISTIC_RULES = {
        "gelatin": (HARAM, "Gelatin is treated as haram unless halal origin is confirmed.", Decimal("98.00")),
        "e120": (HARAM, "E120 (carmine) is commonly derived from insects.", Decimal("99.00")),
        "carmine": (HARAM, "Carmine is commonly derived from insects.", Decimal("99.00")),
        "alcohol": (HARAM, "Alcohol is prohibited.", Decimal("99.00")),
        "natural flavors": (DOUBTFUL, "Natural flavors may hide animal or alcohol-based carriers.", Decimal("82.00")),
        "enzymes": (DOUBTFUL, "Enzyme origin is often unclear without manufacturer data.", Decimal("80.00")),
        "e471": (DOUBTFUL, "E471 can be plant-based or animal-based depending on source.", Decimal("85.00")),
        "lecithin": (DOUBTFUL, "Lecithin can be soy, sunflower, or animal-derived.", Decimal("72.00")),
        "pork": (HARAM, "Pork is prohibited.", Decimal("99.00")),
        "lard": (HARAM, "Lard is prohibited.", Decimal("99.00")),
    }

    def normalize_name(self, value):
        cleaned = value.strip().lower()
        return re.sub(r"\s+", " ", cleaned)

    def split_ingredients(self, text):
        without_header = INGREDIENTS_HEADER_RE.sub("", text or "").strip()
        chunks = [part.strip(" .") for part in SEPARATORS_RE.split(without_header)]
        return [chunk for chunk in chunks if chunk]

    def find_reference(self, normalized_name):
        return (
            Ingredient.objects.filter(name__iexact=normalized_name).first()
            or Ingredient.objects.filter(aliases__icontains=normalized_name).first()
        )

    def analyze_name(self, raw_name):
        normalized_name = self.normalize_name(raw_name)
        ingredient = self.find_reference(normalized_name)
        if ingredient:
            return IngredientDecision(
                raw_name=raw_name,
                normalized_name=normalized_name,
                ingredient=ingredient,
                status=ingredient.status,
                reason=ingredient.reason or ingredient.description or "Taken from the internal ingredient reference.",
                confidence_score=ingredient.confidence_score,
            )

        for key, rule in self.HEURISTIC_RULES.items():
            if key in normalized_name:
                status, reason, confidence_score = rule
                return IngredientDecision(raw_name, normalized_name, None, status, reason, confidence_score)

        return IngredientDecision(
            raw_name,
            normalized_name,
            None,
            UNKNOWN,
            "There is not enough data to classify this ingredient confidently.",
            Decimal("35.00"),
        )

    def summarize(self, decisions):
        if not decisions:
            return UNKNOWN, "No ingredients were found in the provided data.", Decimal("0.00")

        statuses = [item.status for item in decisions]
        if HARAM in statuses:
            status = HARAM
        elif DOUBTFUL in statuses or UNKNOWN in statuses:
            status = DOUBTFUL
        else:
            status = HALAL

        confidence = max((item.confidence_score for item in decisions), default=Decimal("0.00"))
        reasons = [f"{item.raw_name}: {item.reason}" for item in decisions[:5]]
        return status, " ".join(reasons), confidence


class OCRService:
    def extract_text(self, image_field):
        tesseract_cmd = getattr(settings, "TESSERACT_CMD", "")
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        try:
            image = Image.open(image_field)
            return pytesseract.image_to_string(image)
        except TesseractNotFoundError:
            return ""


class AIExplanationService:
    def build_local_summary(self, decisions, final_status):
        if not decisions:
            return "No ingredients were recognized."
        lines = [f"Final status: {final_status.title()}."]
        lines.extend(f"{item.raw_name}: {item.status.title()} because {item.reason}" for item in decisions[:6])
        return " ".join(lines)

    def build_openai_summary(self, decisions, final_status):
        api_key = getattr(settings, "OPENAI_API_KEY", "")
        if not api_key:
            return self.build_local_summary(decisions, final_status)

        compact = [
            {
                "name": item.raw_name,
                "status": item.status,
                "reason": item.reason,
                "confidence": str(item.confidence_score),
            }
            for item in decisions[:10]
        ]
        client = OpenAI(api_key=api_key)
        try:
            response = client.responses.create(
                model=getattr(settings, "OPENAI_MODEL", "gpt-4.1-mini"),
                input=(
                    "You are a halal product analyst. "
                    f"Final product status: {final_status}. "
                    f"Ingredient decisions: {compact}. "
                    "Return a short explanation with risks and next actions."
                ),
            )
            return response.output_text
        except OpenAIError:
            return self.build_local_summary(decisions, final_status)


class ProductAnalyzerService:
    def __init__(self):
        self.ingredient_analyzer = IngredientAnalyzer()
        self.ocr_service = OCRService()
        self.ai_service = AIExplanationService()

    def analyze_product(self, product):
        decisions = self.analyze_text(product.full_ingredients_text)
        status, reason, confidence = self.ingredient_analyzer.summarize(decisions)
        product.halal_status = status
        product.status_reason = reason
        product.confidence_score = confidence
        product.save(update_fields=["halal_status", "status_reason", "confidence_score", "updated_at"])
        self._sync_product_ingredients(product, decisions)
        return product, decisions

    def analyze_text(self, text):
        names = self.ingredient_analyzer.split_ingredients(text)
        return [self.ingredient_analyzer.analyze_name(name) for name in names]

    @transaction.atomic
    def analyze_ocr_request(self, request_obj):
        raw_text = self.ocr_service.extract_text(request_obj.image)
        decisions = self.analyze_text(raw_text)
        final_status, final_reason, confidence = self.ingredient_analyzer.summarize(decisions)
        request_obj.raw_ocr_text = raw_text
        request_obj.cleaned_ingredients_text = ", ".join(item.normalized_name for item in decisions)
        request_obj.final_status = final_status
        request_obj.final_reason = final_reason
        request_obj.confidence_score = confidence
        request_obj.ai_summary = self.ai_service.build_openai_summary(decisions, final_status)
        request_obj.save()

        request_obj.ingredient_results.all().delete()
        for item in decisions:
            OCRIngredientResult.objects.create(
                request=request_obj,
                ingredient=item.ingredient,
                raw_name=item.raw_name,
                normalized_name=item.normalized_name,
                status=item.status,
                reason=item.reason,
                confidence_score=item.confidence_score,
            )
        return request_obj, decisions

    def find_alternatives(self, product, limit=4):
        explicit = ProductAlternative.objects.filter(source_product=product).select_related("alternative_product")[:limit]
        alternatives = [row.alternative_product for row in explicit]
        if len(alternatives) >= limit:
            return alternatives
        fallback = (
            Product.objects.filter(category=product.category, halal_status=HALAL)
            .exclude(pk=product.pk)
            .select_related("brand")[: limit - len(alternatives)]
        )
        return alternatives + list(fallback)

    def _sync_product_ingredients(self, product, decisions):
        product.product_ingredients.all().delete()
        for index, item in enumerate(decisions, start=1):
            ingredient = item.ingredient
            if ingredient is None:
                ingredient, _ = Ingredient.objects.get_or_create(
                    name=item.normalized_name.title(),
                    defaults={
                        "status": item.status,
                        "reason": item.reason,
                        "confidence_score": item.confidence_score,
                    },
                )
            ProductIngredient.objects.create(
                product=product,
                ingredient=ingredient,
                raw_name=item.raw_name,
                position=index,
                status_at_analysis=item.status,
                notes=item.reason,
            )


class ExternalCatalogService:
    search_url = "https://world.openfoodfacts.org/cgi/search.pl"

    def __init__(self):
        self.analyzer = ProductAnalyzerService()

    def search_and_cache_product(self, query):
        if not query:
            return None

        existing_cache = ExternalProductCache.objects.filter(query__iexact=query).select_related("product").first()
        if existing_cache and existing_cache.product:
            return existing_cache.product

        try:
            response = requests.get(
                self.search_url,
                params={
                    "search_terms": query,
                    "search_simple": 1,
                    "action": "process",
                    "json": 1,
                    "page_size": 1,
                },
                timeout=10,
            )
            response.raise_for_status()
        except requests.RequestException:
            return None

        payload = response.json()
        products = payload.get("products") or []
        if not products:
            return None

        raw_product = products[0]
        external_id = str(raw_product.get("id") or raw_product.get("_id") or query)
        cached = ExternalProductCache.objects.filter(external_id=external_id).select_related("product").first()
        if cached and cached.product:
            return cached.product

        brand_name = (raw_product.get("brands") or "").split(",")[0].strip()
        brand = None
        if brand_name:
            brand, _ = Brand.objects.get_or_create(name=brand_name)

        product, _ = Product.objects.get_or_create(
            name=raw_product.get("product_name") or query,
            brand=brand,
            defaults={
                "barcode": raw_product.get("code", ""),
                "country": raw_product.get("countries", ""),
                "full_ingredients_text": raw_product.get("ingredients_text", ""),
                "source_name": "OpenFoodFacts",
                "source_url": raw_product.get("url", ""),
            },
        )
        if raw_product.get("ingredients_text") and not product.full_ingredients_text:
            product.full_ingredients_text = raw_product.get("ingredients_text", "")
            product.source_name = "OpenFoodFacts"
            product.source_url = raw_product.get("url", "")
            product.save(update_fields=["full_ingredients_text", "source_name", "source_url", "updated_at"])

        ExternalProductCache.objects.update_or_create(
            external_id=external_id,
            defaults={
                "query": query,
                "provider": "OpenFoodFacts",
                "payload": raw_product,
                "normalized_name": product.name,
                "product": product,
            },
        )
        if product.full_ingredients_text:
            self.analyzer.analyze_product(product)
        return product
