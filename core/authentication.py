import secrets
from django.contrib.auth.hashers import check_password
from rest_framework import authentication, exceptions
from .models import Machine


class AgentPrincipal:
    is_authenticated = True
    is_staff = False
    is_superuser = False

    def __init__(self, machine):
        self.machine = machine
        self.pk = str(machine.pk)
        self.username = f"agent:{machine.name}"


class AgentKeyAuthentication(authentication.BaseAuthentication):
    """Per-device API key auth. Keys are stored only as password hashes server-side."""

    keyword = "AgentKey"

    def authenticate(self, request):
        agent_id = request.headers.get("X-Agent-ID", "").strip()
        agent_key = request.headers.get("X-Agent-Key", "").strip()
        if not agent_id and not agent_key:
            return None
        if not agent_id or not agent_key:
            raise exceptions.AuthenticationFailed("Incomplete agent credentials")
        try:
            machine = Machine.objects.get(pk=agent_id, enabled=True)
        except (Machine.DoesNotExist, ValueError):
            raise exceptions.AuthenticationFailed("Invalid agent credentials")
        if not machine.agent_key_hash or not check_password(agent_key, machine.agent_key_hash):
            # keep failure path deliberately generic
            secrets.compare_digest(agent_key[:1], "x")
            raise exceptions.AuthenticationFailed("Invalid agent credentials")
        return (AgentPrincipal(machine), machine)

    def authenticate_header(self, request):
        return self.keyword
