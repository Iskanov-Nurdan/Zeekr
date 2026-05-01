from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from .constants import (
    BOYCOTT_CHOICES,
    BOYCOTT_NONE,
    CHECK_TYPE_CHOICES,
    ORIGIN_CHOICES,
    ORIGIN_UNKNOWN,
    PRODUCT_CATEGORY_CHOICES,
    SOURCE_CHOICES,
    SOURCE_EXTERNAL,
    STATUS_CHOICES,
    UNKNOWN,
)
from .managers import BrandQuerySet, IngredientQuerySet, ProductQuerySet


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Ingredient(TimeStampedModel):
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    aliases = models.TextField(blank=True)
    category = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=UNKNOWN)
    description = models.TextField(blank=True)
    origin = models.CharField(max_length=20, choices=ORIGIN_CHOICES, default=ORIGIN_UNKNOWN)
    reason = models.TextField(blank=True)
    possible_risks = models.TextField(blank=True)
    typical_usage = models.TextField(blank=True)
    confidence_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_EXTERNAL)
    source_name = models.CharField(max_length=255, blank=True)

    objects = IngredientQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("catalog:ingredient_detail", args=[self.slug])


class Brand(TimeStampedModel):
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    logo = models.ImageField(upload_to="brands/logos/", blank=True, null=True)
    country = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    website = models.URLField(blank=True)
    boycott_status = models.CharField(max_length=20, choices=BOYCOTT_CHOICES, default=BOYCOTT_NONE)
    boycott_reason = models.TextField(blank=True)
    categories = models.CharField(max_length=255, blank=True)
    source_name = models.CharField(max_length=255, blank=True)

    objects = BrandQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("catalog:brand_detail", args=[self.slug])


class Product(TimeStampedModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, related_name="products", null=True, blank=True)
    category = models.CharField(max_length=50, choices=PRODUCT_CATEGORY_CHOICES, default="other")
    image = models.ImageField(upload_to="products/images/", blank=True, null=True)
    barcode = models.CharField(max_length=64, blank=True, db_index=True)
    country = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    full_ingredients_text = models.TextField(blank=True)
    halal_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=UNKNOWN)
    status_reason = models.TextField(blank=True)
    confidence_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    updated_from_source_at = models.DateTimeField(null=True, blank=True)
    source_name = models.CharField(max_length=255, blank=True)
    source_url = models.URLField(blank=True)
    ingredients = models.ManyToManyField(Ingredient, through="ProductIngredient", related_name="products")

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["name", "brand"], name="unique_product_per_brand"),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or "product"
            slug = base_slug
            counter = 1
            while Product.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                counter += 1
                slug = f"{base_slug}-{counter}"
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("catalog:product_detail", args=[self.slug])


class ProductIngredient(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="product_ingredients")
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, related_name="ingredient_products")
    raw_name = models.CharField(max_length=255, blank=True)
    position = models.PositiveIntegerField(default=0)
    status_at_analysis = models.CharField(max_length=20, choices=STATUS_CHOICES, default=UNKNOWN)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["position", "id"]
        unique_together = ("product", "ingredient", "position")

    def __str__(self):
        return f"{self.product} -> {self.ingredient}"


class ProductAlternative(TimeStampedModel):
    source_product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="alternatives")
    alternative_product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="alternative_for")
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ("source_product", "alternative_product")


class ExternalProductCache(TimeStampedModel):
    external_id = models.CharField(max_length=255, unique=True)
    query = models.CharField(max_length=255, db_index=True)
    provider = models.CharField(max_length=120)
    payload = models.JSONField(default=dict, blank=True)
    normalized_name = models.CharField(max_length=255, blank=True)
    last_synced_at = models.DateTimeField(auto_now=True)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name="external_caches")

    class Meta:
        ordering = ["-last_synced_at"]


class ProductCheckRequest(TimeStampedModel):
    title = models.CharField(max_length=255, blank=True)
    country = models.CharField(max_length=120, blank=True)
    image = models.ImageField(upload_to="ocr/uploads/")
    raw_ocr_text = models.TextField(blank=True)
    cleaned_ingredients_text = models.TextField(blank=True)
    final_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=UNKNOWN)
    final_reason = models.TextField(blank=True)
    confidence_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    ai_summary = models.TextField(blank=True)
    source_name = models.CharField(max_length=255, default="user_upload")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ocr_requests",
    )
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name="ocr_requests")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title or f"OCR request {self.pk}"

    def get_absolute_url(self):
        return reverse("catalog:ocr_detail", args=[self.pk])


class OCRIngredientResult(TimeStampedModel):
    request = models.ForeignKey(ProductCheckRequest, on_delete=models.CASCADE, related_name="ingredient_results")
    ingredient = models.ForeignKey(Ingredient, on_delete=models.SET_NULL, null=True, blank=True, related_name="ocr_hits")
    raw_name = models.CharField(max_length=255)
    normalized_name = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=UNKNOWN)
    reason = models.TextField(blank=True)
    confidence_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )

    class Meta:
        ordering = ["id"]


class SearchHistory(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="search_history")
    check_type = models.CharField(max_length=20, choices=CHECK_TYPE_CHOICES)
    query = models.CharField(max_length=255)
    result_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=UNKNOWN)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name="history_entries")
    ingredient = models.ForeignKey(Ingredient, on_delete=models.SET_NULL, null=True, blank=True, related_name="history_entries")
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True, related_name="history_entries")
    ocr_request = models.ForeignKey(
        ProductCheckRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="history_entries",
    )

    class Meta:
        ordering = ["-created_at"]


class FavoriteItem(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorite_items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True, related_name="favorites")
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, null=True, blank=True, related_name="favorites")
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE, null=True, blank=True, related_name="favorites")

    class Meta:
        ordering = ["-created_at"]

    @property
    def target(self):
        return self.product or self.ingredient or self.brand

