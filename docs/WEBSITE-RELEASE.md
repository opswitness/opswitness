# Public website release boundary

`opswitness.com` is the public product, release-status, support-boundary, and feedback surface for
OpsWitness. It does not host the full console, accept customer work, or represent the local
application as a multi-user SaaS. A future browser demo may use synthetic data only.

## Source and hosting

- Static source: `site/`
- Custom domain: `opswitness.com`
- Deployment: GitHub Pages from the pinned `public site` workflow
- Deployment gate: repository variable `PUBLIC_SITE_APPROVED=true`

The public preview may deploy before the Alpha package is available because it exposes no
unverified download. Do not set the approval variable until all of the following are true:

1. the repository is public and Private Vulnerability Reporting is enabled;
2. all public product claims match the current release-candidate boundary;
3. nonexistent package URLs and release-tag URLs are absent;
4. all local assets and feedback routes pass the public-site tests;
5. the DNS records for the Pages host are configured and verified.

The professional confusing-similarity review remains a separate product-release gate. The website
must describe that status honestly and must not imply trademark clearance.

## Public links

The website exposes only these public actions:

- inspect the public source and GitHub Releases status;
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
the absence of a package URL before release, and all feedback routes. After a prerelease exists,
replace the status panel with the exact inspected release download and rerun the same checks.
