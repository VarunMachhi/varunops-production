from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Prefetch

from core.models import (
    AppCatalog, AuditLog, Command as AgentCommand, EmployeeProfile, Machine, NetworkPolicy,
    SoftwareRequest, SupportTicket, TicketAttachment, UnauthorizedSoftware,
)
from core.serializers import (
    AppCatalogSerializer, AuditLogSerializer, CommandSerializer,
    EmployeeProfileSerializer, MachineSerializer, NetworkPolicySerializer,
    SoftwareRequestSerializer, SupportTicketSerializer,
)


class Command(BaseCommand):
    help = "Verify the Admin workspace queries/serializers without starting the web server."

    def handle(self, *args, **options):
        checks = []
        try:
            machines = Machine.objects.select_related("network_policy").prefetch_related(
                "installed_apps__app",
                "unauthorized_software",
                "detected_software__catalog_app",
                "app_policies__app",
            ).all()
            checks.append(("machines", lambda: MachineSerializer(machines, many=True).data))
            checks.append(("apps", lambda: AppCatalogSerializer(AppCatalog.objects.filter(enabled=True), many=True).data))
            checks.append(("commands", lambda: CommandSerializer(AgentCommand.objects.select_related("machine", "app").all()[:100], many=True).data))
            checks.append(("activity", lambda: AuditLogSerializer(AuditLog.objects.select_related("actor", "machine").all()[:100], many=True).data))
            checks.append(("requests", lambda: SoftwareRequestSerializer(SoftwareRequest.objects.select_related("employee", "machine", "app", "reviewed_by", "linked_command").all()[:150], many=True).data))
            tickets = SupportTicket.objects.select_related("employee", "machine", "assigned_to").prefetch_related(
                "messages__author",
                Prefetch("messages__attachment", queryset=TicketAttachment.objects.only("id", "message_id", "original_name", "content_type", "size")),
            ).all()[:150]
            checks.append(("tickets", lambda: SupportTicketSerializer(tickets, many=True).data))
            checks.append(("network policies", lambda: NetworkPolicySerializer(NetworkPolicy.objects.annotate(machine_count=Count("machines")).all(), many=True).data))
            checks.append(("employees", lambda: EmployeeProfileSerializer(EmployeeProfile.objects.select_related("user", "assigned_machine").all(), many=True).data))

            for name, fn in checks:
                fn()
                self.stdout.write(self.style.SUCCESS(f"[OK] {name}"))
            UnauthorizedSoftware.objects.filter(resolved=False).count()
            self.stdout.write(self.style.SUCCESS("[OK] unauthorized software counter"))
        except Exception as exc:
            raise CommandError(f"Workspace verification failed while checking '{name}': {type(exc).__name__}: {exc}") from exc

        self.stdout.write(self.style.SUCCESS("VarunOps workspace verification passed."))
