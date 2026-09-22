# Live Website Policy Control

Agent version: `4.4.1-livepolicy`

## Admin behavior

Website policies now support:

- ON/OFF toggle without losing PC assignments.
- Edit and push to all PCs already assigned to that policy.
- Delete (unassign + remove the policy).
- Endpoint acknowledgement with `Applying…`, `Applied ✓`, `Removing…`, and `Removed ✓` states.
- A dedicated lightweight policy channel that online endpoints check about every 10 seconds.

Turning a policy OFF keeps its device assignments but sends `policy=null` to those endpoints. The agent removes the Edge/Chrome URL lists and removes Strict Browsing Lock firewall rules, then acknowledges the disabled policy revision.

Turning the same policy ON again keeps those assignments and re-applies the policy automatically.

## Why Admin status is reliable now

Policy acknowledgement is stored in dedicated Machine fields instead of relying only on the large hardware `system_info` JSON payload. This prevents later hardware inventory heartbeats from erasing policy state.

## Offline PCs

Offline PCs remain pending. They apply the latest desired state when they reconnect.

## Existing 4.4.0 endpoints

The bundled 4.4.0 self-update code will discover `4.4.1-livepolicy` through the authenticated manifest and upgrade itself automatically on a normal full poll. No manual client visit is needed for 4.4.0+ endpoints.
