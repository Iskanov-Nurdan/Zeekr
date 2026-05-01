from django.urls import path

from .views import report_issue

app_name = "moderation"

urlpatterns = [
    path("report/", report_issue, name="report_issue"),
]

