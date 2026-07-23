# Public website release boundary

`opswitness.com` is the public product, download, installation, support-boundary, and feedback
surface for OpsWitness. It does not host the full console, accept customer work, or represent the
local application as a multi-user SaaS. A future browser demo may use synthetic data only.

## Source and hosting

- Static source: `site/`
- Custom domain: `opswitness.com`
- Deployment: GitHub Pages from the pinned `public site` workflow
- Deployment gate: repository variable `PUBLIC_SITE_APPROVED=true`

The deployment job is intentionally skipped while the repository remains private or the final
Alpha Release is unavailable. Do not set the approval variable until all of the following are true:

1. the professional confusing-similarity review is complete;
2. the repository is public and Private Vulnerability Reporting is enabled;
3. `v0.1.0-alpha.1` exists as an inspected GitHub prerelease;
4. the release wheel passes the final blank-install smoke;
5. the DNS records for the Pages host are configured and verified.

## Public links

The website exposes only these public actions:

- open the GitHub prerelease and Quickstart;
- read the support matrix, known limitations, and security policy;
- submit Alpha experience, feature, and bug reports as GitHub issues;
- open GitHub Private Vulnerability Reporting for security reports.

Do not add API-key collection, hosted planning, login, analytics containing customer content, or a
remote console proxy to this site. The ordinary product continues to bind to the operator's own Mac.

## Verification

Before deployment:

```bash
python -m http.server 8088 --directory site
```

Verify desktop and 390px mobile layouts, keyboard access, local assets, HTTPS-only external links,
the exact release download, and all feedback routes. The repository tests also validate identity,
local asset presence, image alt text, and HTTPS external links.
