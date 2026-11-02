from django.urls import path

from . import views

app_name = "web"

urlpatterns = [
    path("", views.home, name="home"),
    path("health/", views.health, name="health"),
    path("api/status/", views.api_status, name="api-status"),
    path("search/", views.search, name="search"),
    path("profile/", views.profile, name="profile"),
    path("feedback/", views.feedback, name="feedback"),
]
