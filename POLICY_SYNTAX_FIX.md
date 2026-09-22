# Browser policy syntax fix

This build normalizes existing URLBlocklist/URLAllowlist values during deployment.
Examples:

- `[*.]youtube.com` -> `youtube.com`
- `*.youtube.com` -> `youtube.com`
- `https://youtube.com/*` -> `youtube.com`

It also normalizes policy rules again whenever an endpoint requests its manifest, so older stored records cannot be delivered with invalid Chrome/Edge URLBlocklist syntax.

After deployment, connected agents will receive the corrected policy on their next normal poll. No re-pairing is required.
