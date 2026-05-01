from django.db import models
from django.db.models import Q


class SearchQuerySet(models.QuerySet):
    search_fields = ()

    def search(self, query):
        if not query:
            return self.none()

        lookup = Q()
        for field_name in self.search_fields:
            lookup |= Q(**{f"{field_name}__icontains": query})
        return self.filter(lookup).distinct()


class ProductQuerySet(SearchQuerySet):
    search_fields = ("name", "brand__name", "description", "full_ingredients_text", "barcode")


class IngredientQuerySet(SearchQuerySet):
    search_fields = ("name", "aliases", "description", "typical_usage")


class BrandQuerySet(SearchQuerySet):
    search_fields = ("name", "description", "country", "categories")

