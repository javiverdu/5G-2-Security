"""Scenario A web application: public pages, authentication, profile, feedback."""

from django.apps import AppConfig


class WebConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "web"
