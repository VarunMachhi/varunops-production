# VarunOps 4.5.1 Policy Refresh

- Cleans Chrome/Edge URLBlocklist and URLAllowlist from both 64-bit and 32-bit registry views.
- Verifies both registry views before acknowledging an OFF/removed state.
- Uses Chromium's `--refresh-platform-policy` switch in the signed-in user's session after ON/OFF/Edit changes so running Chrome/Edge reload platform policy without a manual `chrome://policy` reload.
- Keeps the 4.5 recovery supervisor/watchdog and fast presence channel.
