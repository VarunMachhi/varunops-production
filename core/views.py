import secrets
import os
import json
import uuid
import re
import io
import zipfile
import logging
import csv
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.contrib.auth.hashers import make_password, check_password
from django.db import transaction
from django.db.models import Count, Q, Prefetch
from django.http import FileResponse, JsonResponse, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from datetime import timedelta
from django.views.decorators.http import require_GET
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from PIL import Image
from rest_framework.response import Response

from .authentication import AgentKeyAuthentication
from .models import (
    AppCatalog, AuditLog, Command, EmployeeProfile, InstalledApp, Machine, Notification,
    SoftwareRequest, SupportTicket, TicketAttachment, TicketMessage,
    NetworkPolicy, MachineAppPolicy, UnauthorizedSoftware, DetectedSoftware, DeviceMetric, PowerEvent, DevicePairingCode, AgentTask, PasswordResetOTP,
)
from .serializers import (
    AppCatalogSerializer, AuditLogSerializer, CommandSerializer, EmployeeMachineSerializer,
    EmployeeProfileSerializer, MachineSerializer, NotificationSerializer, SoftwareRequestSerializer,
    SupportTicketSerializer, NetworkPolicySerializer, UnauthorizedSoftwareSerializer,
)
from .throttles import AgentEnrollThrottle, AgentThrottle

logger = logging.getLogger("varunops")


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")) or None


def audit(request, event, message, kind="info", machine=None, metadata=None):
    actor = getattr(request, "user", None)
    if not getattr(actor, "is_authenticated", False) or not hasattr(actor, "_meta"):
        actor = None
    return AuditLog.objects.create(
        actor=actor,
        machine=machine,
        event=event,
        message=message,
        kind=kind,
        metadata=metadata or {},
        ip_address=client_ip(request),
    )


def landing(request):
    return render(request, "core/landing.html")


@login_required
def workspace(request):
    if request.user.is_staff:
        return redirect("console")
    return redirect("employee_portal")


@login_required
def console(request):
    if not request.user.is_staff:
        return redirect("employee_portal")
    return render(request, "core/console.html")


@login_required
def employee_portal(request):
    if request.user.is_staff:
        return redirect("console")
    EmployeeProfile.objects.get_or_create(user=request.user)
    return render(request, "core/employee.html")


