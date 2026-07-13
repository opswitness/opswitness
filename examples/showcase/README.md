# Synthetic fleet showcase

This fixture uses no credentials, external services, launchd jobs, or user data. It proves
the local contract end to end: wrapped execution, outage backlog, ordered replay,
single-use tool approval evidence, content-addressed artifact eval/signoff, and a split
execution/outcome digest.

```bash
python examples/showcase/run.py --output /tmp/evidence-bridge-showcase
cat /tmp/evidence-bridge-showcase/digest.md
```

`--output` may be omitted; a unique directory is then created under the system temp directory.
That form is suitable for a fixed `qd workflow` registration because every click gets isolated
output without accepting a runtime path from AionUi.

Success requires `outage_pending > 0`, `final_pending = 0`, first gate decision `defer`,
second decision `allow`, `no_repost_projected = 0`, and `digest_healthy = true`.
