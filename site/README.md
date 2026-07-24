# OpsWitness public site

This directory is the static source for `opswitness.com`.

The site is intentionally a product, release-status, support-boundary, and feedback surface. It
does not host the OpsWitness console, accept customer work, or impersonate an online SaaS. The full
console continues to run on the operator's own Mac.

The public preview may deploy before the install package exists only when every download CTA is
removed and release status is explicit. A package link may be added only after the inspected Alpha
prerelease exists and passes its blank-install smoke test. Deployment still requires the repository
variable `PUBLIC_SITE_APPROVED=true`.