@login_required
def employee_agent_package(request):
    if request.user.is_staff:
        return JsonResponse({"detail": "Staff accounts use the admin console."}, status=403)
    base_url = request.build_absolute_uri("/").rstrip("/")
    agent_dir = settings.BASE_DIR / "agent"
    files = ["VarunOpsAgent.ps1", "install_agent.ps1", "update_agent.ps1", "CHECK_AGENT.bat"]
    for name in files:
        if not (agent_dir / name).exists():
            return JsonResponse({"detail": f"Agent package is missing {name}."}, status=500)
    bat = """@echo off
setlocal
net session >nul 2>&1
if %errorlevel% neq 0 (
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
echo.
echo ==================================
echo   VarunOps - Connect This Company PC
echo ==================================
echo Server: __SERVER__
echo.
set /p CODE=Enter the 8-digit pairing code from VarunOps: 
set /p BRANCH=Branch name (optional): 
if "%CODE%"=="" goto :bad
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_agent.ps1" -ServerUrl "__SERVER__" -PairingCode "%CODE%" -Branch "%BRANCH%"
if errorlevel 1 goto :bad
echo.
echo PC connected to VarunOps.
pause
exit /b 0
:bad
echo.
echo Setup failed. Check the code and internet connection.
pause
exit /b 1
""".replace("__SERVER__", base_url)
    update_bat = """@echo off
setlocal
net session >nul 2>&1
if %errorlevel% neq 0 (
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0update_agent.ps1"
if errorlevel 1 (
  echo.
  echo Agent update failed.
  pause
  exit /b 1
)
echo.
echo Agent repaired and verified. Refresh VarunOps in 10-20 seconds.
pause
"""
    readme = f"""VarunOps PC Connector

NEW PC
1. Sign in to {base_url}/employee/
2. Generate a pairing code.
3. Extract this ZIP.
4. Run CONNECT_THIS_PC.bat as Administrator and enter the code.

EXISTING VARUNOPS PC
If this PC is already paired but the portal says the first full scan is incomplete, run UPDATE_EXISTING_AGENT.bat as Administrator. It preserves the existing device registration, replaces legacy EXE scheduled tasks, runs a strict server sync test, and upgrades the inventory collector.

The first install starts in TEST mode. Software commands remain queued until IT intentionally enables LIVE actions from the Admin device page.
"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in files:
            zf.write(agent_dir / name, arcname=name)
        zf.writestr("CONNECT_THIS_PC.bat", bat)
        zf.writestr("UPDATE_EXISTING_AGENT.bat", update_bat)
        zf.writestr("README.txt", readme)
    buffer.seek(0)
    response = FileResponse(buffer, as_attachment=True, filename="VarunOps-PC-Connector.zip")
    response["Content-Type"] = "application/zip"
    response["Cache-Control"] = "private, no-store"
    return response


@require_GET
def health(request):
    return JsonResponse({"ok": True, "service": "varunops"})


def _bounded_json(value, depth=0):
    """Keep agent JSON structured but bounded before storing it in Machine.system_info."""
    if depth > 3:
        return str(value)[:300]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:500]
    if isinstance(value, list):
        return [_bounded_json(item, depth + 1) for item in value[:30]]
    if isinstance(value, dict):
        return {str(k)[:80]: _bounded_json(v, depth + 1) for k, v in list(value.items())[:40]}
    return str(value)[:500]


def _clean_arg_list(value, limit=20):
    if not isinstance(value, list):
        return []
    output = []
    for item in value[:limit]:
        arg = str(item).strip()[:240]
        if arg and "\x00" not in arg and "\r" not in arg and "\n" not in arg:
            output.append(arg)
    return output


def _direct_installer_valid(app):
    if app.source_type != AppCatalog.SOURCE_DIRECT:
        return True
    try:
        parsed = urlparse(app.installer_url or "")
    except ValueError:
        return False
    return (
        parsed.scheme == "https" and bool(parsed.netloc)
        and bool(re.fullmatch(r"[a-fA-F0-9]{64}", app.installer_sha256 or ""))
        and app.installer_kind in {AppCatalog.INSTALLER_EXE, AppCatalog.INSTALLER_MSI}
    )


def _app_deployment_error(app, action):
    if action in {Command.ACTION_INSTALL, Command.ACTION_UPDATE}:
        if app.source_type == AppCatalog.SOURCE_WINGET:
            if not app.winget_id:
                return "This app uses Winget but no Winget package ID is configured."
        elif app.source_type == AppCatalog.SOURCE_DIRECT:
            if not _direct_installer_valid(app):
                return "Direct installer needs an HTTPS URL, installer type, and a 64-character SHA-256 checksum."
        else:
            return "Unsupported installer source."
    if action == Command.ACTION_UNINSTALL and not app.winget_id:
        return "Uninstall requires a Winget package ID in this build."
    return ""


def _machine_app_policy_map(machine):
    """Return explicit app policies for one machine keyed by app id."""
    return {item.app_id: item for item in MachineAppPolicy.objects.filter(machine=machine).select_related("app")}


def _employee_store_apps(machine):
    """Return only software IT has made available for this particular PC.

    If a machine has no explicit app-policy rows yet, all employee-visible catalog
    apps are treated as Optional for backwards compatibility. Once IT creates any
    per-PC app policy, the list becomes an explicit allowlist: only Required or
    Optional apps with an explicit row are shown to that employee.
    """
    base = AppCatalog.objects.filter(enabled=True, employee_visible=True).order_by("name")
    if not machine:
        return []
    policies = _machine_app_policy_map(machine)
    strict = bool(policies)
    rows = []
    installed = {x.app_id: x for x in InstalledApp.objects.filter(machine=machine).select_related("app")}
    for app in base:
        pol = policies.get(app.pk)
        if strict and (not pol or pol.mode == MachineAppPolicy.MODE_BLOCKED):
            continue
        if pol and pol.mode == MachineAppPolicy.MODE_BLOCKED:
            continue
        data = AppCatalogSerializer(app).data
        data["policy_mode"] = pol.mode if pol else MachineAppPolicy.MODE_OPTIONAL
        data["auto_update"] = pol.auto_update if pol else True
        item = installed.get(app.pk)
        data["installed_version"] = item.version if item else None
        rows.append(data)
    return rows


def _is_windows_baseline(display_name, publisher):
    """Conservative Windows component baseline to reduce false alerts.

    We intentionally do not whitelist every Microsoft-published application, since
    employees can install Microsoft products too. Only common OS/runtime components
    are treated as baseline when they are not explicitly in the company catalog.
    """
    name = str(display_name or "").casefold()
    pub = str(publisher or "").casefold()
    if not pub.startswith("microsoft"):
        return False
    patterns = (
        "microsoft visual c++", "edge webview2 runtime", "microsoft update health tools",
        "windows app runtime", "microsoft windows desktop runtime", ".net runtime",
        ".net host", ".net targeting pack", "windows sdk", "microsoft edge update",
    )
    return any(p in name for p in patterns)


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAdminUser])
def bootstrap(request):
    error_id = secrets.token_hex(4)
    try:
        machines = Machine.objects.select_related("network_policy").prefetch_related(
            "installed_apps__app", "unauthorized_software", "detected_software__catalog_app", "app_policies__app"
        ).all()
        apps = AppCatalog.objects.filter(enabled=True)
        commands = Command.objects.select_related("machine", "app").all()[:100]
        activity = AuditLog.objects.select_related("actor", "machine").all()[:100]
        software_requests = SoftwareRequest.objects.select_related(
            "employee", "machine", "app", "reviewed_by", "linked_command"
        ).all()[:150]
        tickets = SupportTicket.objects.select_related(
            "employee", "machine", "assigned_to"
        ).prefetch_related(
            "messages__author",
            Prefetch(
                "messages__attachment",
                queryset=TicketAttachment.objects.only("id", "message_id", "original_name", "content_type", "size"),
            ),
        ).all()[:150]
        network_policies = NetworkPolicy.objects.annotate(machine_count=Count("machines")).all()
        employees = EmployeeProfile.objects.select_related("user", "assigned_machine").all()
        payload = {
            "user": {"username": request.user.username, "is_superuser": request.user.is_superuser},
            "machines": MachineSerializer(machines, many=True).data,
            "apps": AppCatalogSerializer(apps, many=True).data,
            "commands": CommandSerializer(commands, many=True).data,
            "activity": AuditLogSerializer(activity, many=True).data,
            "software_requests": SoftwareRequestSerializer(software_requests, many=True).data,
            "tickets": SupportTicketSerializer(tickets, many=True).data,
            "network_policies": NetworkPolicySerializer(network_policies, many=True).data,
            "employees": EmployeeProfileSerializer(employees, many=True).data,
            "unauthorized_count": UnauthorizedSoftware.objects.filter(resolved=False).count(),
        }
        return Response(payload)
    except Exception as exc:
        logger.exception("Admin bootstrap failed [%s]", error_id)
        detail = "Admin workspace data could not be loaded. Close VarunOps and run REPAIR_VARUNOPS.bat."
        if settings.DEBUG:
            detail += f" {type(exc).__name__}: {exc}"
        return Response({"detail": detail, "error_id": error_id}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAdminUser])
def create_commands(request):
    action = str(request.data.get("action", "")).lower().strip()
    targets = request.data.get("targets", [])
    if action not in {Command.ACTION_INSTALL, Command.ACTION_UPDATE, Command.ACTION_UNINSTALL}:
        return Response({"detail": "Unsupported action"}, status=status.HTTP_400_BAD_REQUEST)
    if not isinstance(targets, list) or not targets or len(targets) > 500:
        return Response({"detail": "Select between 1 and 500 targets"}, status=status.HTTP_400_BAD_REQUEST)

    created, blocked, invalid = [], [], []
    with transaction.atomic():
        for target in targets:
            if not isinstance(target, dict):
                invalid.append({"detail": "target must be an object"})
                continue
            machine_id = str(target.get("machine_id", ""))
            app_slug = str(target.get("app_slug", ""))[:64]
            try:
                machine = Machine.objects.select_for_update().get(pk=machine_id, enabled=True)
                app = AppCatalog.objects.get(slug=app_slug, enabled=True)
            except (Machine.DoesNotExist, AppCatalog.DoesNotExist, ValueError):
                invalid.append({"machine_id": machine_id, "app_slug": app_slug})
                continue
            if machine.policy == Machine.POLICY_LOCKED:
                blocked.append(f"{machine.name}: machine policy locked")
                continue
            deploy_error = _app_deployment_error(app, action)
            if deploy_error:
                blocked.append(f"{machine.name}: {app.name}: {deploy_error}")
                continue
            app_policy = MachineAppPolicy.objects.filter(machine=machine, app=app).first()
            if app_policy and app_policy.mode == MachineAppPolicy.MODE_BLOCKED and action in {Command.ACTION_INSTALL, Command.ACTION_UPDATE}:
                blocked.append(f"{machine.name}: {app.name} is blocked by software policy")
                continue
            if app_policy and app_policy.mode == MachineAppPolicy.MODE_REQUIRED and action == Command.ACTION_UNINSTALL:
                blocked.append(f"{machine.name}: {app.name} is required by software policy")
                continue
            # Prevent duplicate queued/running work for the same machine/app/action.
            cmd, was_created = Command.objects.get_or_create(
                machine=machine,
                app=app,
                action=action,
                status=Command.STATUS_QUEUED,
                defaults={"requested_by": request.user},
            )
            if was_created:
                created.append(cmd)

    audit(
        request,
        "commands.create",
        f"{action.title()} queued for {len(created)} app target(s)",
        "success" if created else "warning",
        metadata={"created": len(created), "blocked": blocked, "invalid": invalid},
    )
    return Response({
        "created": len(created),
        "blocked": sorted(set(blocked)),
        "invalid": invalid,
    }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAdminUser])
def assign_policy(request):
    machine_ids = request.data.get("machine_ids", [])
    policy = str(request.data.get("policy", "")).lower()
    valid_policies = {x[0] for x in Machine.POLICY_CHOICES}
    if policy not in valid_policies or not isinstance(machine_ids, list) or not machine_ids:
        return Response({"detail": "Invalid policy or machine selection"}, status=400)
    if len(machine_ids) > 500:
        return Response({"detail": "Too many machines"}, status=400)
    try:
        machine_ids = [uuid.UUID(str(value)) for value in machine_ids]
    except (ValueError, TypeError, AttributeError):
        return Response({"detail": "Invalid machine identifier"}, status=400)
    updated = Machine.objects.filter(id__in=machine_ids, enabled=True).update(policy=policy)
    audit(request, "policy.assign", f"{policy.title()} policy applied to {updated} machine(s)", "success", metadata={"policy": policy, "count": updated})
    return Response({"updated": updated})


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAdminUser])
def cancel_command(request, command_id):
    try:
        command = Command.objects.get(pk=command_id, status=Command.STATUS_QUEUED)
    except (Command.DoesNotExist, ValueError):
        return Response({"detail": "Queued command not found"}, status=404)
    command.status = Command.STATUS_CANCELLED
    command.completed_at = timezone.now()
    command.result_message = "Cancelled from console"
    command.save(update_fields=["status", "completed_at", "result_message"])
    linked_request = SoftwareRequest.objects.filter(linked_command=command).select_related("employee", "app").first()
    if linked_request:
        linked_request.status = SoftwareRequest.STATUS_CANCELLED
        linked_request.completed_at = timezone.now()
        linked_request.save(update_fields=["status", "completed_at"])
        notify_user(linked_request.employee, "Software request cancelled", f"The queued {linked_request.app.name} action was cancelled by IT.", "warning", "/employee/#requests")
    audit(request, "command.cancel", f"Cancelled {command.action} for {command.machine.name}/{command.app.name}", "warning", machine=command.machine)
    return Response({"ok": True})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([AgentEnrollThrottle])
def agent_enroll(request):
    if not isinstance(request.data, dict):
        return Response({"detail": "JSON object required"}, status=400)
    supplied = request.headers.get("X-Enrollment-Token", "")
    expected = settings.AGENT_ENROLLMENT_TOKEN
    if not expected or not supplied or not secrets.compare_digest(supplied, expected):
        return Response({"detail": "Enrollment denied"}, status=403)

    name = str(request.data.get("name", "")).strip()[:120]
    if len(name) < 2:
        return Response({"detail": "Machine name is required"}, status=400)
    branch = str(request.data.get("branch", ""))[:120]
    device_type = str(request.data.get("device_type", "Desktop"))[:40]
    os_version = str(request.data.get("os_version", ""))[:180]
    serial_number = str(request.data.get("serial_number", ""))[:120]

    secret = secrets.token_urlsafe(48)
    machine, created = Machine.objects.get_or_create(name=name, defaults={
        "branch": branch,
        "device_type": device_type,
        "os_version": os_version,
        "serial_number": serial_number,
    })
    if not created and machine.agent_key_hash:
        return Response({"detail": "Machine is already enrolled. Rotate its key from the server instead of re-enrolling."}, status=409)
    machine.branch = branch or machine.branch
    machine.device_type = device_type or machine.device_type
    machine.os_version = os_version or machine.os_version
    machine.serial_number = serial_number or machine.serial_number
    machine.agent_key_hash = make_password(secret)
    machine.agent_key_rotated_at = timezone.now()
    machine.enabled = True
    machine.save()
    audit(request, "agent.enroll", f"Agent enrolled for {machine.name}", "success", machine=machine)
    return Response({"agent_id": str(machine.id), "agent_key": secret, "name": machine.name}, status=201)


@api_view(["GET"])
@authentication_classes([AgentKeyAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([AgentThrottle])
def agent_manifest(request):
    machine = request.auth
    apps = AppCatalog.objects.filter(enabled=True)
    app_policies = {p.app_id: p for p in MachineAppPolicy.objects.filter(machine=machine).select_related("app")}
    policy = machine.network_policy if machine.network_policy_id and machine.network_policy and machine.network_policy.enabled else None
    return Response({
        "apps": [
            {
                "slug": app.slug,
                "name": app.name,
                "latest_version": app.latest_version,
                "winget_id": app.winget_id,
                "source_type": app.source_type,
                "installer_url": app.installer_url,
                "installer_sha256": app.installer_sha256,
                "installer_kind": app.installer_kind,
                "install_args": app.install_args,
                "update_args": app.update_args,
                "detection_names": app.detection_names,
                "policy_mode": app_policies.get(app.pk).mode if app.pk in app_policies else "optional",
                "auto_update": app_policies.get(app.pk).auto_update if app.pk in app_policies else True,
            }
            for app in apps
        ],
        "compliance_mode": machine.compliance_mode,
        "live_actions": machine.agent_live_mode,
        "network_policy": ({
            "id": policy.pk, "name": policy.name, "mode": policy.mode,
            "allowed_sites": policy.allowed_sites, "blocked_sites": policy.blocked_sites,
            "enforce_edge": policy.enforce_edge, "enforce_chrome": policy.enforce_chrome,
            "revision": policy.revision,
        } if policy else None),
    })


@api_view(["POST"])
@authentication_classes([AgentKeyAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([AgentThrottle])
def agent_heartbeat(request):
    machine = request.auth
    data = request.data
    if not isinstance(data, dict):
        return Response({"detail": "JSON object required"}, status=400)
    machine.ip_address = data.get("ip_address") or machine.ip_address
    machine.os_version = str(data.get("os_version", machine.os_version))[:180]
    machine.serial_number = str(data.get("serial_number", machine.serial_number))[:120]
    info = data.get("system_info", {})
    if isinstance(info, dict):
        # hard cap simple JSON inventory to avoid unbounded storage abuse
        machine.system_info = _bounded_json(info)
    machine.last_seen = timezone.now()
    machine.save(update_fields=["ip_address", "os_version", "serial_number", "system_info", "last_seen"])

    reported = data.get("apps", None)
    if isinstance(reported, list):
        allowed_apps = {a.slug: a for a in AppCatalog.objects.filter(enabled=True)}
        seen = set()
        for item in reported[:250]:
            if not isinstance(item, dict):
                continue
            slug = str(item.get("slug", ""))[:64]
            app = allowed_apps.get(slug)
            if not app:
                continue
            version = str(item.get("version", ""))[:64]
            detected_name = str(item.get("detected_name", ""))[:180]
            InstalledApp.objects.update_or_create(
                machine=machine,
                app=app,
                defaults={"version": version, "detected_name": detected_name},
            )
            seen.add(app.pk)
        InstalledApp.objects.filter(machine=machine).exclude(app_id__in=seen).delete()

    # Near-real-time device telemetry. Keep the newest sample directly on the Machine
    # so dashboards remain fast and free-tier databases do not grow every 10 seconds.
    # A historical snapshot is kept approximately every 15 minutes; seven days are retained.
    metrics = data.get("metrics", {})
    if isinstance(metrics, dict):
        try:
            clean_metrics = {
                "cpu_percent": max(0, min(100, float(metrics.get("cpu_percent", 0) or 0))),
                "memory_percent": max(0, min(100, float(metrics.get("memory_percent", 0) or 0))),
                "memory_used_gb": max(0, float(metrics.get("memory_used_gb", 0) or 0)),
                "memory_total_gb": max(0, float(metrics.get("memory_total_gb", 0) or 0)),
                "storage_percent": max(0, min(100, float(metrics.get("storage_percent", 0) or 0))),
                "storage_used_gb": max(0, float(metrics.get("storage_used_gb", 0) or 0)),
                "storage_total_gb": max(0, float(metrics.get("storage_total_gb", 0) or 0)),
                "storage_volumes": (metrics.get("storage_volumes", [])[:20] if isinstance(metrics.get("storage_volumes", []), list) else []),
                "uptime_seconds": max(0, int(metrics.get("uptime_seconds", 0) or 0)),
            }
            now = timezone.now()
            machine.live_metrics = clean_metrics
            machine.metrics_updated_at = now
            machine.save(update_fields=["live_metrics", "metrics_updated_at"])
            newest = DeviceMetric.objects.filter(machine=machine).order_by("-recorded_at").only("recorded_at").first()
            if not newest or (now - newest.recorded_at).total_seconds() >= 900:
                DeviceMetric.objects.create(machine=machine, **clean_metrics)
            DeviceMetric.objects.filter(machine=machine, recorded_at__lt=now-timedelta(days=7)).delete()
        except (TypeError, ValueError):
            pass

    boot_time = parse_datetime(str(data.get("boot_time", ""))) if data.get("boot_time") else None
    if boot_time and (not machine.last_boot_at or abs((machine.last_boot_at - boot_time).total_seconds()) > 2):
        machine.last_boot_at = boot_time
        machine.save(update_fields=["last_boot_at"])
        PowerEvent.objects.get_or_create(machine=machine, event_type=PowerEvent.EVENT_BOOT, occurred_at=boot_time, defaults={"source_id": "agent-boot"})

    power_events = data.get("power_events", [])
    if isinstance(power_events, list):
        allowed_event_types = {PowerEvent.EVENT_BOOT, PowerEvent.EVENT_SHUTDOWN, PowerEvent.EVENT_UNEXPECTED}
        for item in power_events[:40]:
            if not isinstance(item, dict):
                continue
            event_type = str(item.get("event_type", ""))[:24]
            occurred_at = parse_datetime(str(item.get("occurred_at", "")))
            if event_type in allowed_event_types and occurred_at:
                PowerEvent.objects.get_or_create(
                    machine=machine, event_type=event_type, occurred_at=occurred_at,
                    defaults={"source_id": str(item.get("source_id", ""))[:80]},
                )

    # Persist the complete reported software inventory and classify it against this PC's policy.
    inventory = data.get("software_inventory", None)
    if isinstance(inventory, list):
        policies = {p.app_id: p for p in MachineAppPolicy.objects.filter(machine=machine).select_related("app")}
        catalog = list(AppCatalog.objects.filter(enabled=True))
        approved_catalog = [a for a in catalog if not policies or (a.pk in policies and policies[a.pk].mode != MachineAppPolicy.MODE_BLOCKED)]
        exceptions = {str(x).casefold() for x in (machine.software_exceptions or [])}
        currently_unauthorized = set()
        currently_seen = set()
        assigned_profile = EmployeeProfile.objects.filter(assigned_machine=machine).select_related("user").first()
        assigned_label = ""
        if assigned_profile:
            assigned_label = assigned_profile.user.get_full_name() or assigned_profile.user.username

        for item in inventory[:700]:
            if not isinstance(item, dict):
                continue
            display_name = str(item.get("name", "")).strip()[:180]
            version = str(item.get("version", ""))[:64]
            publisher = str(item.get("publisher", ""))[:140]
            if not display_name:
                continue

            low = display_name.casefold()
            matched_app = None
            for app in approved_catalog:
                names = [str(x).casefold() for x in (app.detection_names or []) if x] or [app.name.casefold()]
                if any(n == low or n in low for n in names):
                    matched_app = app
                    break

            if low in exceptions:
                classification = DetectedSoftware.CLASS_EXCEPTION
            elif matched_app:
                classification = DetectedSoftware.CLASS_CATALOG
            elif _is_windows_baseline(display_name, publisher):
                classification = DetectedSoftware.CLASS_SYSTEM
            else:
                classification = DetectedSoftware.CLASS_UNAUTHORIZED

            DetectedSoftware.objects.update_or_create(
                machine=machine,
                display_name=display_name,
                defaults={
                    "version": version,
                    "publisher": publisher,
                    "catalog_app": matched_app,
                    "classification": classification,
                },
            )
            currently_seen.add(display_name)

            if classification == DetectedSoftware.CLASS_UNAUTHORIZED:
                currently_unauthorized.add(low)
                previous = UnauthorizedSoftware.objects.filter(machine=machine, display_name=display_name).only("resolved").first()
                should_notify = previous is None or bool(previous.resolved)
                event, created = UnauthorizedSoftware.objects.update_or_create(
                    machine=machine, display_name=display_name,
                    defaults={"version": version, "publisher": publisher, "resolved": False, "resolution": ""},
                )
                if should_notify:
                    where = f" on {machine.name}" + (f" (assigned to {assigned_label})" if assigned_label else "")
                    notify_staff(
                        "Unauthorized software detected",
                        f"{display_name} {version or ''} was detected{where}.",
                        "warning", "/console/#compliance",
                    )
                    audit(
                        request, "compliance.unauthorized",
                        f"Unauthorized software detected: {display_name}",
                        "warning", machine=machine,
                        metadata={"version": version, "publisher": publisher, "assigned_employee": assigned_label},
                    )

        # Only prune the stored inventory after receiving at least one valid entry.
        if currently_seen:
            DetectedSoftware.objects.filter(machine=machine).exclude(display_name__in=currently_seen).delete()

        for event in UnauthorizedSoftware.objects.filter(machine=machine, resolved=False):
            if event.display_name.casefold() not in currently_unauthorized:
                event.resolved = True
                event.resolution = "No longer detected or approved"
                event.save(update_fields=["resolved", "resolution"])

    # Per-PC software policy: required apps can be restored, blocked apps removed, and approved apps updated.
    installed_by_app = {x.app_id: x for x in InstalledApp.objects.filter(machine=machine).select_related("app")}
    for policy_item in MachineAppPolicy.objects.filter(machine=machine).select_related("app"):
        installed = installed_by_app.get(policy_item.app_id)
        desired_action = None
        if machine.compliance_mode == Machine.COMPLIANCE_ENFORCE:
            if policy_item.mode == MachineAppPolicy.MODE_REQUIRED and not installed:
                desired_action = Command.ACTION_INSTALL
            elif policy_item.mode == MachineAppPolicy.MODE_BLOCKED and installed:
                desired_action = Command.ACTION_UNINSTALL
        if installed and policy_item.mode != MachineAppPolicy.MODE_BLOCKED and policy_item.auto_update and installed.app.latest_version and installed.version != installed.app.latest_version:
            desired_action = Command.ACTION_UPDATE
        if desired_action and machine.policy != Machine.POLICY_LOCKED:
            exists = Command.objects.filter(machine=machine, app=policy_item.app, action=desired_action, status__in=[Command.STATUS_QUEUED, Command.STATUS_RUNNING]).exists()
            if not exists:
                Command.objects.create(machine=machine, app=policy_item.app, action=desired_action)

    # Automatic means: keep already-installed approved apps current; never auto-install missing apps.
    if machine.policy == Machine.POLICY_AUTOMATIC:
        auto_count = 0
        blocked_ids = set(MachineAppPolicy.objects.filter(machine=machine, mode=MachineAppPolicy.MODE_BLOCKED).values_list("app_id", flat=True))
        for installed in InstalledApp.objects.filter(machine=machine).select_related("app"):
            if installed.app_id in blocked_ids or not installed.version or not installed.app.latest_version or installed.version == installed.app.latest_version:
                continue
            duplicate = Command.objects.filter(
                machine=machine, app=installed.app, action=Command.ACTION_UPDATE,
                status__in=[Command.STATUS_QUEUED, Command.STATUS_RUNNING],
            ).exists()
            if not duplicate:
                Command.objects.create(machine=machine, app=installed.app, action=Command.ACTION_UPDATE)
                auto_count += 1
        if auto_count:
            audit(request, "policy.auto_queue", f"Automatic policy queued {auto_count} update(s) for {machine.name}", "info", machine=machine)

    machine.refresh_from_db(fields=["system_info", "live_metrics", "metrics_updated_at", "last_seen"])
    system_info_received = bool(machine.system_info)
    metrics_received = bool(machine.metrics_updated_at and machine.live_metrics)
    agent_version = str((machine.system_info or {}).get("agent_version", ""))
    machine_ready = bool(system_info_received and metrics_received and agent_version.startswith("4.2"))
    return Response({
        "ok": True,
        "server_time": timezone.now().isoformat(),
        "policy": machine.policy,
        "compliance_mode": machine.compliance_mode,
        "network_policy_revision": machine.network_policy.revision if machine.network_policy_id else None,
        "system_info_received": system_info_received,
        "metrics_received": metrics_received,
        "machine_ready": machine_ready,
        "agent_version": agent_version,
    })


@api_view(["GET"])
@authentication_classes([AgentKeyAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([AgentThrottle])
def agent_commands(request):
    machine = request.auth
    if not machine.agent_live_mode:
        return Response({"commands": [], "test_mode": True})
    now = timezone.now()
    stale_cutoff = now - timedelta(minutes=30)

    # Recover commands whose agent disappeared after pickup. Three failed leases becomes terminal.
    stale = Command.objects.filter(machine=machine, status=Command.STATUS_RUNNING, last_dispatch_at__lt=stale_cutoff)
    for cmd in stale:
        if cmd.attempts >= 3:
            cmd.status = Command.STATUS_FAILED
            cmd.completed_at = now
            cmd.result_message = "Agent did not report a result after three dispatch attempts."
            cmd.save(update_fields=["status", "completed_at", "result_message"])
            linked_request = SoftwareRequest.objects.filter(linked_command=cmd).select_related("employee", "app").first()
            if linked_request:
                linked_request.status = SoftwareRequest.STATUS_FAILED
                linked_request.completed_at = now
                linked_request.save(update_fields=["status", "completed_at"])
                notify_user(linked_request.employee, "Software installation needs attention", f"{linked_request.app.name} could not be confirmed by the device agent. IT has been notified.", "warning", "/employee/#requests")
        else:
            cmd.status = Command.STATUS_QUEUED
            cmd.save(update_fields=["status"])

    commands = list(
        Command.objects.filter(machine=machine, status=Command.STATUS_QUEUED)
        .select_related("app")
        .order_by("requested_at")[:20]
    )
    payload = []
    for cmd in commands:
        cmd.status = Command.STATUS_RUNNING
        cmd.started_at = cmd.started_at or now
        cmd.last_dispatch_at = now
        cmd.attempts += 1
        cmd.save(update_fields=["status", "started_at", "last_dispatch_at", "attempts"])
        payload.append({
            "id": str(cmd.id),
            "action": cmd.action,
            "app": {
                "slug": cmd.app.slug,
                "name": cmd.app.name,
                "winget_id": cmd.app.winget_id,
                "latest_version": cmd.app.latest_version,
                "source_type": cmd.app.source_type,
                "installer_url": cmd.app.installer_url,
                "installer_sha256": cmd.app.installer_sha256,
                "installer_kind": cmd.app.installer_kind,
                "install_args": cmd.app.install_args,
                "update_args": cmd.app.update_args,
            },
        })
    if commands:
        audit(request, "agent.dispatch", f"Dispatched {len(commands)} command(s) to {machine.name}", "info", machine=machine)
    return Response({"commands": payload})


@api_view(["POST"])
@authentication_classes([AgentKeyAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([AgentThrottle])
def agent_command_result(request, command_id):
    machine = request.auth
    if not isinstance(request.data, dict):
        return Response({"detail": "JSON object required"}, status=400)
    try:
        command = Command.objects.select_related("app").get(pk=command_id, machine=machine, status=Command.STATUS_RUNNING)
    except (Command.DoesNotExist, ValueError):
        return Response({"detail": "Running command not found"}, status=404)
    result_status = str(request.data.get("status", "")).lower()
    if result_status not in {Command.STATUS_SUCCEEDED, Command.STATUS_FAILED}:
        return Response({"detail": "Invalid result status"}, status=400)
    command.status = result_status
    command.completed_at = timezone.now()
    command.result_message = str(request.data.get("message", ""))[:4000]
    command.save(update_fields=["status", "completed_at", "result_message"])

    if result_status == Command.STATUS_SUCCEEDED:
        if command.action == Command.ACTION_UNINSTALL:
            InstalledApp.objects.filter(machine=machine, app=command.app).delete()
        else:
            version = str(request.data.get("version", command.app.latest_version))[:64]
            InstalledApp.objects.update_or_create(machine=machine, app=command.app, defaults={"version": version})

    linked_request = SoftwareRequest.objects.filter(linked_command=command).select_related("employee", "app", "machine").first()
    if linked_request:
        linked_request.status = SoftwareRequest.STATUS_COMPLETED if result_status == Command.STATUS_SUCCEEDED else SoftwareRequest.STATUS_FAILED
        linked_request.completed_at = timezone.now()
        linked_request.save(update_fields=["status", "completed_at"])
        if result_status == Command.STATUS_SUCCEEDED:
            notify_user(linked_request.employee, "Software ready", f"{linked_request.app.name} is ready on {linked_request.machine.name}.", "success", "/employee/#software")
        else:
            notify_user(linked_request.employee, "Software action failed", f"IT could not complete {linked_request.app.name}. The request remains visible for follow-up.", "warning", "/employee/#requests")

    audit(
        request,
        "agent.result",
        f"{command.action.title()} {result_status} for {machine.name}/{command.app.name}",
        "success" if result_status == Command.STATUS_SUCCEEDED else "error",
        machine=machine,
        metadata={"command_id": str(command.id)},
    )
    return Response({"ok": True})


def notify_user(user, title, message, kind="info", link=""):
    if not user or not getattr(user, "pk", None):
        return None
    return Notification.objects.create(
        user=user,
        title=str(title)[:140],
        message=str(message)[:500],
        kind=kind if kind in {"info", "success", "warning"} else "info",
        link=str(link)[:240],
    )


def notify_staff(title, message, kind="info", link="", exclude_user=None):
    from django.contrib.auth import get_user_model
    qs = get_user_model().objects.filter(is_active=True, is_staff=True)
    if exclude_user and getattr(exclude_user, "pk", None):
        qs = qs.exclude(pk=exclude_user.pk)
    Notification.objects.bulk_create([
        Notification(user=user, title=str(title)[:140], message=str(message)[:500], kind=kind, link=str(link)[:240])
        for user in qs[:50]
    ])


def employee_profile_for(user):
    profile, _ = EmployeeProfile.objects.get_or_create(user=user)
    return profile


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def employee_bootstrap(request):
    if request.user.is_staff:
        return Response({"detail": "Staff accounts use the admin console."}, status=403)
    profile = employee_profile_for(request.user)
    machine = None
    if profile.assigned_machine_id:
        machine = Machine.objects.select_related("network_policy").prefetch_related("installed_apps__app").filter(pk=profile.assigned_machine_id).first()
    software_requests = SoftwareRequest.objects.filter(employee=request.user).select_related(
        "machine", "app", "reviewed_by", "linked_command"
    )[:100]
    tickets = SupportTicket.objects.filter(employee=request.user).select_related(
        "machine", "assigned_to"
    ).prefetch_related("messages__author", Prefetch("messages__attachment", queryset=TicketAttachment.objects.only("id", "message_id", "original_name", "content_type", "size")))[:100]
    notifications = Notification.objects.filter(user=request.user)[:100]
    agent_version = str((machine.system_info or {}).get("agent_version", "")) if machine else ""
    machine_ready = bool(
        machine and machine.online and machine.system_info and machine.metrics_updated_at
        and agent_version.startswith("4.2")
        and ((machine.system_info or {}).get("hostname") or machine.name)
    )
    return Response({
        "profile": EmployeeProfileSerializer(profile).data,
        "machine": EmployeeMachineSerializer(machine).data if machine else None,
        "onboarding": {
            "state": profile.onboarding_state,
            "machine_ready": machine_ready,
            "email_ready": bool((request.user.email or "").strip()),
            "masked_email": _mask_email(request.user.email or ""),
        },
        "apps": _employee_store_apps(machine),
        "software_requests": SoftwareRequestSerializer(software_requests, many=True).data,
        "tickets": SupportTicketSerializer(tickets, many=True).data,
        "notifications": NotificationSerializer(notifications, many=True).data,
    })


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def employee_request_software(request):
    if request.user.is_staff:
        return Response({"detail": "Use the admin console."}, status=403)
    profile = employee_profile_for(request.user)
    if profile.onboarding_state != EmployeeProfile.ONBOARD_ACTIVE:
        return Response({"detail": "Complete PC connection and email verification before using company software requests."}, status=403)
    if not profile.assigned_machine_id:
        return Response({"detail": "No managed computer is assigned to your employee account."}, status=409)
    app_slug = str(request.data.get("app_slug", "")).strip()[:64]
    reason = str(request.data.get("reason", "")).strip()[:1200]
    requested_action = str(request.data.get("action", "install")).strip().lower()
    if requested_action not in {SoftwareRequest.ACTION_INSTALL, SoftwareRequest.ACTION_UPDATE, SoftwareRequest.ACTION_UNINSTALL}:
        return Response({"detail": "Invalid software action."}, status=400)
    try:
        app = AppCatalog.objects.get(slug=app_slug, enabled=True)
    except AppCatalog.DoesNotExist:
        return Response({"detail": "Approved application not found."}, status=404)
    app_policies = _machine_app_policy_map(profile.assigned_machine)
    strict_app_allowlist = bool(app_policies)
    app_policy = app_policies.get(app.pk)
    if strict_app_allowlist and not app_policy:
        return Response({"detail": "This application is not allowed for your assigned PC."}, status=403)
    if app_policy and app_policy.mode == MachineAppPolicy.MODE_BLOCKED:
        return Response({"detail": "This application is blocked by your PC software policy."}, status=403)
    if requested_action == SoftwareRequest.ACTION_UNINSTALL and app_policy and app_policy.mode == MachineAppPolicy.MODE_REQUIRED:
        return Response({"detail": "This application is required by company policy and cannot be removed."}, status=409)

    duplicate = SoftwareRequest.objects.filter(
        employee=request.user,
        machine_id=profile.assigned_machine_id,
        app=app,
        status__in=[SoftwareRequest.STATUS_SUBMITTED, SoftwareRequest.STATUS_QUEUED],
    ).exists()
    if duplicate:
        return Response({"detail": "You already have an active request for this application."}, status=409)
    item = SoftwareRequest.objects.create(
        employee=request.user,
        machine_id=profile.assigned_machine_id,
        app=app,
        action=requested_action,
        reason=reason,
    )
    audit(request, "employee.software_request", f"{request.user.username} requested {requested_action} for {app.name}", "info", machine=profile.assigned_machine)
    notify_staff(
        "New software request",
        f"{request.user.get_full_name() or request.user.username} requested {requested_action} for {app.name} on {profile.assigned_machine.name}.",
        "info",
        "/console/#requests",
    )
    return Response(SoftwareRequestSerializer(item).data, status=201)


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def employee_cancel_software_request(request, request_id):
    if request.user.is_staff:
        return Response({"detail": "Use the admin console."}, status=403)
    profile = employee_profile_for(request.user)
    if profile.onboarding_state != EmployeeProfile.ONBOARD_ACTIVE:
        return Response({"detail": "Complete onboarding first."}, status=403)
    try:
        item = SoftwareRequest.objects.get(pk=request_id, employee=request.user, status=SoftwareRequest.STATUS_SUBMITTED)
    except (SoftwareRequest.DoesNotExist, ValueError):
        return Response({"detail": "Submitted request not found."}, status=404)
    item.status = SoftwareRequest.STATUS_CANCELLED
    item.completed_at = timezone.now()
    item.save(update_fields=["status", "completed_at"])
    audit(request, "employee.software_cancel", f"Software request cancelled: {item.app.name}", "warning", machine=item.machine)
    return Response({"ok": True})


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAdminUser])
def admin_software_request_action(request, request_id):
    decision = str(request.data.get("decision", "")).strip().lower()
    note = str(request.data.get("note", "")).strip()[:1200]
    if decision not in {"approve", "reject"}:
        return Response({"detail": "Decision must be approve or reject."}, status=400)
    with transaction.atomic():
        try:
            item = SoftwareRequest.objects.select_for_update().select_related("employee", "machine", "app").get(pk=request_id)
        except (SoftwareRequest.DoesNotExist, ValueError):
            return Response({"detail": "Software request not found."}, status=404)
        if item.status != SoftwareRequest.STATUS_SUBMITTED:
            return Response({"detail": "This request has already been reviewed."}, status=409)
        item.reviewed_by = request.user
        item.reviewed_at = timezone.now()
        item.admin_note = note
        if decision == "reject":
            item.status = SoftwareRequest.STATUS_REJECTED
            item.completed_at = timezone.now()
            item.save(update_fields=["reviewed_by", "reviewed_at", "admin_note", "status", "completed_at"])
            notify_user(item.employee, "Software request declined", f"{item.app.name}: {note or 'The IT team declined this request.'}", "warning", "/employee/#requests")
            audit(request, "software_request.reject", f"Rejected {item.employee.username}'s request for {item.app.name}", "warning", machine=item.machine)
            return Response(SoftwareRequestSerializer(item).data)

        if item.machine.policy == Machine.POLICY_LOCKED:
            return Response({"detail": "This machine is locked by policy. Change the machine policy before approving software changes."}, status=409)
        app_policy = MachineAppPolicy.objects.filter(machine=item.machine, app=item.app).first()
        if app_policy and app_policy.mode == MachineAppPolicy.MODE_BLOCKED and item.action in {SoftwareRequest.ACTION_INSTALL, SoftwareRequest.ACTION_UPDATE}:
            return Response({"detail": "This application is blocked by the PC software policy."}, status=409)
        if app_policy and app_policy.mode == MachineAppPolicy.MODE_REQUIRED and item.action == SoftwareRequest.ACTION_UNINSTALL:
            return Response({"detail": "This application is required by company policy and cannot be removed."}, status=409)

        installed = InstalledApp.objects.filter(machine=item.machine, app=item.app).first()
        if item.action == SoftwareRequest.ACTION_UNINSTALL:
            if not installed:
                item.status = SoftwareRequest.STATUS_COMPLETED
                item.completed_at = timezone.now()
                item.save(update_fields=["reviewed_by", "reviewed_at", "admin_note", "status", "completed_at"])
                notify_user(item.employee, "Software already removed", f"{item.app.name} is not installed on {item.machine.name}.", "success", "/employee/#software")
                return Response(SoftwareRequestSerializer(item).data)
            action = Command.ACTION_UNINSTALL
        elif item.action == SoftwareRequest.ACTION_UPDATE:
            if not installed:
                return Response({"detail": "The app is not installed, so it cannot be updated. Approve an install request instead."}, status=409)
            if installed.version == item.app.latest_version:
                item.status = SoftwareRequest.STATUS_COMPLETED
                item.completed_at = timezone.now()
                item.save(update_fields=["reviewed_by", "reviewed_at", "admin_note", "status", "completed_at"])
                notify_user(item.employee, "Software already current", f"{item.app.name} is already current on {item.machine.name}.", "success", "/employee/#software")
                return Response(SoftwareRequestSerializer(item).data)
            action = Command.ACTION_UPDATE
        else:
            if installed:
                item.status = SoftwareRequest.STATUS_COMPLETED
                item.completed_at = timezone.now()
                item.save(update_fields=["reviewed_by", "reviewed_at", "admin_note", "status", "completed_at"])
                notify_user(item.employee, "Software already installed", f"{item.app.name} is already installed on {item.machine.name}.", "success", "/employee/#software")
                return Response(SoftwareRequestSerializer(item).data)
            action = Command.ACTION_INSTALL
        deploy_error = _app_deployment_error(item.app, action)
        if deploy_error:
            return Response({"detail": deploy_error}, status=409)
        active = Command.objects.filter(
            machine=item.machine,
            app=item.app,
            action=action,
            status__in=[Command.STATUS_QUEUED, Command.STATUS_RUNNING],
        ).first()
        if active and SoftwareRequest.objects.filter(linked_command=active).exists():
            return Response({"detail": "An employee-linked command for this app is already active."}, status=409)
        command = active or Command.objects.create(
            machine=item.machine,
            app=item.app,
            action=action,
            requested_by=request.user,
        )
        item.linked_command = command
        item.status = SoftwareRequest.STATUS_QUEUED
        item.save(update_fields=["reviewed_by", "reviewed_at", "admin_note", "linked_command", "status"])
        notify_user(item.employee, "Software request approved", f"{item.app.name} has been approved and queued for {item.machine.name}.", "success", "/employee/#requests")
        audit(request, "software_request.approve", f"Approved {item.employee.username}'s request for {item.app.name}", "success", machine=item.machine, metadata={"command_id": str(command.id)})
        return Response(SoftwareRequestSerializer(item).data)


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def employee_create_ticket(request):
    if request.user.is_staff:
        return Response({"detail": "Use the admin console."}, status=403)
    profile = employee_profile_for(request.user)
    if profile.onboarding_state != EmployeeProfile.ONBOARD_ACTIVE:
        return Response({"detail": "Complete onboarding before opening IT tickets."}, status=403)
    category = str(request.data.get("category", "")).strip().lower()
    priority = str(request.data.get("priority", "medium")).strip().lower()
    subject = str(request.data.get("subject", "")).strip()[:180]
    description = str(request.data.get("description", "")).strip()[:5000]
    if category not in {x[0] for x in SupportTicket.CATEGORY_CHOICES}:
        return Response({"detail": "Select a valid issue category."}, status=400)
    if priority not in {x[0] for x in SupportTicket.PRIORITY_CHOICES}:
        return Response({"detail": "Select a valid priority."}, status=400)
    if len(subject) < 4 or len(description) < 8:
        return Response({"detail": "Please provide a clear subject and description."}, status=400)
    ticket = SupportTicket.objects.create(
        employee=request.user,
        machine=profile.assigned_machine,
        category=category,
        priority=priority,
        subject=subject,
        description=description,
    )
    audit(request, "employee.ticket_create", f"Ticket created: {subject}", "info", machine=profile.assigned_machine, metadata={"ticket_id": str(ticket.id)})
    notify_staff(
        "New IT ticket",
        f"{request.user.get_full_name() or request.user.username}: {subject} ({priority}).",
        "warning" if priority in {"high", "critical"} else "info",
        "/console/#tickets",
    )
    return Response(SupportTicketSerializer(ticket).data, status=201)


def _validate_ticket_attachment(upload):
    if not upload:
        return None
    if upload.size > 2 * 1024 * 1024:
        raise ValueError("Screenshot must be 2 MB or smaller.")
    name = upload.name or "attachment"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in {"png", "jpg", "jpeg", "webp"}:
        raise ValueError("Only PNG, JPG/JPEG and WebP screenshots are allowed.")
    try:
        upload.seek(0)
        image = Image.open(upload)
        image.verify()
        if image.format not in {"PNG", "JPEG", "WEBP"}:
            raise ValueError("Unsupported image format.")
        upload._varunops_verified_content_type = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[image.format]
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("The uploaded screenshot is not a valid image.") from exc
    finally:
        upload.seek(0)
    return upload


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def ticket_add_message(request, ticket_id):
    try:
        ticket = SupportTicket.objects.select_related("employee", "assigned_to", "machine").get(pk=ticket_id)
    except (SupportTicket.DoesNotExist, ValueError):
        return Response({"detail": "Ticket not found."}, status=404)
    if not request.user.is_staff and ticket.employee_id != request.user.id:
        return Response({"detail": "You do not have access to this ticket."}, status=403)
    if not request.user.is_staff and employee_profile_for(request.user).onboarding_state != EmployeeProfile.ONBOARD_ACTIVE:
        return Response({"detail": "Complete onboarding first."}, status=403)
    body = str(request.data.get("body", "")).strip()[:4000]
    upload = request.FILES.get("attachment")
    try:
        upload = _validate_ticket_attachment(upload)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=400)
    if not body and not upload:
        return Response({"detail": "Write a message or attach a screenshot."}, status=400)
    message = TicketMessage.objects.create(ticket=ticket, author=request.user, body=body)
    if upload:
        content = upload.read()
        TicketAttachment.objects.create(
            message=message,
            blob=content,
            original_name=(upload.name or "screenshot")[:180],
            content_type=str(getattr(upload, "_varunops_verified_content_type", "application/octet-stream"))[:80],
            size=len(content),
        )
    if request.user.is_staff:
        if not ticket.assigned_to:
            ticket.assigned_to = request.user
            if ticket.status == SupportTicket.STATUS_SUBMITTED:
                ticket.status = SupportTicket.STATUS_ASSIGNED
            ticket.save(update_fields=["assigned_to", "status", "updated_at"])
        notify_user(ticket.employee, "IT replied to your ticket", f"{ticket.subject}: {body[:180] or 'Screenshot attached.'}", "info", f"/employee/#ticket-{ticket.id}")
    else:
        notify_staff("Employee replied to ticket", f"{ticket.employee.get_full_name() or ticket.employee.username}: {ticket.subject}", "info", f"/console/#ticket-{ticket.id}")
    audit(request, "ticket.message", f"Message added to ticket {ticket.id}", "info", machine=ticket.machine, metadata={"ticket_id": str(ticket.id)})
    ticket.refresh_from_db()
    return Response(SupportTicketSerializer(ticket).data, status=201)


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAdminUser])
def admin_ticket_action(request, ticket_id):
    action = str(request.data.get("action", "")).strip().lower()
    allowed = {"assign", "in_progress", "resolved", "closed", "reopen"}
    if action not in allowed:
        return Response({"detail": "Unsupported ticket action."}, status=400)
    try:
        ticket = SupportTicket.objects.select_related("employee", "machine", "assigned_to").get(pk=ticket_id)
    except (SupportTicket.DoesNotExist, ValueError):
        return Response({"detail": "Ticket not found."}, status=404)
    if action == "assign":
        ticket.assigned_to = request.user
        ticket.status = SupportTicket.STATUS_ASSIGNED
    elif action == "in_progress":
        ticket.assigned_to = ticket.assigned_to or request.user
        ticket.status = SupportTicket.STATUS_IN_PROGRESS
    elif action == "resolved":
        ticket.assigned_to = ticket.assigned_to or request.user
        ticket.status = SupportTicket.STATUS_RESOLVED
        ticket.resolved_at = timezone.now()
    elif action == "closed":
        ticket.status = SupportTicket.STATUS_CLOSED
        ticket.resolved_at = ticket.resolved_at or timezone.now()
    elif action == "reopen":
        ticket.assigned_to = ticket.assigned_to or request.user
        ticket.status = SupportTicket.STATUS_IN_PROGRESS
        ticket.resolved_at = None
    ticket.save()
    label = ticket.get_status_display()
    notify_user(ticket.employee, "IT ticket updated", f"{ticket.subject} is now {label}.", "success" if ticket.status in {SupportTicket.STATUS_RESOLVED, SupportTicket.STATUS_CLOSED} else "info", f"/employee/#ticket-{ticket.id}")
    audit(request, "ticket.status", f"Ticket {ticket.id} changed to {ticket.status}", "success", machine=ticket.machine, metadata={"ticket_id": str(ticket.id), "status": ticket.status})
    return Response(SupportTicketSerializer(ticket).data)


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def notification_read(request, notification_id):
    updated = Notification.objects.filter(pk=notification_id, user=request.user).update(is_read=True)
    if not updated:
        return Response({"detail": "Notification not found."}, status=404)
    return Response({"ok": True})


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def notifications_read_all(request):
    updated = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return Response({"updated": updated})


@login_required
@require_GET
def ticket_attachment_download(request, attachment_id):
    try:
        attachment = TicketAttachment.objects.select_related("message__ticket__employee").get(pk=attachment_id)
    except (TicketAttachment.DoesNotExist, ValueError):
        return JsonResponse({"detail": "Attachment not found."}, status=404)
    ticket = attachment.message.ticket
    if not request.user.is_staff and ticket.employee_id != request.user.id:
        return JsonResponse({"detail": "Forbidden."}, status=403)
    if attachment.blob:
        response = HttpResponse(bytes(attachment.blob), content_type=attachment.content_type or "application/octet-stream")
        safe_name = attachment.original_name.replace('"', '')
        response["Content-Disposition"] = f'attachment; filename="{safe_name}"'
    else:
        try:
            handle = attachment.file.open("rb")
        except (FileNotFoundError, ValueError):
            return JsonResponse({"detail": "Attachment file is unavailable."}, status=404)
        response = FileResponse(handle, as_attachment=True, filename=attachment.original_name)
        response["Content-Type"] = attachment.content_type or "application/octet-stream"
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


def _uuid_list(values, limit=500):
    if not isinstance(values, list) or not values or len(values) > limit:
        return None
    try:
        return [uuid.UUID(str(value)) for value in values]
    except (ValueError, TypeError, AttributeError):
        return None


def _clean_sites(values):
    if not isinstance(values, list):
        return []
    out = []
    for raw in values[:300]:
        value = str(raw).strip()
        if not value or len(value) > 240:
            continue
        # Browser policy URL patterns; no commands/scripts are accepted here.
        if any(ch in value for ch in "\r\n\0"):
            continue
        out.append(value)
    return list(dict.fromkeys(out))


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAdminUser])
def admin_machine_app_policy(request):
    machine_ids = _uuid_list(request.data.get("machine_ids", []))
    app_slug = str(request.data.get("app_slug", ""))[:64]
    mode = str(request.data.get("mode", "optional")).lower()
    auto_update = bool(request.data.get("auto_update", True))
    if not machine_ids or mode not in {MachineAppPolicy.MODE_REQUIRED, MachineAppPolicy.MODE_OPTIONAL, MachineAppPolicy.MODE_BLOCKED}:
        return Response({"detail": "Invalid machine selection or app policy."}, status=400)
    try:
        app = AppCatalog.objects.get(slug=app_slug, enabled=True)
    except AppCatalog.DoesNotExist:
        return Response({"detail": "Application not found."}, status=404)
    count = 0
    for machine in Machine.objects.filter(id__in=machine_ids, enabled=True):
        MachineAppPolicy.objects.update_or_create(
            machine=machine, app=app,
            defaults={"mode": mode, "auto_update": auto_update},
        )
        count += 1
    audit(request, "app_policy.assign", f"{app.name} set to {mode} on {count} machine(s)", "success", metadata={"app": app.slug, "mode": mode, "count": count})
    return Response({"updated": count})


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAdminUser])
def admin_compliance_mode(request):
    machine_ids = _uuid_list(request.data.get("machine_ids", []))
    mode = str(request.data.get("mode", "audit")).lower()
    if not machine_ids or mode not in {Machine.COMPLIANCE_AUDIT, Machine.COMPLIANCE_ENFORCE}:
        return Response({"detail": "Invalid compliance mode or machines."}, status=400)
    updated = Machine.objects.filter(id__in=machine_ids, enabled=True).update(compliance_mode=mode)
    audit(request, "compliance.mode", f"Compliance mode {mode} applied to {updated} machine(s)", "success", metadata={"mode": mode, "count": updated})
    return Response({"updated": updated})


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAdminUser])
def admin_agent_mode(request):
    machine_id = request.data.get("machine_id")
    live = bool(request.data.get("live", False))
    try:
        machine = Machine.objects.get(pk=machine_id, enabled=True)
    except (Machine.DoesNotExist, ValueError, TypeError):
        return Response({"detail": "Machine not found."}, status=404)
    machine.agent_live_mode = live
    machine.save(update_fields=["agent_live_mode"])
    audit(request, "agent.mode", f"Agent execution mode set to {'LIVE' if live else 'TEST'} on {machine.name}", "warning" if live else "info", machine=machine)
    return Response({"ok": True, "live": live})


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAdminUser])
def admin_network_policy_save(request):
    policy_id = request.data.get("id")
    name = str(request.data.get("name", "")).strip()[:120]
    mode = str(request.data.get("mode", NetworkPolicy.MODE_BLOCKLIST)).lower()
    if len(name) < 2 or mode not in {NetworkPolicy.MODE_BLOCKLIST, NetworkPolicy.MODE_ALLOWLIST}:
        return Response({"detail": "Provide a policy name and valid mode."}, status=400)
    if policy_id:
        try:
            obj = NetworkPolicy.objects.get(pk=int(policy_id))
        except (NetworkPolicy.DoesNotExist, ValueError, TypeError):
            return Response({"detail": "Network policy not found."}, status=404)
        if NetworkPolicy.objects.exclude(pk=obj.pk).filter(name=name).exists():
            return Response({"detail": "Another network policy already uses this name."}, status=409)
    else:
        if NetworkPolicy.objects.filter(name=name).exists():
            return Response({"detail": "A network policy with this name already exists."}, status=409)
        obj = NetworkPolicy(name=name)
    obj.name = name
    obj.mode = mode
    obj.allowed_sites = _clean_sites(request.data.get("allowed_sites", []))
    obj.blocked_sites = _clean_sites(request.data.get("blocked_sites", []))
    obj.enforce_edge = bool(request.data.get("enforce_edge", True))
    obj.enforce_chrome = bool(request.data.get("enforce_chrome", True))
    obj.enabled = bool(request.data.get("enabled", True))
    obj.revision = 1 if not policy_id else (obj.revision or 0) + 1
    obj.save()
    audit(request, "network_policy.save", f"Saved network policy {obj.name}", "success", metadata={"policy_id": obj.pk, "mode": obj.mode, "revision": obj.revision})
    return Response(NetworkPolicySerializer(obj).data, status=201 if not policy_id else 200)


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAdminUser])
def admin_network_policy_assign(request):
    machine_ids = _uuid_list(request.data.get("machine_ids", []))
    if not machine_ids:
        return Response({"detail": "Select one or more machines."}, status=400)
    policy_id = request.data.get("policy_id")
    policy = None
    if policy_id not in (None, "", 0, "0"):
        try:
            policy = NetworkPolicy.objects.get(pk=int(policy_id), enabled=True)
        except (NetworkPolicy.DoesNotExist, ValueError, TypeError):
            return Response({"detail": "Network policy not found."}, status=404)
    updated = Machine.objects.filter(id__in=machine_ids, enabled=True).update(network_policy=policy)
    audit(request, "network_policy.assign", f"Network policy {policy.name if policy else 'None'} applied to {updated} machine(s)", "success")
    return Response({"updated": updated})


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAdminUser])
def admin_unauthorized_action(request, event_id):
    action = str(request.data.get("action", "")).lower()
    try:
        event = UnauthorizedSoftware.objects.select_related("machine").get(pk=event_id, resolved=False)
    except UnauthorizedSoftware.DoesNotExist:
        return Response({"detail": "Active unauthorized software alert not found."}, status=404)
    if action == "allow":
        values = list(event.machine.software_exceptions or [])
        if event.display_name not in values:
            values.append(event.display_name)
        event.machine.software_exceptions = values[:300]
        event.machine.save(update_fields=["software_exceptions"])
        event.resolved = True
        event.resolution = "Approved exception by IT"
        event.save(update_fields=["resolved", "resolution"])
        audit(request, "compliance.allow_exception", f"Allowed {event.display_name} on {event.machine.name}", "warning", machine=event.machine)
        return Response({"ok": True})
    if action == "uninstall":
        duplicate = AgentTask.objects.filter(machine=event.machine, kind=AgentTask.KIND_UNINSTALL_DETECTED, status__in=[AgentTask.STATUS_QUEUED, AgentTask.STATUS_RUNNING], payload__display_name=event.display_name).exists()
        if not duplicate:
            AgentTask.objects.create(
                machine=event.machine,
                kind=AgentTask.KIND_UNINSTALL_DETECTED,
                payload={"display_name": event.display_name},
                requested_by=request.user,
            )
        event.resolution = "Removal queued by IT"
        event.save(update_fields=["resolution"])
        audit(request, "compliance.remove_queue", f"Queued removal of {event.display_name} from {event.machine.name}", "warning", machine=event.machine)
        return Response({"ok": True})
    return Response({"detail": "Action must be allow or uninstall."}, status=400)


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def employee_create_pairing_code(request):
    if request.user.is_staff:
        return Response({"detail": "Staff accounts do not use employee pairing."}, status=403)
    EmployeeProfile.objects.get_or_create(user=request.user)
    DevicePairingCode.objects.filter(user=request.user, used_at__isnull=True).update(used_at=timezone.now())
    code = f"{secrets.randbelow(100000000):08d}"
    DevicePairingCode.objects.create(
        user=request.user,
        code_hash=make_password(code),
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    return Response({"code": code, "expires_in_seconds": 600})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([AgentEnrollThrottle])
def agent_enroll_with_pairing(request):
    """Enroll a new employee PC using only the short-lived pairing code.

    This removes the need to expose the global IT enrollment token to employees.
    The pairing code is single-use and valid for ten minutes.
    """
    if not isinstance(request.data, dict):
        return Response({"detail": "JSON object required"}, status=400)
    code = str(request.data.get("code", "")).strip()
    if len(code) != 8 or not code.isdigit():
        return Response({"detail": "Invalid pairing code."}, status=400)
    match = None
    for candidate in DevicePairingCode.objects.filter(used_at__isnull=True, expires_at__gt=timezone.now()).select_related("user")[:100]:
        if check_password(code, candidate.code_hash):
            match = candidate
            break
    if not match:
        return Response({"detail": "Pairing code is invalid or expired."}, status=404)
    profile, _ = EmployeeProfile.objects.get_or_create(user=match.user)
    if profile.assigned_machine_id:
        return Response({"detail": "This employee already has a managed PC. IT must reassign it first."}, status=409)

    name = str(request.data.get("name") or "").strip()[:120]
    serial_number = str(request.data.get("serial_number") or "").strip()[:120]
    if not name:
        return Response({"detail": "Device name is required."}, status=400)
    machine = None
    if serial_number:
        machine = Machine.objects.filter(serial_number=serial_number).first()
    if not machine:
        machine = Machine.objects.filter(name=name).first()
    if machine and machine.agent_key_hash:
        return Response({"detail": "This PC is already enrolled. Ask IT to reassign or rotate it."}, status=409)
    if not machine:
        machine = Machine(name=name)

    secret = secrets.token_urlsafe(48)
    machine.branch = str(request.data.get("branch") or profile.branch or "")[:120]
    machine.device_type = str(request.data.get("device_type") or "Desktop")[:40]
    machine.os_version = str(request.data.get("os_version") or "")[:180]
    machine.serial_number = serial_number
    machine.agent_key_hash = make_password(secret)
    machine.agent_key_rotated_at = timezone.now()
    machine.enabled = True
    machine.save()
    profile.assigned_machine = machine
    if not profile.branch:
        profile.branch = machine.branch
    if profile.onboarding_state != EmployeeProfile.ONBOARD_ACTIVE:
        profile.onboarding_state = EmployeeProfile.ONBOARD_VERIFY_EMAIL
    profile.save(update_fields=["assigned_machine", "branch", "onboarding_state", "updated_at"])
    match.used_at = timezone.now()
    match.save(update_fields=["used_at"])
    notify_user(match.user, "Device registered", f"{machine.name} is now connected to your VarunOps account.", "success", "/employee/#device")
    audit(request, "agent.employee_enroll", f"{machine.name} enrolled and paired with {match.user.username}", "success", machine=machine)
    return Response({"agent_id": str(machine.id), "agent_key": secret, "name": machine.name, "employee": match.user.get_full_name() or match.user.username}, status=201)


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAdminUser])
def admin_create_employee(request):
    from django.contrib.auth import get_user_model
    username = str(request.data.get("username", "")).strip().lower()[:150]
    first_name = str(request.data.get("first_name", "")).strip()[:80]
    last_name = str(request.data.get("last_name", "")).strip()[:80]
    email = str(request.data.get("email", "")).strip()[:254]
    employee_code = str(request.data.get("employee_code", "")).strip()[:40]
    department = str(request.data.get("department", "")).strip()[:100]
    branch = str(request.data.get("branch", "")).strip()[:120]
    job_title = str(request.data.get("job_title", "")).strip()[:100]
    if not re.fullmatch(r"[a-z0-9._-]{3,150}", username):
        return Response({"detail": "Username must be at least 3 characters and use letters, numbers, dot, underscore or hyphen."}, status=400)
    if not email or "@" not in email:
        return Response({"detail": "A valid employee email is required for OTP verification and password setup."}, status=400)
    User = get_user_model()
    if User.objects.filter(username=username).exists():
        return Response({"detail": "That username already exists."}, status=409)
    if employee_code and EmployeeProfile.objects.filter(employee_code=employee_code).exists():
        return Response({"detail": "That employee code already exists."}, status=409)
    password = secrets.token_urlsafe(12)
    user = User.objects.create_user(username=username, password=password, email=email, first_name=first_name, last_name=last_name)
    profile = EmployeeProfile.objects.create(
        user=user, employee_code=employee_code or None, department=department, branch=branch, job_title=job_title,
        onboarding_state=EmployeeProfile.ONBOARD_PAIR_DEVICE, temporary_password_issued_at=timezone.now(),
    )
    audit(request, "employee.create", f"Created employee account {username}", "success", metadata={"employee_code": employee_code})
    return Response({"profile": EmployeeProfileSerializer(profile).data, "temporary_password": password}, status=201)


@api_view(["POST"])
@authentication_classes([AgentKeyAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([AgentThrottle])
def agent_pair_employee(request):
    machine = request.auth
    code = str(request.data.get("code", "")).strip()
    if len(code) != 8 or not code.isdigit():
        return Response({"detail": "Invalid pairing code."}, status=400)
    match = None
    for candidate in DevicePairingCode.objects.filter(used_at__isnull=True, expires_at__gt=timezone.now()).select_related("user")[:100]:
        if check_password(code, candidate.code_hash):
            match = candidate
            break
    if not match:
        return Response({"detail": "Pairing code is invalid or expired."}, status=404)
    profile, _ = EmployeeProfile.objects.get_or_create(user=match.user)
    other = EmployeeProfile.objects.filter(assigned_machine=machine).exclude(pk=profile.pk).exists()
    if other:
        return Response({"detail": "This PC is already assigned to another employee. IT must reassign it."}, status=409)
    if profile.assigned_machine_id and profile.assigned_machine_id != machine.pk:
        return Response({"detail": "Your employee account already has another PC assigned. Ask IT to reassign it."}, status=409)
    profile.assigned_machine = machine
    if not profile.branch:
        profile.branch = machine.branch
    profile.save(update_fields=["assigned_machine", "branch", "updated_at"])
    match.used_at = timezone.now()
    match.save(update_fields=["used_at"])
    notify_user(match.user, "Device registered", f"{machine.name} is now linked to your VarunOps account.", "success", "/employee/#device")
    audit(request, "employee.device_pair", f"{machine.name} paired with {match.user.username}", "success", machine=machine)
    return Response({"ok": True, "employee": match.user.get_full_name() or match.user.username})


@api_view(["GET"])
@authentication_classes([AgentKeyAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([AgentThrottle])
def agent_tasks(request):
    machine = request.auth
    if not machine.agent_live_mode:
        return Response({"tasks": [], "test_mode": True})
    now = timezone.now()
    stale_cutoff = now - timedelta(minutes=30)
    for stale in AgentTask.objects.filter(machine=machine, status=AgentTask.STATUS_RUNNING).filter(Q(last_dispatch_at__lt=stale_cutoff) | Q(last_dispatch_at__isnull=True)):
        if stale.attempts >= 3:
            stale.status = AgentTask.STATUS_FAILED
            stale.completed_at = now
            stale.result_message = "Agent did not report a result after three dispatch attempts."
            stale.save(update_fields=["status", "completed_at", "result_message"])
        else:
            stale.status = AgentTask.STATUS_QUEUED
            stale.save(update_fields=["status"])

    rows = list(AgentTask.objects.filter(machine=machine, status=AgentTask.STATUS_QUEUED).order_by("requested_at")[:10])
    payload = []
    for item in rows:
        item.status = AgentTask.STATUS_RUNNING
        item.started_at = item.started_at or now
        item.last_dispatch_at = now
        item.attempts += 1
        item.save(update_fields=["status", "started_at", "last_dispatch_at", "attempts"])
        payload.append({"id": str(item.id), "kind": item.kind, "payload": item.payload})
    return Response({"tasks": payload})


@api_view(["POST"])
@authentication_classes([AgentKeyAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([AgentThrottle])
def agent_task_result(request, task_id):
    machine = request.auth
    try:
        item = AgentTask.objects.get(pk=task_id, machine=machine, status=AgentTask.STATUS_RUNNING)
    except AgentTask.DoesNotExist:
        return Response({"detail": "Running task not found."}, status=404)
    succeeded = str(request.data.get("status", "")).lower() == "succeeded"
    item.status = AgentTask.STATUS_SUCCEEDED if succeeded else AgentTask.STATUS_FAILED
    item.completed_at = timezone.now()
    item.result_message = str(request.data.get("message", ""))[:4000]
    item.save(update_fields=["status", "completed_at", "result_message"])
    if item.kind == AgentTask.KIND_UNINSTALL_DETECTED and succeeded:
        name = str(item.payload.get("display_name", ""))[:180]
        UnauthorizedSoftware.objects.filter(machine=machine, display_name=name, resolved=False).update(resolved=True, resolution="Removed by VarunOps agent")
    audit(request, "agent.task_result", f"{item.kind} {'succeeded' if succeeded else 'failed'} on {machine.name}", "success" if succeeded else "error", machine=machine)
    return Response({"ok": True})


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAdminUser])
def admin_catalog_save(request):
    slug = str(request.data.get("slug", "")).strip().lower()[:64]
    name = str(request.data.get("name", "")).strip()[:100]
    winget_id = str(request.data.get("winget_id", "")).strip()[:120]
    source_type = str(request.data.get("source_type", AppCatalog.SOURCE_WINGET)).strip().lower()
    installer_url = str(request.data.get("installer_url", "")).strip()[:1200]
    installer_sha256 = str(request.data.get("installer_sha256", "")).strip().lower()[:64]
    installer_kind = str(request.data.get("installer_kind", AppCatalog.INSTALLER_EXE)).strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,63}", slug) or len(name) < 2:
        return Response({"detail": "Valid app slug and name are required."}, status=400)
    if source_type not in {AppCatalog.SOURCE_WINGET, AppCatalog.SOURCE_DIRECT}:
        return Response({"detail": "Installer source must be Winget or Direct HTTPS."}, status=400)
    if winget_id and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{1,119}", winget_id):
        return Response({"detail": "Winget package id has an invalid format."}, status=400)
    if installer_kind not in {AppCatalog.INSTALLER_EXE, AppCatalog.INSTALLER_MSI}:
        return Response({"detail": "Installer type must be EXE or MSI."}, status=400)
    if source_type == AppCatalog.SOURCE_WINGET and not winget_id:
        return Response({"detail": "Winget source requires a Winget package ID."}, status=400)
    if source_type == AppCatalog.SOURCE_DIRECT:
        try:
            parsed = urlparse(installer_url)
        except ValueError:
            parsed = None
        if not parsed or parsed.scheme != "https" or not parsed.netloc:
            return Response({"detail": "Direct installers must use a public HTTPS URL."}, status=400)
        if not re.fullmatch(r"[a-f0-9]{64}", installer_sha256):
            return Response({"detail": "Direct installers require the exact 64-character SHA-256 checksum."}, status=400)

    app, created = AppCatalog.objects.get_or_create(slug=slug, defaults={"name": name})
    app.name = name
    app.winget_id = winget_id
    app.source_type = source_type
    app.installer_url = installer_url if source_type == AppCatalog.SOURCE_DIRECT else ""
    app.installer_sha256 = installer_sha256 if source_type == AppCatalog.SOURCE_DIRECT else ""
    app.installer_kind = installer_kind
    app.install_args = _clean_arg_list(request.data.get("install_args", []))
    app.update_args = _clean_arg_list(request.data.get("update_args", []))
    app.homepage_url = str(request.data.get("homepage_url", "")).strip()[:600]
    app.icon_url = str(request.data.get("icon_url", "")).strip()[:600]
    app.latest_version = str(request.data.get("latest_version", ""))[:64]
    app.publisher = str(request.data.get("publisher", ""))[:120]
    app.description = str(request.data.get("description", ""))[:1200]
    app.category = str(request.data.get("category", ""))[:80]
    app.employee_visible = bool(request.data.get("employee_visible", True))
    app.license_required = bool(request.data.get("license_required", False))
    app.license_notes = str(request.data.get("license_notes", ""))[:400]
    app.update_notes = str(request.data.get("update_notes", ""))[:600]
    detection_names = request.data.get("detection_names", [])
    app.detection_names = [str(x)[:180] for x in detection_names[:30]] if isinstance(detection_names, list) else [name]
    app.enabled = bool(request.data.get("enabled", True))
    app.save()
    audit(request, "catalog.save", f"{'Created' if created else 'Updated'} software catalog item {app.name}", "success", metadata={"source_type": app.source_type})
    return Response(AppCatalogSerializer(app).data, status=201 if created else 200)


def _employee_asset_payload(data):
    allowed = [
        "asset_tag", "pin_number", "vendor", "purchase_date", "desk_location",
        "monitor_brand", "monitor_model", "monitor_serial", "screen_size",
        "mouse_brand", "mouse_model", "mouse_serial",
        "keyboard_brand", "keyboard_model", "keyboard_serial",
        "ups_brand", "ups_model", "ups_serial", "notes",
    ]
    out = {}
    for key in allowed:
        value = str(data.get(key, "")).strip()
        out[key] = value[:500 if key == "notes" else 160]
    return out


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def employee_save_asset_details(request):
    if request.user.is_staff:
        return Response({"detail": "Use the admin console."}, status=403)
    profile = employee_profile_for(request.user)
    if not profile.assigned_machine_id:
        return Response({"detail": "Connect your company PC first."}, status=409)
    details = _employee_asset_payload(request.data if isinstance(request.data, dict) else {})
    machine = profile.assigned_machine
    merged = dict(machine.asset_details or {})
    merged.update(details)
    machine.asset_details = merged
    machine.save(update_fields=["asset_details"])
    profile.asset_details = merged
    profile.save(update_fields=["asset_details", "updated_at"])
    audit(request, "employee.asset_details", f"{request.user.username} updated manual asset details", "info", machine=machine)
    return Response({"ok": True, "asset_details": merged})


def _send_transactional_email(recipient, subject, message):
    """Send via Resend HTTPS API on cloud free tiers; fall back to Django email locally/elsewhere."""
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    if api_key:
        payload = json.dumps({
            "from": settings.DEFAULT_FROM_EMAIL,
            "to": [recipient],
            "subject": subject,
            "text": message,
        }).encode("utf-8")
        req = Request(
            "https://api.resend.com/emails",
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "VarunOps/1.0",
            },
        )
        try:
            with urlopen(req, timeout=20) as response:
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(f"Resend returned HTTP {response.status}")
                return True
        except HTTPError as exc:
            detail = ""
            try:
                detail = exc.read(1000).decode("utf-8", errors="replace")
            except Exception:
                pass
            raise RuntimeError(f"Resend HTTP {exc.code}: {detail[:500]}") from exc
        except URLError as exc:
            raise RuntimeError(f"Resend connection failed: {exc.reason}") from exc
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[recipient],
        fail_silently=False,
    )
    return True


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def employee_request_password_otp(request):
    if request.user.is_staff:
        return Response({"detail": "Staff accounts use the admin console."}, status=403)
    profile = employee_profile_for(request.user)
    if not profile.assigned_machine_id:
        return Response({"detail": "Connect your company PC before setting your permanent password."}, status=409)
    machine = profile.assigned_machine
    agent_version = str((machine.system_info or {}).get("agent_version", ""))
    if not machine.online or not machine.system_info or not machine.metrics_updated_at or not agent_version.startswith("4.2"):
        return Response({"detail": "PC is paired but the verified Agent 4.2 inventory/telemetry sync is not complete yet. Run the latest UPDATE_EXISTING_AGENT.bat as Administrator and retry."}, status=409)
    if profile.onboarding_state == EmployeeProfile.ONBOARD_ACTIVE:
        # The same flow is also safe for future password resets.
        pass
    email = (request.user.email or "").strip()
    if not email or "@" not in email:
        return Response({"detail": "Your employee account has no valid email. Ask IT to update it."}, status=409)
    now = timezone.now()
    newest = PasswordResetOTP.objects.filter(user=request.user).order_by("-created_at").first()
    if newest and (now - newest.created_at).total_seconds() < 60:
        return Response({"detail": "Please wait 60 seconds before requesting another OTP."}, status=429)
    recent_count = PasswordResetOTP.objects.filter(user=request.user, created_at__gte=now-timedelta(hours=1)).count()
    if recent_count >= 5:
        return Response({"detail": "Too many OTP requests. Try again later or contact IT."}, status=429)
    PasswordResetOTP.objects.filter(user=request.user, used_at__isnull=True).update(used_at=now)
    code = f"{secrets.randbelow(1000000):06d}"
    otp = PasswordResetOTP.objects.create(
        user=request.user,
        code_hash=make_password(code),
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    try:
        _send_transactional_email(
            email,
            "VarunOps verification code",
            f"Your VarunOps verification code is {code}. It expires in 10 minutes. If you did not request this, contact IT.",
        )
    except Exception as exc:
        otp.delete()
        logger.exception("OTP email failed")
        return Response({"detail": "OTP email could not be sent. IT should verify the SMTP/Resend settings."}, status=502)
    audit(request, "employee.otp_sent", f"Password verification OTP sent for {request.user.username}", "info", machine=profile.assigned_machine)
    payload = {"ok": True, "masked_email": _mask_email(email), "expires_in_seconds": 600}
    if settings.DEBUG and settings.EMAIL_BACKEND.endswith("console.EmailBackend"):
        payload["development_otp"] = code
    return Response(payload)


def _mask_email(email):
    try:
        local, domain = email.split("@", 1)
        show = local[:2] if len(local) > 2 else local[:1]
        return show + "***@" + domain
    except ValueError:
        return "configured email"


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def employee_complete_password_reset(request):
    if request.user.is_staff:
        return Response({"detail": "Staff accounts use the admin console."}, status=403)
    profile = employee_profile_for(request.user)
    if not profile.assigned_machine_id:
        return Response({"detail": "Connect your company PC first."}, status=409)
    code = str(request.data.get("otp", "")).strip()
    new_password = str(request.data.get("new_password", ""))
    confirm_password = str(request.data.get("confirm_password", ""))
    if not re.fullmatch(r"\d{6}", code):
        return Response({"detail": "Enter the 6-digit OTP."}, status=400)
    if new_password != confirm_password:
        return Response({"detail": "Passwords do not match."}, status=400)
    candidates = PasswordResetOTP.objects.filter(
        user=request.user, used_at__isnull=True, expires_at__gt=timezone.now()
    ).order_by("-created_at")[:5]
    otp = None
    for candidate in candidates:
        if candidate.attempts >= 5:
            continue
        if check_password(code, candidate.code_hash):
            otp = candidate
            break
        candidate.attempts += 1
        candidate.save(update_fields=["attempts"])
    if not otp:
        return Response({"detail": "OTP is invalid or expired."}, status=400)
    try:
        validate_password(new_password, user=request.user)
    except ValidationError as exc:
        return Response({"detail": " ".join(exc.messages)}, status=400)
    request.user.set_password(new_password)
    request.user.save(update_fields=["password"])
    update_session_auth_hash(request, request.user)
    now = timezone.now()
    otp.used_at = now
    otp.save(update_fields=["used_at"])
    PasswordResetOTP.objects.filter(user=request.user, used_at__isnull=True).update(used_at=now)
    profile.onboarding_state = EmployeeProfile.ONBOARD_ACTIVE
    profile.email_verified_at = now
    profile.password_changed_at = now
    profile.save(update_fields=["onboarding_state", "email_verified_at", "password_changed_at", "updated_at"])
    notify_user(request.user, "Setup complete", "Your email is verified and your permanent VarunOps password is active.", "success", "/employee/")
    audit(request, "employee.password_set", f"{request.user.username} completed secure onboarding", "success", machine=profile.assigned_machine)
    return Response({"ok": True, "onboarding_state": profile.onboarding_state})


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAdminUser])
def admin_update_employee(request, username):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    try:
        user = User.objects.select_related("employee_profile").get(username=username, is_staff=False)
    except User.DoesNotExist:
        return Response({"detail": "Employee not found."}, status=404)
    profile, _ = EmployeeProfile.objects.get_or_create(user=user)
    email = str(request.data.get("email", user.email or "")).strip()[:254]
    employee_code = str(request.data.get("employee_code", profile.employee_code or "")).strip()[:40]
    if not email or "@" not in email:
        return Response({"detail": "A valid employee email is required for OTP verification."}, status=400)
    if employee_code and EmployeeProfile.objects.filter(employee_code=employee_code).exclude(pk=profile.pk).exists():
        return Response({"detail": "That employee code already exists."}, status=409)
    old_email = user.email
    user.first_name = str(request.data.get("first_name", user.first_name)).strip()[:80]
    user.last_name = str(request.data.get("last_name", user.last_name)).strip()[:80]
    user.email = email
    user.save(update_fields=["first_name", "last_name", "email"])
    profile.employee_code = employee_code or None
    profile.department = str(request.data.get("department", profile.department)).strip()[:100]
    profile.branch = str(request.data.get("branch", profile.branch)).strip()[:120]
    profile.job_title = str(request.data.get("job_title", profile.job_title)).strip()[:100]
    profile.phone = str(request.data.get("phone", profile.phone)).strip()[:30]
    if old_email.casefold() != email.casefold():
        profile.email_verified_at = None
    profile.save(update_fields=["employee_code", "department", "branch", "job_title", "phone", "email_verified_at", "updated_at"])
    audit(request, "employee.update", f"Updated employee account {username}", "info", machine=profile.assigned_machine, metadata={"email_changed": old_email.casefold() != email.casefold()})
    return Response(EmployeeProfileSerializer(profile).data)


def _first(sequence):
    return sequence[0] if isinstance(sequence, list) and sequence else {}


def _fmt_dt(value):
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S") if value else ""


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAdminUser])
def admin_export_asset_csv(request):
    """Export a compact asset register compatible with the user's existing inventory columns."""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="VarunOps_Asset_Inventory.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    columns = [
        "Hostname", "Employee", "Designation", "Branch", "Device Type", "Status", "Last Seen", "Last Sync",
        "IP Address", "MAC Address", "OS", "System Brand", "System Model", "CPU", "CPU Serial",
        "CPU Manufacturer", "Cores", "Threads", "Clock Speed", "Architecture", "Motherboard", "Motherboard Serial",
        "BIOS Serial", "RAM Total", "RAM Modules", "Storage", "Monitor Brand", "Monitor", "Monitor Serial",
        "Screen Size", "Resolution", "Monitor Mfg Date", "Mouse Brand", "Mouse", "Keyboard Brand", "Keyboard",
        "UPS", "Asset Tag", "Vendor", "Purchase Date", "Registered", "Active",
    ]
    writer.writerow(columns)
    profiles = {p.assigned_machine_id: p for p in EmployeeProfile.objects.select_related("user").exclude(assigned_machine_id__isnull=True)}
    for m in Machine.objects.all().order_by("name"):
        info = m.system_info or {}
        asset = m.asset_details or {}
        profile = profiles.get(m.id)
        user = profile.user if profile else None
        net = _first(info.get("network_adapters"))
        monitor = _first(info.get("monitors"))
        mouse = _first(info.get("mouse_devices"))
        keyboard = _first(info.get("keyboard_devices"))
        ram_modules = info.get("memory_modules") or []
        disks = info.get("physical_disks") or []
        ram_text = " | ".join(
            f"{r.get('capacity_gb','?')}GB {r.get('manufacturer','')} {r.get('part_number','')} SN:{r.get('serial','')}".strip()
            for r in ram_modules
        )
        disk_text = " | ".join(
            f"{d.get('model','Disk')} {d.get('size_gb','')}GB SN:{d.get('serial','')} {d.get('media_type','')}".strip()
            for d in disks
        )
        monitor_brand = asset.get("monitor_brand") or monitor.get("manufacturer") or monitor.get("manufacturer_code") or ""
        monitor_model = asset.get("monitor_model") or monitor.get("model") or ""
        monitor_serial = asset.get("monitor_serial") or monitor.get("serial") or ""
        screen_size = asset.get("screen_size") or (f"{monitor.get('diagonal_inches')} inch" if monitor.get("diagonal_inches") else "")
        mfg = ""
        if monitor.get("mfg_year"):
            mfg = str(monitor.get("mfg_year"))
            if monitor.get("mfg_week"):
                mfg += f" W{monitor.get('mfg_week')}"
        writer.writerow([
            m.name,
            (user.get_full_name() or user.username) if user else "",
            profile.job_title if profile else "",
            m.branch or (profile.branch if profile else ""),
            m.device_type,
            "Online" if m.online else "Offline",
            _fmt_dt(m.last_seen),
            _fmt_dt(m.metrics_updated_at),
            m.ip_address or "",
            net.get("mac") or net.get("mac_address") or "",
            info.get("os_caption") or m.os_version or "",
            info.get("manufacturer") or "",
            info.get("model") or "",
            info.get("cpu_name") or info.get("processor") or "",
            info.get("cpu_id") or "",
            info.get("cpu_manufacturer") or "",
            info.get("cpu_cores") or "",
            info.get("cpu_logical_processors") or "",
            (str(info.get("cpu_max_clock_mhz")) + " MHz") if info.get("cpu_max_clock_mhz") else "",
            info.get("os_architecture") or info.get("architecture") or "",
            " ".join(x for x in [info.get("motherboard_manufacturer"), info.get("motherboard_model")] if x),
            info.get("motherboard_serial") or "",
            info.get("bios_serial") or m.serial_number or "",
            (str(info.get("memory_total_gb")) + " GB") if info.get("memory_total_gb") else "",
            ram_text,
            disk_text,
            monitor_brand,
            monitor_model,
            monitor_serial,
            screen_size,
            info.get("resolution") or "",
            mfg,
            asset.get("mouse_brand") or mouse.get("manufacturer") or "",
            asset.get("mouse_model") or mouse.get("name") or "",
            asset.get("keyboard_brand") or keyboard.get("manufacturer") or "",
            asset.get("keyboard_model") or keyboard.get("name") or keyboard.get("description") or "",
            " ".join(x for x in [asset.get("ups_brand"), asset.get("ups_model"), asset.get("ups_serial")] if x),
            asset.get("asset_tag") or "",
            asset.get("vendor") or "",
            asset.get("purchase_date") or "",
            _fmt_dt(m.enrolled_at),
            "Yes" if m.enabled else "No",
        ])
    audit(request, "assets.export", "Exported asset inventory CSV", "info", metadata={"device_count": Machine.objects.count()})
    return response


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAdminUser])
def admin_reissue_temp_password(request, username):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    try:
        user = User.objects.get(username=username, is_staff=False)
    except User.DoesNotExist:
        return Response({"detail": "Employee not found."}, status=404)
    profile, _ = EmployeeProfile.objects.get_or_create(user=user)
    password = secrets.token_urlsafe(12)
    user.set_password(password)
    user.save(update_fields=["password"])
    profile.temporary_password_issued_at = timezone.now()
    profile.onboarding_state = EmployeeProfile.ONBOARD_VERIFY_EMAIL if profile.assigned_machine_id else EmployeeProfile.ONBOARD_PAIR_DEVICE
    profile.save(update_fields=["temporary_password_issued_at", "onboarding_state", "updated_at"])
    audit(request, "employee.temp_password_reissued", f"Reissued temporary password for {username}", "warning", machine=profile.assigned_machine)
    return Response({"username": username, "temporary_password": password, "onboarding_state": profile.onboarding_state})


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAdminUser])
def admin_machine_asset_details(request):
    machine_id = str(request.data.get("machine_id", "")).strip()
    try:
        machine = Machine.objects.get(pk=machine_id)
    except (Machine.DoesNotExist, ValueError):
        return Response({"detail": "Device not found."}, status=404)
    merged = dict(machine.asset_details or {})
    merged.update(_employee_asset_payload(request.data if isinstance(request.data, dict) else {}))
    machine.asset_details = merged
    machine.save(update_fields=["asset_details"])
    profile = EmployeeProfile.objects.filter(assigned_machine=machine).first()
    if profile:
        profile.asset_details = merged
        profile.save(update_fields=["asset_details", "updated_at"])
    audit(request, "device.asset_details", f"IT updated asset details for {machine.name}", "info", machine=machine)
    return Response({"ok": True, "asset_details": merged})


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def employee_update_profile(request):
    if request.user.is_staff:
        return Response({"detail": "Staff accounts use the admin console."}, status=403)
    profile = employee_profile_for(request.user)
    if profile.onboarding_state != EmployeeProfile.ONBOARD_ACTIVE:
        return Response({"detail": "Complete onboarding first."}, status=403)
    request.user.first_name = str(request.data.get("first_name", request.user.first_name)).strip()[:80]
    request.user.last_name = str(request.data.get("last_name", request.user.last_name)).strip()[:80]
    request.user.save(update_fields=["first_name", "last_name"])
    profile.phone = str(request.data.get("phone", profile.phone)).strip()[:30]
    profile.save(update_fields=["phone", "updated_at"])
    audit(request, "employee.profile_update", f"{request.user.username} updated contact profile", "info", machine=profile.assigned_machine)
    return Response(EmployeeProfileSerializer(profile).data)
