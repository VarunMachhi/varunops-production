import os
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create/update the production administrator from environment variables."

    def handle(self, *args, **options):
        username = os.getenv("ADMIN_USERNAME", "admin").strip()
        password = os.getenv("ADMIN_PASSWORD", "")
        email = os.getenv("ADMIN_EMAIL", "").strip()
        if not username:
            raise CommandError("ADMIN_USERNAME is required.")
        if len(password) < 14:
            raise CommandError("ADMIN_PASSWORD must be at least 14 characters.")
        User = get_user_model()
        user, created = User.objects.get_or_create(username=username, defaults={"email": email})
        user.email = email or user.email
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        # Set only when newly created or explicitly requested, so every deploy does not reset it.
        if created or os.getenv("RESET_ADMIN_PASSWORD", "0").lower() in {"1", "true", "yes"}:
            user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Production admin ready: {username}"))
