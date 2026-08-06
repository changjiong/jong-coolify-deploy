# Creation Handoff

## Result

- Skill: `jong-coolify-deploy` `0.2.1`
- Job: deploy a local Git repository end to end to a verified URL on a self-hosted Coolify VPS
- Local path: redacted from the public package
- Publication status: prepared for `changjiong/jong-coolify-deploy`

## Reference skills studied

- `qiaomu-website-develop`: learned the preflight -> build -> source -> provider -> domain -> HTTPS sequence; adapted in `references/deployment-workflow.md`.
- Coolify official API: confirmed self-hosted instance-domain routing, Bearer authentication, application creation, deployment triggering, deployment status, logs, and deletion endpoints; implemented in `scripts/coolify_api.py`.
- local `coolify-deploy`: learned Application/Service choice, explicit persistence, internal aliases, and status/log verification; adapted across the workflow and API routing.
- `StuMason/coolify-mcp`: learned typed resource hierarchy, list/get economy, and diagnose-before-act; retained as an optional adapter in `references/coolify-api-routing.md`.
- `joshuadavidthomas/agent-skills` `coolify-compose`: learned repository/raw Compose distinctions, editable variables, healthchecks, and Traefik port discipline; implemented in the Service branch.

`Coolify-Manager` was inspected but rejected as a primary anchor because WordPress, CLI installation, raw API fallback, and broad operations dilute the deployment-specific trigger.

## Absorbed and rejected

- Keep: end-to-end delivery, explicit persistence, healthchecks, and verification.
- Adapt: Vercel/Cloudflare delivery becomes GitHub/Coolify REST API/VPS delivery; MCP becomes optional; DNS writes remain exact-hostname scoped.
- Reject: automatic destructive DNS replacement, SSH/host-Docker fallback, host HTTP ports, resource reuse by name, and WordPress-specific workflows.
- Invent: secret-safe API client, `/tmp` provider smoke runner, project inspector, exact resource identity matching, rollback capture, and evidence-bound handoff.

## Advantages and highlights

- **Design advantage:** a single bounded workflow owns source, platform, domain, runtime, and evidence.
- **Design advantage:** the API client reads tokens only from environment variables, never accepts them on the command line, and masks secret-like response fields.
- **Validated advantage:** 23/23 trigger cases pass with zero false positive/negative cases.
- **Validated advantage:** a provider-backed `/tmp` Dockerfile application reached `finished`, passed TLS/routes/health/log checks, and was cleaned up by exact UUID.
- **Hypothesis:** private GitHub App and Compose reliability should improve versus prompt-only workflows, but those provider paths remain `missing evidence`.

## Verification and limits

- Trigger evaluation: passed
- Package validation: passed with no warnings
- Unit tests: 12 passed
- Skill IR: regeneration pending for `0.2.0`
- Secret scan/release check: final rerun pending
- Local install discovery: `npx skills add . --list` found exactly one skill
- Provider-backed deployment: passed for the `/tmp` Dockerfile REST path
- Provider evidence: `reports/provider-smoke.json`
- Human blind review: missing evidence
- Public publication/install: not requested
