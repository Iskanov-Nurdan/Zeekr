import re
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO

import pytesseract
import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from openai import OpenAI
from openai import OpenAIError
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from pytesseract import TesseractNotFoundError

from .constants import CHECK_TYPE_OCR, CHECK_TYPE_PRODUCT, DOUBTFUL, HALAL, HARAM, UNKNOWN
from .models import (
    Brand,
    ExternalProductCache,
    FavoriteItem,
    Ingredient,
    OCRIngredientResult,
    Product,
    ProductAlternative,
    ProductIngredient,
    SearchHistory,
)

SEPARATORS_RE = re.compile(r"[,;\n]+")
INGREDIENTS_HEADER_RE = re.compile(r"ingredients?\s*[:\-]\s*", re.IGNORECASE)
OCR_NOISE_RE = re.compile(r"[^a-zA-Z0-9,\-;:()%/\n ]+")
OCR_COMMON_FIXES = {
    "e 120": "e120",
    "e-120": "e120",
    "e 471": "e471",
    "e-471": "e471",
    "carrnine": "carmine",
    "gelatine": "gelatin",
    "flavourings": "flavors",
}
FAVORITE_LIMIT = 100
HISTORY_LIMIT = 200


@dataclass
class IngredientDecision:
    raw_name: str
    normalized_name: str
    ingredient: Ingredient | None
    status: str
    reason: str
    confidence_score: Decimal
    matched_by: str = "unknown"


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
        cleaned = OCR_NOISE_RE.sub(" ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,-")
        for source, target in OCR_COMMON_FIXES.items():
            cleaned = cleaned.replace(source, target)
        return cleaned

    def split_ingredients(self, text):
        without_header = INGREDIENTS_HEADER_RE.sub("", text or "").strip()
        chunks = [part.strip(" .") for part in SEPARATORS_RE.split(without_header)]
        cleaned = []
        seen = set()
        for chunk in chunks:
            normalized = self.normalize_name(chunk)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            cleaned.append(chunk)
        return cleaned

    def find_reference(self, normalized_name):
        exact = Ingredient.objects.filter(name__iexact=normalized_name).first()
        if exact:
            return exact, "exact_name"

        alias = Ingredient.objects.filter(aliases__icontains=normalized_name).first()
        if alias:
            return alias, "alias"

        partial = Ingredient.objects.filter(
            Q(name__icontains=normalized_name) | Q(aliases__icontains=normalized_name)
        ).first()
        if partial:
            return partial, "partial"

        return None, "none"

    def analyze_name(self, raw_name):
        normalized_name = self.normalize_name(raw_name)
        ingredient, matched_by = self.find_reference(normalized_name)
        if ingredient:
            confidence = ingredient.confidence_score
            if matched_by == "partial":
                confidence = min(confidence, Decimal("78.00"))
            return IngredientDecision(
                raw_name=raw_name,
                normalized_name=normalized_name,
                ingredient=ingredient,
                status=ingredient.status,
                reason=ingredient.reason or ingredient.description or "Taken from the internal ingredient reference.",
                confidence_score=confidence,
                matched_by=matched_by,
            )

        for key, rule in self.HEURISTIC_RULES.items():
            if key in normalized_name:
                status, reason, confidence_score = rule
                return IngredientDecision(raw_name, normalized_name, None, status, reason, confidence_score, "heuristic")

        return IngredientDecision(
            raw_name,
            normalized_name,
            None,
            UNKNOWN,
            "There is not enough data to classify this ingredient confidently.",
            Decimal("35.00"),
            "unknown",
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

        haram_count = sum(1 for item in decisions if item.status == HARAM)
        doubtful_count = sum(1 for item in decisions if item.status == DOUBTFUL)
        unknown_count = sum(1 for item in decisions if item.status == UNKNOWN)
        average_confidence = sum((item.confidence_score for item in decisions), Decimal("0.00")) / max(len(decisions), 1)

        if status == HARAM:
            confidence = min(Decimal("99.00"), average_confidence + Decimal("10.00") + haram_count)
        elif status == DOUBTFUL:
            confidence = max(Decimal("62.00"), average_confidence - Decimal("6.00") + doubtful_count)
        else:
            confidence = max(Decimal("78.00"), average_confidence - Decimal("2.00"))
        confidence = max(Decimal("35.00"), min(Decimal("99.00"), confidence - unknown_count))

        reasons = [f"{item.raw_name}: {item.reason}" for item in decisions[:6]]
        summary = (
            f"Detected {len(decisions)} ingredients. "
            f"Haram: {haram_count}, doubtful: {doubtful_count}, unknown: {unknown_count}. "
            + " ".join(reasons)
        )
        return status, summary, confidence

    def analyze_many(self, raw_names):
        return [self.analyze_name(name) for name in raw_names]


class OCRService:
    def _prepare_variants(self, image_field):
        image_field.open("rb")
        raw_bytes = image_field.read()
        image_field.seek(0)
        base_image = Image.open(BytesIO(raw_bytes)).convert("RGB")
        grayscale = ImageOps.grayscale(base_image)
        contrasted = ImageEnhance.Contrast(grayscale).enhance(2.0)
        sharpened = contrasted.filter(ImageFilter.SHARPEN)
        thresholded = sharpened.point(lambda x: 255 if x > 160 else 0)
        enlarged = sharpened.resize((sharpened.width * 2, sharpened.height * 2))
        return [base_image, grayscale, sharpened, thresholded, enlarged]

    def _score_text(self, text):
        if not text:
            return 0
        cleaned = OCR_NOISE_RE.sub(" ", text)
        words = [part for part in re.split(r"[\s,;]+", cleaned) if len(part) > 1]
        return len(words)

    def extract_text(self, image_field):
        tesseract_cmd = getattr(settings, "TESSERACT_CMD", "")
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        try:
            best_text = ""
            best_score = -1
            for image in self._prepare_variants(image_field):
                for config in ("--psm 6", "--psm 11", "--psm 4"):
                    text = pytesseract.image_to_string(image, config=config)
                    score = self._score_text(text)
                    if score > best_score:
                        best_score = score
                        best_text = text
            return self.clean_text(best_text)
        except TesseractNotFoundError:
            return ""

    def clean_text(self, text):
        cleaned = (text or "").replace("\r", "\n")
        for source, target in OCR_COMMON_FIXES.items():
            cleaned = re.sub(re.escape(source), target, cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\n{2,}", "\n", cleaned)
        return cleaned.strip()


class AIExplanationService:
    def build_local_summary(self, decisions, final_status):
        if not decisions:
            return "No ingredients were recognized."
        lines = [f"Final status: {final_status.title()}."]
        haram = [item.raw_name for item in decisions if item.status == HARAM]
        doubtful = [item.raw_name for item in decisions if item.status == DOUBTFUL]
        unknown = [item.raw_name for item in decisions if item.status == UNKNOWN]
        if haram:
            lines.append(f"Critical ingredients: {', '.join(haram[:4])}.")
        if doubtful:
            lines.append(f"Need clarification: {', '.join(doubtful[:4])}.")
        if unknown:
            lines.append(f"Missing enough data for: {', '.join(unknown[:4])}.")
        lines.extend(f"{item.raw_name}: {item.status.title()} because {item.reason}" for item in decisions[:4])
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
                    "Return a compact explanation with 3 parts: verdict, risky ingredients, next action. "
                    "Be precise and avoid generic filler."
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
    freshness_hours = 24

    def __init__(self):
        self.analyzer = ProductAnalyzerService()

    def is_fresh(self, cache_row):
        if not cache_row:
            return False
        age = timezone.now() - cache_row.last_synced_at
        return age.total_seconds() < self.freshness_hours * 3600

    def search_and_cache_product(self, query):
        if not query:
            return None

        existing_cache = ExternalProductCache.objects.filter(query__iexact=query).select_related("product").first()
        if existing_cache and existing_cache.product and self.is_fresh(existing_cache):
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
        if cached and cached.product and self.is_fresh(cached):
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
        updated_fields = []
        if raw_product.get("ingredients_text"):
            product.full_ingredients_text = raw_product.get("ingredients_text", "")
            updated_fields.append("full_ingredients_text")
        if raw_product.get("code"):
            product.barcode = raw_product.get("code", "")
            updated_fields.append("barcode")
        if raw_product.get("countries"):
            product.country = raw_product.get("countries", "")
            updated_fields.append("country")
        product.source_name = "OpenFoodFacts"
        product.source_url = raw_product.get("url", "")
        product.updated_from_source_at = timezone.now()
        updated_fields.extend(["source_name", "source_url", "updated_from_source_at", "updated_at"])
        if updated_fields:
            product.save(update_fields=list(dict.fromkeys(updated_fields)))

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


class UserActivityService:
    def record_history(self, *, user, check_type, query, result_status, product=None, ingredient=None, brand=None, ocr_request=None):
        recent_duplicate = SearchHistory.objects.filter(
            user=user,
            check_type=check_type,
            query__iexact=query,
            product=product,
            ingredient=ingredient,
            brand=brand,
            ocr_request=ocr_request,
            created_at__gte=timezone.now() - timezone.timedelta(minutes=10),
        ).first()
        if recent_duplicate:
            recent_duplicate.result_status = result_status
            recent_duplicate.save(update_fields=["result_status", "updated_at"])
            return recent_duplicate

        record = SearchHistory.objects.create(
            user=user,
            check_type=check_type,
            query=query,
            result_status=result_status,
            product=product,
            ingredient=ingredient,
            brand=brand,
            ocr_request=ocr_request,
        )
        stale_ids = list(
            SearchHistory.objects.filter(user=user).order_by("-created_at").values_list("id", flat=True)[HISTORY_LIMIT:]
        )
        if stale_ids:
            SearchHistory.objects.filter(id__in=stale_ids).delete()
        return record

    def toggle_favorite(self, *, user, content_type, target):
        lookup = {"user": user, content_type: target}
        favorite = FavoriteItem.objects.filter(**lookup).first()
        if favorite:
            favorite.delete()
            return False, None

        if FavoriteItem.objects.filter(user=user).count() >= FAVORITE_LIMIT:
            raise ValueError(f"Favorite limit reached ({FAVORITE_LIMIT}).")

        favorite = FavoriteItem.objects.create(**lookup)
        return True, favorite
