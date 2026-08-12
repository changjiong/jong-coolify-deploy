# Verification

Date: `2026-08-12`

## Local

- Python compilation: passed for all bundled scripts.
- Unit tests: 22 passed, including CLI dispatch, GitHub App source preflight, settings read-back, deployment-history baseline, webhook provenance/commit matching, failed deployment handling, and duplicate CI trigger detection.
- Codex credential reuse: passed against the existing `mcp_servers.coolify.env` configuration without exporting additional environment variables.
- Trigger evaluation: 30/30 passed, 0 false positives, 0 false negatives.
- Package validation: passed with no warnings.
- Secret scan: passed with no findings.
- Install discovery: `npx skills add . --list` found exactly one root skill.
- Local release check: passed with 7 pass, 2 expected warnings, and 0 blocks on
  `feat/github-push-auto-deploy`. The warnings are the intentionally uncommitted
  local worktree and remote clean-install evidence unavailable before publication.
- Current Coolify source contract cross-check: confirmed the GitHub App
  repository-list route and `repositories[].full_name`, the Application
  `is_auto_deploy_enabled` update field, deployment history, and GitHub push
  records carrying the pushed commit with `is_webhook=true`.

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

- Private GitHub App push auto-deploy has contract/unit coverage but no provider run.
- Docker Compose Service path has workflow coverage but no provider run.
- Human blind review and production adoption telemetry are not present.
- Public Release and remote isolated install are release-time gates; this
  pre-release source report does not claim they have completed.
