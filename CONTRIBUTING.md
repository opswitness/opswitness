# Contributing

Contributions are welcome under the **Developer Certificate of Origin** (DCO).
Sign off each commit (`git commit -s`), which certifies you wrote the code or otherwise
have the right to submit it under Apache-2.0. No CLA.

## Ground rules

- The core stays Apache-2.0, permanently.
- No secrets in the repo, ever — CI runs gitleaks against every commit and the full history.
- Deterministic beats clever: anything computable from available data is code, not an LLM call.
- Fail closed: an approval path that can't reach its backend must deny.

## Dev setup

```bash
pip install -e ".[dev]"
pytest
ruff check .
```
