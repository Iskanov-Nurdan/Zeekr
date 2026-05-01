from django import forms

from .models import ProductCheckRequest


class ProductSearchForm(forms.Form):
    query = forms.CharField(
        max_length=255,
        required=False,
        label="Поиск товара",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Например: Kinder Bueno, Coca Cola Vanilla",
            }
        ),
    )
    status = forms.ChoiceField(
        required=False,
        label="Статус",
        choices=[("", "Any status"), ("halal", "Halal"), ("haram", "Haram"), ("doubtful", "Doubtful")],
        widget=forms.Select(),
    )
    country = forms.CharField(
        max_length=120,
        required=False,
        label="Страна",
        widget=forms.TextInput(attrs={"placeholder": "Например: Kyrgyzstan"}),
    )
    brand = forms.CharField(
        max_length=255,
        required=False,
        label="Бренд",
        widget=forms.TextInput(attrs={"placeholder": "Например: Nestle"}),
    )


class IngredientSearchForm(forms.Form):
    query = forms.CharField(
        max_length=255,
        required=False,
        label="Поиск ингредиента",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Например: Gelatin, E120, E471",
            }
        ),
    )
    status = forms.ChoiceField(
        required=False,
        label="Статус",
        choices=[("", "Any status"), ("halal", "Halal"), ("haram", "Haram"), ("doubtful", "Doubtful")],
        widget=forms.Select(),
    )


class BrandSearchForm(forms.Form):
    query = forms.CharField(
        max_length=255,
        required=False,
        label="Поиск бренда",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Nestle, Coca Cola, Pepsi, McDonald's",
            }
        ),
    )
    boycott_status = forms.ChoiceField(
        required=False,
        label="Boycott статус",
        choices=[("", "Any boycott status"), ("active", "Active"), ("review", "Under review"), ("none", "None")],
        widget=forms.Select(),
    )


class OCRUploadForm(forms.ModelForm):
    class Meta:
        model = ProductCheckRequest
        fields = ["title", "country", "image"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Например: Doritos Hot Chili"}),
            "country": forms.TextInput(attrs={"placeholder": "Например: Kyrgyzstan"}),
            "image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }
        labels = {
            "title": "Название товара",
            "country": "Страна",
            "image": "Фото состава",
        }
