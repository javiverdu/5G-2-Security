"""Create the controlled laboratory account after migrations.

Idempotent: an existing account keeps its password, which is set only on
creation. The credentials come from the environment, never from the image.
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create the lab account (LAB_ADMIN_USER / LAB_ADMIN_PASSWORD) if missing."

    def handle(self, *args, **options):
        username = os.environ.get("LAB_ADMIN_USER", "securityadmin")
        password = os.environ.get("LAB_ADMIN_PASSWORD", "")
        email = os.environ.get("LAB_ADMIN_EMAIL", "securityadmin@telecom-lab.local")

        if not password:
            self.stderr.write(
                "LAB_ADMIN_PASSWORD is not set; skipping lab account creation"
            )
            return

        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username, defaults={"email": email}
        )
        if created:
            user.set_password(password)
            user.save(update_fields=["password"])
            self.stdout.write(f"[lab-user] created {username}")
        else:
            self.stdout.write(f"[lab-user] {username} already exists")
