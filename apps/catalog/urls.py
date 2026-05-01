from django.urls import path

from .views import (
    BrandDetailView,
    BrandListView,
    BoycottListView,
    IngredientDetailView,
    IngredientListView,
    OCRDetailView,
    ProductDetailView,
    ProductListView,
    analyze_product_view,
    favorite_toggle_view,
    ocr_upload_view,
)

app_name = "catalog"

urlpatterns = [
    path("products/", ProductListView.as_view(), name="product_list"),
    path("products/<slug:slug>/", ProductDetailView.as_view(), name="product_detail"),
    path("products/<slug:slug>/analyze/", analyze_product_view, name="product_analyze"),
    path("ingredients/", IngredientListView.as_view(), name="ingredient_list"),
    path("ingredients/<slug:slug>/", IngredientDetailView.as_view(), name="ingredient_detail"),
    path("brands/", BrandListView.as_view(), name="brand_list"),
    path("brands/<slug:slug>/", BrandDetailView.as_view(), name="brand_detail"),
    path("boycott/", BoycottListView.as_view(), name="boycott_list"),
    path("ocr/", ocr_upload_view, name="ocr_upload"),
    path("ocr/<int:pk>/", OCRDetailView.as_view(), name="ocr_detail"),
    path("favorites/<str:content_type>/<slug:slug>/toggle/", favorite_toggle_view, name="favorite_toggle"),
]
