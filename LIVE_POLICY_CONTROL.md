# VarunOps Live Policy Control 4.4.2

- Website-policy endpoint polling: about 5 seconds while the endpoint agent is running.
- ON/OFF/Edit invalidates old acknowledgements immediately.
- URLBlocklist/URLAllowlist registry subkeys are deleted before desired values are written.
- Failed local verification is **not cached**; the endpoint retries on the next fast-policy tick until verified.
- OFF keeps assignments but removes URL lists and VarunOps Strict Browsing firewall rules.
- Delete unassigns the policy; endpoints clear policy on their next control sync.
- Admin policy cards show endpoint-confirmed state, online/offline counts, and whether an endpoint still needs the newer agent.
