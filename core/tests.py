import os
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from core.models import AppCatalog, Machine


@override_settings(AGENT_ENROLLMENT_TOKEN="x" * 40)
class SecurityFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("admin", password="very-strong-test-pass-123", is_staff=True)
        self.client = Client()
        self.app = AppCatalog.objects.create(slug="chrome", name="Chrome", latest_version="140", winget_id="Google.Chrome")

    def test_console_requires_login(self):
        response = self.client.get("/console/")
        self.assertEqual(response.status_code, 302)

    def test_enrollment_rejects_bad_token(self):
        response = self.client.post("/api/agent/enroll/", {"name": "PC-1"}, content_type="application/json", HTTP_X_ENROLLMENT_TOKEN="bad")
        self.assertEqual(response.status_code, 403)

    def test_agent_key_is_not_returned_again(self):
        response = self.client.post("/api/agent/enroll/", {"name": "PC-1"}, content_type="application/json", HTTP_X_ENROLLMENT_TOKEN="x" * 40)
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        machine = Machine.objects.get(name="PC-1")
        self.assertTrue(machine.agent_key_hash)
        self.assertNotIn(payload["agent_key"], machine.agent_key_hash)

    def test_locked_machine_blocks_command(self):
        machine = Machine.objects.create(name="LOCKED", policy=Machine.POLICY_LOCKED)
        self.client.login(username="admin", password="very-strong-test-pass-123")
        response = self.client.post(
            "/api/commands/",
            {"action": "update", "targets": [{"machine_id": str(machine.id), "app_slug": "chrome"}]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 0)

from core.models import Command, EmployeeProfile, SoftwareRequest, SupportTicket


class EmployeePortalSecurityTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user("itadmin", password="very-strong-test-pass-123", is_staff=True)
        self.employee = User.objects.create_user("employee1", password="very-strong-test-pass-123", first_name="Employee")
        self.other = User.objects.create_user("employee2", password="very-strong-test-pass-123")
        self.machine = Machine.objects.create(name="EMP-PC-1", branch="Vadodara HO")
        self.other_machine = Machine.objects.create(name="EMP-PC-2", branch="Rajkot")
        EmployeeProfile.objects.create(user=self.employee, assigned_machine=self.machine, branch="Vadodara HO")
        EmployeeProfile.objects.create(user=self.other, assigned_machine=self.other_machine, branch="Rajkot")
        self.app = AppCatalog.objects.create(slug="sevenzip", name="7-Zip", latest_version="25.01", winget_id="7zip.7zip")

    def test_employee_console_redirects_to_employee_portal(self):
        self.client.login(username="employee1", password="very-strong-test-pass-123")
        response = self.client.get("/console/")
        self.assertRedirects(response, "/employee/")

    def test_employee_request_uses_server_side_assigned_machine(self):
        self.client.login(username="employee1", password="very-strong-test-pass-123")
        response = self.client.post(
            "/api/employee/software-requests/",
            {"app_slug": "sevenzip", "reason": "Required for archives", "machine_id": str(self.other_machine.id)},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        item = SoftwareRequest.objects.get(employee=self.employee)
        self.assertEqual(item.machine, self.machine)

    def test_employee_cannot_review_software_request(self):
        item = SoftwareRequest.objects.create(employee=self.employee, machine=self.machine, app=self.app)
        self.client.login(username="employee1", password="very-strong-test-pass-123")
        response = self.client.post(
            f"/api/software-requests/{item.id}/action/",
            {"decision": "approve"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Command.objects.exists())

    def test_admin_approval_creates_allowlisted_command(self):
        item = SoftwareRequest.objects.create(employee=self.employee, machine=self.machine, app=self.app)
        self.client.login(username="itadmin", password="very-strong-test-pass-123")
        response = self.client.post(
            f"/api/software-requests/{item.id}/action/",
            {"decision": "approve"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.status, SoftwareRequest.STATUS_QUEUED)
        self.assertEqual(item.linked_command.app, self.app)
        self.assertEqual(item.linked_command.machine, self.machine)

    def test_employee_cannot_reply_to_another_employees_ticket(self):
        ticket = SupportTicket.objects.create(
            employee=self.other, machine=self.other_machine, category="network", priority="medium",
            subject="Other employee ticket", description="This belongs to another employee.",
        )
        self.client.login(username="employee1", password="very-strong-test-pass-123")
        response = self.client.post(
            f"/api/tickets/{ticket.id}/messages/",
            {"body": "Should not work"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

from core.models import MachineAppPolicy


class EnterprisePolicyTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user("enterpriseadmin", password="very-strong-test-pass-123", is_staff=True)
        self.employee = User.objects.create_user("enterpriseemployee", password="very-strong-test-pass-123")
        self.machine = Machine.objects.create(name="POLICY-PC-1", branch="Vadodara HO")
        EmployeeProfile.objects.create(user=self.employee, assigned_machine=self.machine, branch="Vadodara HO")
        self.allowed = AppCatalog.objects.create(slug="allowed-app", name="Allowed App", latest_version="1", winget_id="Vendor.Allowed", employee_visible=True)
        self.required = AppCatalog.objects.create(slug="required-app", name="Required App", latest_version="1", winget_id="Vendor.Required", employee_visible=True)
        self.blocked = AppCatalog.objects.create(slug="blocked-app", name="Blocked App", latest_version="1", winget_id="Vendor.Blocked", employee_visible=True)
        self.hidden = AppCatalog.objects.create(slug="hidden-app", name="Hidden App", latest_version="1", winget_id="Vendor.Hidden", employee_visible=False)
        MachineAppPolicy.objects.create(machine=self.machine, app=self.allowed, mode=MachineAppPolicy.MODE_OPTIONAL)
        MachineAppPolicy.objects.create(machine=self.machine, app=self.required, mode=MachineAppPolicy.MODE_REQUIRED)
        MachineAppPolicy.objects.create(machine=self.machine, app=self.blocked, mode=MachineAppPolicy.MODE_BLOCKED)

    def test_employee_store_is_per_machine_allowlist(self):
        self.client.login(username="enterpriseemployee", password="very-strong-test-pass-123")
        response = self.client.get("/api/employee/bootstrap/")
        self.assertEqual(response.status_code, 200)
        slugs = {item["slug"] for item in response.json()["apps"]}
        self.assertIn("allowed-app", slugs)
        self.assertIn("required-app", slugs)
        self.assertNotIn("blocked-app", slugs)
        self.assertNotIn("hidden-app", slugs)

    def test_employee_cannot_request_blocked_app(self):
        self.client.login(username="enterpriseemployee", password="very-strong-test-pass-123")
        response = self.client.post(
            "/api/employee/software-requests/",
            {"app_slug": "blocked-app", "action": "install", "reason": "test"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_employee_cannot_request_required_app_uninstall(self):
        self.client.login(username="enterpriseemployee", password="very-strong-test-pass-123")
        response = self.client.post(
            "/api/employee/software-requests/",
            {"app_slug": "required-app", "action": "uninstall", "reason": "test"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)

    def test_admin_command_respects_app_policy(self):
        self.client.login(username="enterpriseadmin", password="very-strong-test-pass-123")
        response = self.client.post(
            "/api/commands/",
            {"action": "install", "targets": [{"machine_id": str(self.machine.id), "app_slug": "blocked-app"}]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 0)
        self.assertFalse(Command.objects.filter(machine=self.machine, app=self.blocked).exists())

        response = self.client.post(
            "/api/commands/",
            {"action": "uninstall", "targets": [{"machine_id": str(self.machine.id), "app_slug": "required-app"}]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 0)
        self.assertFalse(Command.objects.filter(machine=self.machine, app=self.required).exists())
