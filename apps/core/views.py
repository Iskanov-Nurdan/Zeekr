from django.contrib import messages
from django.shortcuts import redirect, render

from apps.catalog.forms import OCRUploadForm, ProductSearchForm
from apps.catalog.models import Brand, Ingredient, Product
from apps.catalog.services import ProductAnalyzerService


analyzer_service = ProductAnalyzerService()


def home(request):
    query = request.GET.get("q", "").strip()
    ocr_form = OCRUploadForm()
    products = Product.objects.none()
    ingredients = Ingredient.objects.none()
    brands = Brand.objects.none()

    if request.method == "POST":
        ocr_form = OCRUploadForm(request.POST, request.FILES)
        if ocr_form.is_valid():
            ocr_request = ocr_form.save(commit=False)
            if request.user.is_authenticated:
                ocr_request.created_by = request.user
            ocr_request.save()
            analyzer_service.analyze_ocr_request(ocr_request)
            messages.success(request, "Проверка по фото завершена.")
            return redirect(ocr_request.get_absolute_url())

    if query:
        products = Product.objects.search(query)[:5]
        ingredients = Ingredient.objects.search(query)[:5]
        brands = Brand.objects.search(query)[:5]

    context = {
        "query": query,
        "product_count": Product.objects.count(),
        "ingredient_count": Ingredient.objects.count(),
        "brand_count": Brand.objects.count(),
        "products": products,
        "ingredients": ingredients,
        "brands": brands,
        "search_form": ProductSearchForm(initial={"query": query}),
        "ocr_form": ocr_form,
    }
    return render(request, "core/home.html", context)
