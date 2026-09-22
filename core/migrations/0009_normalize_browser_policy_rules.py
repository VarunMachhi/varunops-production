from django.db import migrations


def normalize_rule(raw):
    value = str(raw or "").strip()
    if not value or len(value) > 240 or any(ch in value for ch in "\r\n\0"):
        return ""
    if value == "*":
        return value
    if value.startswith("[*.]"):
        value = value[4:]
    elif value.startswith("*."):
        value = value[2:]
    if value.endswith("/*"):
        value = value[:-2]
    for prefix in ("https://", "http://"):
        if value.lower().startswith(prefix):
            rest = value[len(prefix):]
            if "/" not in rest:
                value = rest
            break
    return value.strip().rstrip("/")


def clean(values):
    if not isinstance(values, list):
        return []
    out = []
    for raw in values[:300]:
        value = normalize_rule(raw)
        if value and value not in out:
            out.append(value)
    return out


def forwards(apps, schema_editor):
    NetworkPolicy = apps.get_model("core", "NetworkPolicy")
    for policy in NetworkPolicy.objects.all().iterator():
        allowed = clean(policy.allowed_sites)
        blocked = clean(policy.blocked_sites)
        if allowed != (policy.allowed_sites or []) or blocked != (policy.blocked_sites or []):
            policy.allowed_sites = allowed
            policy.blocked_sites = blocked
            policy.revision = max(1, int(policy.revision or 0) + 1)
            policy.save(update_fields=["allowed_sites", "blocked_sites", "revision", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [("core", "0008_github_strict_browsing")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
