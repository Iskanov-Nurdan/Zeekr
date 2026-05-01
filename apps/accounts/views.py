from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.catalog.models import FavoriteItem, SearchHistory
from apps.moderation.models import DataIssueReport

from .forms import UserProfileForm


@login_required
def dashboard(request):
    profile = request.user.profile
    form = UserProfileForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("accounts:dashboard")

    context = {
        "form": form,
        "profile": profile,
        "history_entries": SearchHistory.objects.filter(user=request.user)[:20],
        "favorite_items": FavoriteItem.objects.filter(user=request.user)[:20],
        "reports": DataIssueReport.objects.filter(user=request.user)[:20],
    }
    return render(request, "accounts/dashboard.html", context)


@login_required
def favorites(request):
    items = FavoriteItem.objects.filter(user=request.user).select_related("product", "ingredient", "brand")
    return render(request, "accounts/favorites.html", {"items": items})


@login_required
def history(request):
    entries = SearchHistory.objects.filter(user=request.user).select_related(
        "product", "ingredient", "brand", "ocr_request"
    )
    return render(request, "accounts/history.html", {"entries": entries})

