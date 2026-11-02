"""Views for the lab application.

Public: /, /health/, /api/status/, /search/
Protected: /profile/, /feedback/ (Django authentication)
"""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render

from .models import Feedback

# Static corpus so /search/ exercises user input without a database dependency.
SEARCH_CORPUS = [
    "5G standalone core and the N2/N3/N4 interfaces",
    "N6 data network and the un-NATed user plane",
    "TLS termination at the Nginx gateway",
    "Django authentication, CSRF and secure cookies",
    "DevSecOps security gates in Scenario B",
]


def home(request):
    return render(request, "web/home.html")


def health(request):
    """Deployment health probe (phase 1B contract: exact JSON body)."""
    return JsonResponse(
        {
            "service": "project2-django",
            "status": "ok",
            "project": "Telecommunication Security",
        }
    )


def api_status(request):
    """Small status API; also exposes whether the caller is authenticated."""
    return JsonResponse(
        {
            "status": "ok",
            "service": "project2-django",
            "project": "Telecommunication Security",
            "authenticated": request.user.is_authenticated,
        }
    )


def search(request):
    """Public search over a static corpus; echoes the query through templates."""
    query = request.GET.get("q", "").strip()
    if query:
        needle = query.casefold()
        results = [item for item in SEARCH_CORPUS if needle in item.casefold()]
    else:
        results = []
    return render(
        request, "web/search.html", {"query": query, "results": results, "total": len(results)}
    )


@login_required
def profile(request):
    return render(request, "web/profile.html")


@login_required
def feedback(request):
    if request.method == "POST":
        message = request.POST.get("message", "").strip()
        if not message:
            return HttpResponse("message is required", status=400, content_type="text/plain")
        Feedback.objects.create(user=request.user, message=message)
        return render(request, "web/feedback.html", {"submitted": True})
    return render(request, "web/feedback.html")
