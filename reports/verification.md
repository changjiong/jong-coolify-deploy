# Verification

Date: `2026-08-06`

## Local

- Python compilation: passed for all bundled scripts.
- Unit tests: 12 passed.
- Trigger evaluation: 23/23 passed, 0 false positives, 0 false negatives.
- Package validation: passed with no warnings.
- Secret scan: passed with no findings.
- Install discovery: `npx skills add . --list` found exactly one root skill.

## Provider

- Coolify API health: passed against a self-hosted Coolify v1 API; the real instance origin is intentionally redacted.
- Server inventory: passed; secret-like server fields were masked.
- Temporary source: minimal Nginx Dockerfile generated under `/tmp`.
- Application creation: passed through `POST /applications/dockerfile`.
- Deployment: `finished`.
- Logs: checked.
- HTTPS certificate: verified.
- HTTP to HTTPS: `302`.
- `/`: `200`.
- `/deep/route`: `200`.
- `/healthz`: `200`, body matched `ok`.
- Cleanup: temporary application deleted by its exact UUID.

Full provider evidence: `reports/provider-smoke.json`.

## Missing Evidence

- Private GitHub App repository path has contract/unit coverage but no provider run.
- Docker Compose Service path has workflow coverage but no provider run.
- Human blind review, production adoption telemetry, and public release/install are not present.
