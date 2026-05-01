from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import DetailView, ListView

from .constants import CHECK_TYPE_BRAND, CHECK_TYPE_INGREDIENT, CHECK_TYPE_OCR, CHECK_TYPE_PRODUCT, UNKNOWN
from .forms import BrandSearchForm, IngredientSearchForm, OCRUploadForm, ProductSearchForm
from .models import Brand, FavoriteItem, Ingredient, Product, ProductCheckRequest, SearchHistory
from .services import ExternalCatalogService, ProductAnalyzerService

analyzer_service = ProductAnalyzerService()
external_catalog_service = ExternalCatalogService()


class ProductListView(ListView):
    model = Product
    template_name = "catalog/product_list.html"
    context_object_name = "products"
    paginate_by = 20

    def get_queryset(self):
        queryset = Product.objects.select_related("brand").all()
        self.form = ProductSearchForm(self.request.GET or None)
        if self.form.is_valid():
            query = self.form.cleaned_data.get("query")
            status = self.form.cleaned_data.get("status")
            country = self.form.cleaned_data.get("country")
            brand = self.form.cleaned_data.get("brand")
            if query:
                queryset = queryset.search(query)
            if status:
                queryset = queryset.filter(halal_status=status)
            if country:
                queryset = queryset.filter(country__icontains=country)
            if brand:
                queryset = queryset.filter(brand__name__icontains=brand)
            if query and not queryset.exists():
                imported_product = external_catalog_service.search_and_cache_product(query)
                if imported_product:
                    queryset = Product.objects.filter(pk=imported_product.pk).select_related("brand")
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = self.form
        return context


class ProductDetailView(DetailView):
    model = Product
    slug_field = "slug"
    slug_url_kwarg = "slug"
    template_name = "catalog/product_detail.html"

    def get_queryset(self):
        return Product.objects.select_related("brand").prefetch_related("product_ingredients__ingredient")

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if request.user.is_authenticated:
            SearchHistory.objects.create(
                user=request.user,
                check_type=CHECK_TYPE_PRODUCT,
                query=self.object.name,
                result_status=self.object.halal_status,
                product=self.object,
            )
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["alternatives"] = analyzer_service.find_alternatives(self.object)
        return context


class IngredientListView(ListView):
    model = Ingredient
    template_name = "catalog/ingredient_list.html"
    context_object_name = "ingredients"
    paginate_by = 20

    def get_queryset(self):
        queryset = Ingredient.objects.all()
        self.form = IngredientSearchForm(self.request.GET or None)
        if self.form.is_valid():
            query = self.form.cleaned_data.get("query")
            status = self.form.cleaned_data.get("status")
            if query:
                queryset = queryset.search(query)
            if status:
                queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = self.form
        return context


class IngredientDetailView(DetailView):
    model = Ingredient
    slug_field = "slug"
    slug_url_kwarg = "slug"
    template_name = "catalog/ingredient_detail.html"

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if request.user.is_authenticated:
            SearchHistory.objects.create(
                user=request.user,
                check_type=CHECK_TYPE_INGREDIENT,
                query=self.object.name,
                result_status=self.object.status,
                ingredient=self.object,
            )
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)


class BrandListView(ListView):
    model = Brand
    template_name = "catalog/brand_list.html"
    context_object_name = "brands"
    paginate_by = 20

    def get_queryset(self):
        queryset = Brand.objects.annotate(product_total=Count("products"))
        self.form = BrandSearchForm(self.request.GET or None)
        if self.form.is_valid():
            query = self.form.cleaned_data.get("query")
            boycott_status = self.form.cleaned_data.get("boycott_status")
            if query:
                queryset = queryset.search(query)
            if boycott_status:
                queryset = queryset.filter(boycott_status=boycott_status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = self.form
        return context


class BoycottListView(ListView):
    model = Brand
    template_name = "catalog/boycott_list.html"
    context_object_name = "brands"
    paginate_by = 20

    def get_queryset(self):
        return Brand.objects.filter(boycott_status="active").annotate(product_total=Count("products"))


class BrandDetailView(DetailView):
    model = Brand
    slug_field = "slug"
    slug_url_kwarg = "slug"
    template_name = "catalog/brand_detail.html"

    def get_queryset(self):
        return Brand.objects.prefetch_related("products")

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if request.user.is_authenticated:
            SearchHistory.objects.create(
                user=request.user,
                check_type=CHECK_TYPE_BRAND,
                query=self.object.name,
                result_status=UNKNOWN,
                brand=self.object,
            )
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)


def ocr_upload_view(request):
    form = OCRUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        ocr_request = form.save(commit=False)
        if request.user.is_authenticated:
            ocr_request.created_by = request.user
        ocr_request.save()
        analyzer_service.analyze_ocr_request(ocr_request)
        if request.user.is_authenticated:
            SearchHistory.objects.create(
                user=request.user,
                check_type=CHECK_TYPE_OCR,
                query=ocr_request.title or f"OCR #{ocr_request.pk}",
                result_status=ocr_request.final_status,
                ocr_request=ocr_request,
            )
        messages.success(request, "OCR analysis completed.")
        return redirect(ocr_request.get_absolute_url())
    return render(request, "catalog/ocr_upload.html", {"form": form})


class OCRDetailView(DetailView):
    model = ProductCheckRequest
    pk_url_kwarg = "pk"
    template_name = "catalog/ocr_detail.html"

    def get_queryset(self):
        return ProductCheckRequest.objects.prefetch_related("ingredient_results__ingredient")


@login_required
def favorite_toggle_view(request, content_type, slug):
    model_map = {
        "product": Product,
        "ingredient": Ingredient,
        "brand": Brand,
    }
    model_class = model_map[content_type]
    target = get_object_or_404(model_class, slug=slug)
    lookup = {"user": request.user, content_type: target}
    favorite, created = FavoriteItem.objects.get_or_create(**lookup)
    if not created:
        favorite.delete()
        messages.info(request, "Removed from favorites.")
    else:
        messages.success(request, "Added to favorites.")
    return HttpResponseRedirect(request.META.get("HTTP_REFERER", reverse("accounts:favorites")))


def analyze_product_view(request, slug):
    product = get_object_or_404(Product, slug=slug)
    analyzer_service.analyze_product(product)
    messages.success(request, "Product composition was re-analyzed.")
    return redirect(product.get_absolute_url())
