from rest_framework.throttling import AnonRateThrottle


class AgentEnrollThrottle(AnonRateThrottle):
    scope = "agent_enroll"


class AgentThrottle(AnonRateThrottle):
    scope = "agent"

    def get_cache_key(self, request, view):
        machine = getattr(request, "auth", None)
        if machine is not None:
            return self.cache_format % {"scope": self.scope, "ident": f"machine:{machine.pk}"}
        return super().get_cache_key(request, view)
