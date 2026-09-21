import os
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from core.models import (AppCatalog, AuditLog, EmployeeProfile, InstalledApp, Machine, Notification, SoftwareRequest, SupportTicket, TicketMessage, NetworkPolicy, MachineAppPolicy, DeviceMetric, PowerEvent, UnauthorizedSoftware, DetectedSoftware)


class Command(BaseCommand):
    help = "Create demo apps, machines, software inventory, and optional admin user."

    def handle(self, *args, **options):
        apps = [
            ("chrome", "Google Chrome", "140", "Google.Chrome", ["Google Chrome"]),
            ("sevenzip", "7-Zip", "25.01", "7zip.7zip", ["7-Zip"]),
            ("anydesk", "AnyDesk", "9.5", "AnyDeskSoftwareGmbH.AnyDesk", ["AnyDesk"]),
            ("vlc", "VLC media player", "3.0.21", "VideoLAN.VLC", ["VLC media player"]),
            ("notepadpp", "Notepad++", "8.8", "Notepad++.Notepad++", ["Notepad++"]),
        ]
        app_objs = {}
        app_meta = {
            "chrome": ("Google LLC", "Browser", "Company web browser"),
            "sevenzip": ("Igor Pavlov", "Utility", "Archive and extraction utility"),
            "anydesk": ("AnyDesk Software GmbH", "Remote Support", "IT remote support client"),
            "vlc": ("VideoLAN", "Media", "Media playback utility"),
            "notepadpp": ("Notepad++ Team", "Utility", "Text editor for logs and configuration files"),
        }
        for slug, name, version, winget_id, detection in apps:
            publisher, category, description = app_meta[slug]
            app, _ = AppCatalog.objects.update_or_create(slug=slug, defaults={
                "name": name, "latest_version": version, "winget_id": winget_id,
                "detection_names": detection, "publisher": publisher, "category": category,
                "description": description, "employee_visible": True, "enabled": True,
            })
            app_objs[slug] = app

        work_policy, _ = NetworkPolicy.objects.update_or_create(
            name="Clinic Work Only",
            defaults={
                "mode": NetworkPolicy.MODE_ALLOWLIST,
                "allowed_sites": ["https://*.dncc.in/*", "https://mail.google.com/*", "https://accounts.google.com/*"],
                "blocked_sites": [], "enforce_edge": True, "enforce_chrome": True, "enabled": True,
            },
        )

        machines = [
            ("VDN-HO-01", "Vadodara HO", "Desktop", "manual", ["HO", "Finance"]),
            ("PANJIM-PC-02", "Panjim", "Desktop", "automatic", ["Clinic", "Reception"]),
            ("RAJKOT-LT-01", "Rajkot", "Laptop", "automatic", ["Laptop"]),
            ("BORIVALI-SERVER-01", "Borivali", "Server", "locked", ["Server", "Critical"]),
            ("BANDRA-PC-03", "Bandra", "Desktop", "manual", ["Clinic"]),
        ]
        for idx, (name, branch, dtype, policy, tags) in enumerate(machines, start=1):
            m, _ = Machine.objects.update_or_create(name=name, defaults={
                "branch": branch,
                "device_type": dtype,
                "policy": policy,
                "tags": tags,
                "ip_address": f"10.20.{idx}.21",
                "os_version": "Windows 11 Pro",
                "serial_number": f"DEMO-{idx:04d}",
                "last_seen": timezone.now() if name != "BORIVALI-SERVER-01" else timezone.now() - timedelta(minutes=12),
                "compliance_mode": Machine.COMPLIANCE_AUDIT if idx == 1 else Machine.COMPLIANCE_ENFORCE,
                "network_policy": work_policy if idx in {1,2,3,5} else None,
                "last_boot_at": timezone.now() - timedelta(hours=4+idx),
            })
            for slug, app in app_objs.items():
                MachineAppPolicy.objects.update_or_create(
                    machine=m, app=app,
                    defaults={"mode": MachineAppPolicy.MODE_REQUIRED if slug in {"chrome", "sevenzip"} else MachineAppPolicy.MODE_OPTIONAL, "auto_update": True},
                )
            if not DeviceMetric.objects.filter(machine=m).exists():
                DeviceMetric.objects.create(
                    machine=m, cpu_percent=12+idx*4, memory_percent=38+idx*3, memory_used_gb=6+idx/2, memory_total_gb=16,
                    storage_percent=42+idx*2, storage_used_gb=210+idx*10, storage_total_gb=512,
                    storage_volumes=[{"mount": "C:\\", "filesystem": "NTFS", "percent": 42+idx*2, "used_gb": 210+idx*10, "total_gb": 512}],
                    uptime_seconds=(4+idx)*3600,
                )
            PowerEvent.objects.get_or_create(machine=m, event_type=PowerEvent.EVENT_BOOT, occurred_at=m.last_boot_at, defaults={"source_id": "demo"})
            versions = {
                "chrome": "139" if idx in {2, 4} else "140",
                "sevenzip": "24.09" if idx in {3, 5} else "25.01",
                "anydesk": "9.4" if idx == 1 else "9.5",
                "vlc": "3.0.20" if idx in {1, 3} else "3.0.21",
                "notepadpp": "8.7" if idx == 5 else "8.8",
            }
            for slug, version in versions.items():
                InstalledApp.objects.update_or_create(machine=m, app=app_objs[slug], defaults={"version": version})
                DetectedSoftware.objects.update_or_create(
                    machine=m, display_name=app_objs[slug].name,
                    defaults={
                        "version": version, "publisher": app_objs[slug].publisher,
                        "catalog_app": app_objs[slug], "classification": DetectedSoftware.CLASS_CATALOG,
                    },
                )

        demo_machine = Machine.objects.filter(name="VDN-HO-01").first()
        if demo_machine:
            UnauthorizedSoftware.objects.get_or_create(
                machine=demo_machine, display_name="Example Unapproved Toolbar",
                defaults={"version": "1.0", "publisher": "Demo Vendor"},
            )
            DetectedSoftware.objects.update_or_create(
                machine=demo_machine, display_name="Example Unapproved Toolbar",
                defaults={"version": "1.0", "publisher": "Demo Vendor", "classification": DetectedSoftware.CLASS_UNAUTHORIZED},
            )

        if not AuditLog.objects.exists():
            AuditLog.objects.create(event="demo.seed", kind="success", message="Demo workspace initialized")

        # Local employee portal demo account. This is intentionally non-staff and can only access its own records.
        employee_username = os.getenv("DEMO_EMPLOYEE_USERNAME", "varun").strip()
        employee_password = os.getenv("DEMO_EMPLOYEE_PASSWORD", "EmployeeDemo!234")
        employee_email = os.getenv("DEMO_EMPLOYEE_EMAIL", "varun@example.com")
        if employee_username and employee_password:
            User = get_user_model()
            employee, employee_created = User.objects.get_or_create(
                username=employee_username,
                defaults={"email": employee_email, "first_name": "Varun", "last_name": "Machhi", "is_staff": False, "is_superuser": False},
            )
            if employee_created:
                employee.set_password(employee_password)
                employee.save()
            elif employee.is_staff:
                self.stdout.write(self.style.WARNING(
                    f"Skipped demo employee setup because username '{employee_username}' already belongs to a staff account."
                ))
                employee = None
            assigned = None
            if employee:
                profile, _ = EmployeeProfile.objects.update_or_create(
                    user=employee,
                    defaults={
                        "employee_code": "EMP-DEMO-001",
                        "job_title": "IT Support",
                        "department": "IT",
                        "branch": "Vadodara HO",
                        "assigned_machine": None,
                    },
                )
                if not Notification.objects.filter(user=employee).exists():
                    Notification.objects.create(
                        user=employee, kind="success", title="Welcome to VarunOps",
                        message="Your managed device, software requests and IT support tickets are available here.",
                        link="/employee/",
                    )
                if not SupportTicket.objects.filter(employee=employee).exists():
                    ticket = SupportTicket.objects.create(
                        employee=employee, machine=None, category="other", priority="low",
                        subject="Welcome test ticket",
                        description="This demo ticket shows the employee-to-IT support workflow. Pair your real test PC from My PC to start live inventory.",
                    )
                    TicketMessage.objects.create(ticket=ticket, author=employee, body="This is demo data; you can close it from the admin console.")

        username = os.getenv("DEMO_ADMIN_USERNAME", "").strip()
        password = os.getenv("DEMO_ADMIN_PASSWORD", "")
        email = os.getenv("DEMO_ADMIN_EMAIL", "")
        if username and password:
            User = get_user_model()
            user, created = User.objects.get_or_create(username=username, defaults={"email": email, "is_staff": True, "is_superuser": True})
            if created:
                user.set_password(password)
                user.save()
                self.stdout.write(self.style.WARNING("Created demo admin. Change its password before any real deployment."))
        self.stdout.write(self.style.SUCCESS("VarunOps demo data is ready."))
