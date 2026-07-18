# Private HTTPS, device pairing, and PWA

Quarterdeck stays loopback-only unless `console.exposure: private` is explicitly configured.
Private mode has two independent gates:

1. the browser connection must be effective HTTPS on the exact configured host; and
2. the browser must hold a live, revocable Quarterdeck device credential.

A tailnet/LAN connection alone is never authentication. AionUi, Paperclip, and provider CLIs keep
their loopback addresses in both modes.

## Recommended: Tailscale Serve

Tailscale Serve keeps Quarterdeck bound to `127.0.0.1`, provisions browser-trusted HTTPS, and
persists its background proxy across restarts. It is private to the tailnet; do not substitute
Tailscale Funnel, which is public internet exposure.

Configure `config.yaml` with the MagicDNS FQDN shown by Tailscale:

```yaml
console:
  exposure: private
  private_transport: trusted_loopback_proxy
  host: 127.0.0.1
  port: 8765
  public_host: quarterdeck.example-tailnet.ts.net
  public_port: 443
```

Start/restart Quarterdeck, then configure the private reverse proxy:

```bash
tailscale serve --bg --https=443 http://127.0.0.1:8765
tailscale serve status --json
```

The human-readable status must say `tailnet only`. To remove the private route without exposing a
replacement, run:

```bash
tailscale serve --https=443 off
```

Quarterdeck accepts the proxy's `X-Forwarded-Proto: https` only when the TCP peer is loopback and
the request Host exactly equals `public_host`. Direct LAN callers cannot spoof that boundary.

## Alternative: direct TLS

Direct mode binds Quarterdeck to a private IP or wildcard and requires a matching SAN certificate.
The private key must be a regular, non-symlink file with no group/world permissions. Startup loads
the certificate/key pair, rejects expired or not-yet-valid certificates, and verifies the exact
configured DNS/IP SAN before opening the listener.

```yaml
console:
  exposure: private
  private_transport: direct_tls
  host: 100.100.101.102
  port: 8765
  public_host: quarterdeck.example-tailnet.ts.net
  tls_certfile: /Users/you/.config/quarterdeck/tls/quarterdeck.crt
  tls_keyfile: /Users/you/.config/quarterdeck/tls/quarterdeck.key
```

Tailscale can issue the files, but file-based certificates require renewal:

```bash
tailscale cert \
  --cert-file=/Users/you/.config/quarterdeck/tls/quarterdeck.crt \
  --key-file=/Users/you/.config/quarterdeck/tls/quarterdeck.key \
  quarterdeck.example-tailnet.ts.net
chmod 600 /Users/you/.config/quarterdeck/tls/quarterdeck.key
```

## Pair and revoke devices

Create the first short-lived code locally:

```bash
qd console pair
```

Open the printed HTTPS `/pair` URL on the device and enter the code. The code is single-use. The
browser receives a `Secure`, `HttpOnly`, `SameSite=Strict` cookie; disk stores only its SHA-256
hash. Additional invitations and revocation are available in **Settings > Device access** or via:

```bash
qd console devices
qd console revoke DEVICE_ID --yes
```

Revocation blocks the next request. Cached PWA files cannot bypass it because the service worker
never handles `/api/` traffic.

## Safari and Chrome

The same HTTPS URL works in Safari and Chrome while the device is on the private network. The web
manifest uses standalone display mode and includes 192, 512, maskable, and Apple touch PNG icons.
The service worker caches only the static application shell and offline notice. It never caches
tasks, plans, approvals, mail summaries, evidence, API errors, or device credentials.

On iPhone, connect Tailscale first, open the HTTPS URL in Safari or Chrome, pair the browser, then
use the browser's **Add to Home Screen** action when a standalone app icon is desired. Pairing is
per browser profile; revoking one device does not revoke another.

Reference: [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve),
[Tailscale HTTPS certificates](https://tailscale.com/docs/how-to/set-up-https-certificates), and
[WebKit web app support](https://webkit.org/blog/17333/webkit-features-in-safari-26-0/).
