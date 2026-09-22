# EnterpriseUX upgrade

1. Replace the GitHub repository files with this package and push.
2. Render: Deploy latest commit. Migration `0008_github_strict_browsing` is applied by the normal startup script.
3. PCs already on Agent 4.4.0+ update automatically from the authenticated VarunOps server. Only legacy pre-4.4 endpoints need the one-time connector bootstrap.
4. Test browsing policy on one non-critical PC before rolling it out broadly.

## Company-only browsing
Create a Website Policy:
- Mode: Allow only selected sites
- Add all required company/login/CDN domains
- Edge: enabled
- Chrome: enabled
- Strict Browsing Lock: enabled
Assign it to one PC first. Edge/Chrome use mandatory URL allow/block policies. Strict Browsing Lock also adds outbound Windows Firewall blocks for common alternative browsers.

This free endpoint mode does not claim to filter every arbitrary network-capable process, VPN, portable/custom browser, or administrator-controlled tunnel. A true all-application/FQDN firewall posture needs Windows Firewall Dynamic Keywords + Defender Network Protection + DoH controls, or a Secure Web Gateway, and should be rolled out only after inventory/testing.

## GitHub Release software source
Use a public GitHub repository and publish your authorized/redistributable EXE/MSI under Releases. Keep a stable asset filename across releases when possible.

In Admin > Software > Add software:
- Source: GitHub Release asset
- Repository: `owner/repository`
- Asset: exact filename, e.g. `CompanyTool-Setup.exe`
- Type: EXE or MSI
- Silent install/update arguments
- Detection names
- Winget ID if available (recommended for safe automatic uninstall)

Use **Check latest GitHub release** before saving. VarunOps resolves the latest published release and uses the release asset download URL. A SHA-256 checksum is mandatory; when GitHub exposes a SHA-256 digest it is filled automatically, otherwise enter the exact checksum manually.

Use **Refresh GitHub** later to sync a newer release. Automatic refresh refuses to change the package when the new release has no SHA-256 digest.


## Agent 4.3.1 PolicyFix
Existing PCs must run the newest UPDATE_EXISTING_AGENT.bat as Administrator. The Admin Policies page now shows endpoint Applied/Pending status. For troubleshooting run CHECK_WEB_POLICY.bat and inspect chrome://policy or edge://policy.


## Agent 4.4.1 Live Policy Control

Online 4.4.1+ endpoints poll the lightweight website-policy state about every 10 seconds. Admin ON/OFF/Edit actions propagate without a client visit and endpoint acknowledgement is stored separately from hardware inventory.
