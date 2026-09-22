from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from core import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.landing, name="landing"),
    path("workspace/", views.workspace, name="workspace"),
    path("console/", views.console, name="console"),
    path("employee/", views.employee_portal, name="employee_portal"),
    path("employee/agent-package/", views.employee_agent_package, name="employee_agent_package"),
    path("employee/complete-setup/", views.employee_complete_password_reset_form, name="employee_complete_password_reset_form"),
    path("api/", include("core.api_urls")),
]
