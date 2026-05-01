from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import DataIssueReportForm


@login_required
def report_issue(request):
    form = DataIssueReportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        report = form.save(commit=False)
        report.user = request.user
        report.save()
        return redirect("accounts:dashboard")
    return render(request, "moderation/report_issue.html", {"form": form})

