"""Minimal application views: the landing page and the health check."""

from django.http import HttpResponse, JsonResponse


def home(request):
    return HttpResponse(
        "Project 2 — Scenario A application is running.\n", content_type="text/plain"
    )


def health(request):
    """Deployment health probe (phase 1B contract: exact JSON body)."""
    return JsonResponse(
        {
            "service": "project2-django",
            "status": "ok",
            "project": "Telecommunication Security",
        }
    )
