from django.contrib import admin

from .models import (
    Brand,
    ExternalProductCache,
    FavoriteItem,
    Ingredient,
    OCRIngredientResult,
    Product,
    ProductAlternative,
    ProductCheckRequest,
    ProductIngredient,
    SearchHistory,
)


class ProductIngredientInline(admin.TabularInline):
    model = ProductIngredient
    extra = 0


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "origin", "confidence_score", "source_name")
    list_filter = ("status", "origin", "source_type")
    search_fields = ("name", "aliases", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "country", "boycott_status", "source_name")
    list_filter = ("boycott_status", "country")
    search_fields = ("name", "country", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "brand", "category", "halal_status", "confidence_score", "updated_from_source_at")
    list_filter = ("category", "halal_status", "country")
    search_fields = ("name", "barcode", "brand__name", "full_ingredients_text")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductIngredientInline]


@admin.register(ProductCheckRequest)
class ProductCheckRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "country", "final_status", "confidence_score", "created_by", "created_at")
    list_filter = ("final_status", "country")
    search_fields = ("title", "raw_ocr_text", "cleaned_ingredients_text")


admin.site.register(ProductIngredient)
admin.site.register(ProductAlternative)
admin.site.register(ExternalProductCache)
admin.site.register(OCRIngredientResult)
admin.site.register(SearchHistory)
admin.site.register(FavoriteItem)

