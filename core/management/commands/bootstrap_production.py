import os
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create/update the production administrator from environment variables without resetting it on every deploy."

    def handle(self, *args, **options):
        username = os.getenv("ADMIN_USERNAME", "admin").strip()
        password = os.getenv("ADMIN_PASSWORD", "")
        email = os.getenv("ADMIN_EMAIL", "").strip()
        reset_requested = os.getenv("RESET_ADMIN_PASSWORD", "0").lower() in {"1", "true", "yes"}

        if not username:
            raise CommandError("ADMIN_USERNAME is required.")

        User = get_user_model()
        user = User.objects.filter(username=username).first()
        creating = user is None

        # A password is required only when an administrator must actually be created
        # or when the operator explicitly requests a password reset. Existing admins
        # must not make every deploy depend on ADMIN_PASSWORD being present.
        if creating or reset_requested:
            if len(password) < 14:
                reason = "create the first production administrator" if creating else "reset the administrator password"
                raise CommandError(
                    f"ADMIN_PASSWORD must be at least 14 characters to {reason}. "
                    "Set it in Render -> Environment and redeploy."
                )

        if creating:
            user = User(username=username, email=email)
            user.set_password(password)
            created_text = "created"
        else:
            created_text = "already exists"
            if email:
                user.email = email
            if reset_requested:
                user.set_password(password)

        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.save()

        if reset_requested:
            self.stdout.write(self.style.WARNING("Administrator password was explicitly reset from ADMIN_PASSWORD."))
        self.stdout.write(self.style.SUCCESS(f"Production admin ready: {username} ({created_text})"))
