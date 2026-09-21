from django.urls import path
from . import views

urlpatterns = [
    path("health/", views.health, name="health"),

    # Staff console API
    path("bootstrap/", views.bootstrap, name="bootstrap"),
    path("commands/", views.create_commands, name="create_commands"),
    path("commands/<uuid:command_id>/cancel/", views.cancel_command, name="cancel_command"),
    path("policies/assign/", views.assign_policy, name="assign_policy"),
    path("software-requests/<uuid:request_id>/action/", views.admin_software_request_action, name="admin_software_request_action"),
    path("tickets/<uuid:ticket_id>/action/", views.admin_ticket_action, name="admin_ticket_action"),
    path("app-policies/assign/", views.admin_machine_app_policy, name="admin_machine_app_policy"),
    path("compliance/mode/", views.admin_compliance_mode, name="admin_compliance_mode"),
    path("agent-mode/", views.admin_agent_mode, name="admin_agent_mode"),
    path("compliance/unauthorized/<int:event_id>/action/", views.admin_unauthorized_action, name="admin_unauthorized_action"),
    path("network-policies/save/", views.admin_network_policy_save, name="admin_network_policy_save"),
    path("network-policies/assign/", views.admin_network_policy_assign, name="admin_network_policy_assign"),
    path("catalog/save/", views.admin_catalog_save, name="admin_catalog_save"),
    path("employees/create/", views.admin_create_employee, name="admin_create_employee"),

    # Employee portal API
    path("employee/bootstrap/", views.employee_bootstrap, name="employee_bootstrap"),
    path("employee/software-requests/", views.employee_request_software, name="employee_request_software"),
    path("employee/software-requests/<uuid:request_id>/cancel/", views.employee_cancel_software_request, name="employee_cancel_software_request"),
    path("employee/tickets/", views.employee_create_ticket, name="employee_create_ticket"),
    path("employee/device-pairing/", views.employee_create_pairing_code, name="employee_create_pairing_code"),
    path("employee/profile/", views.employee_update_profile, name="employee_update_profile"),
    path("tickets/<uuid:ticket_id>/messages/", views.ticket_add_message, name="ticket_add_message"),
    path("notifications/<int:notification_id>/read/", views.notification_read, name="notification_read"),
    path("notifications/read-all/", views.notifications_read_all, name="notifications_read_all"),
    path("tickets/attachments/<uuid:attachment_id>/", views.ticket_attachment_download, name="ticket_attachment_download"),

    # Windows agent API
    path("agent/enroll/", views.agent_enroll, name="agent_enroll"),
    path("agent/enroll-pairing/", views.agent_enroll_with_pairing, name="agent_enroll_with_pairing"),
    path("agent/manifest/", views.agent_manifest, name="agent_manifest"),
    path("agent/heartbeat/", views.agent_heartbeat, name="agent_heartbeat"),
    path("agent/commands/", views.agent_commands, name="agent_commands"),
    path("agent/commands/<uuid:command_id>/result/", views.agent_command_result, name="agent_command_result"),
    path("agent/pair/", views.agent_pair_employee, name="agent_pair_employee"),
    path("agent/tasks/", views.agent_tasks, name="agent_tasks"),
    path("agent/tasks/<uuid:task_id>/result/", views.agent_task_result, name="agent_task_result"),
]
