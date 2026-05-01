from django import forms

from .models import DataIssueReport


class DataIssueReportForm(forms.ModelForm):
    class Meta:
        model = DataIssueReport
        fields = ["subject", "description", "photo"]

