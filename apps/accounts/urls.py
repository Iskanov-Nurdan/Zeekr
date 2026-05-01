from django.urls import path

from .views import dashboard, favorites, history

app_name = "accounts"

urlpatterns = [
    path("dashboard/", dashboard, name="dashboard"),
    path("favorites/", favorites, name="favorites"),
    path("history/", history, name="history"),
]

