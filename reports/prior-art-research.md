# Prior-Art Research

- Researched at: 2026-08-12
- Queries: `Coolify GitHub auto deploy webhook`; `Coolify verify deployment commit SHA`
- Catalogs: skills.sh, SkillsMP, GitHub source, Coolify official API/CLI source
- Candidate families: 28 after catalog deduplication
- Catalog failures: none
- Rating evidence: unavailable
- Metric semantics: skills.sh installs measure ecosystem adoption; GitHub stars measure repository attention; neither is a rating or correctness signal

## Shortlist

| Candidate | Relevance | Adoption/trust signal on 2026-08-12 | Mechanism adopted | Deliberate rejection | License |
| --- | --- | --- | --- | --- | --- |
| Coolify official API and CLI | First-party contract for Application settings, GitHub App sources, deployment history and webhook records | Primary source; `coollabsio/coolify` `v4.x` and official CLI inspected | `is_auto_deploy_enabled`, `PATCH /applications/{uuid}`, `GET /deployments/applications/{uuid}`, full commit and terminal-state verification | No private/internal database or UI mutation | Apache-2.0 for source repository |
| TerminalSkills `coolify` | Most-adopted inspected Coolify candidate and CI/CD contrast | 53 skills.sh installs in the catalog snapshot; repository 128 stars; pushed 2026-07-26 | Explicit deploy API path and token isolation informed the duplicate-trigger threat model | GitHub Actions `/deploy` is not added when native GitHub App webhook is available because two triggers can deploy twice | Apache-2.0 |
| `jonmumm/skills` `deploy-verify` | Specialist in proving the expected deployed version | 23 skills.sh installs in the catalog snapshot; repository 2 stars; pushed 2026-07-30 | Always reconcile the deployed version with the expected commit | Cloudflare/Wrangler commands and fixed wait heuristics | license evidence unavailable |
| Hookdeck `github-webhooks` | Trust anchor for generic GitHub webhook handling | 282 skills.sh installs in the catalog snapshot; repository 80 stars; pushed 2026-08-05 | Confirmed that push delivery and provenance matter | Entire handler/signature implementation rejected: Coolify already owns webhook receipt and signature validation | MIT |

The prior package research remains relevant for end-to-end delivery, Compose,
persistence, DNS/TLS, and rollback. This iteration narrows new research to the
requested automatic redeployment capability.

## Keep / Adapt / Reject / Invent

### Keep

- Coolify GitHub App as the native repository and webhook integration.
- First-party Application update and deployment-history APIs.
- Deployed-version reconciliation from `deploy-verify`.
- Secret isolation and explicit deployment invocation semantics from TerminalSkills.

### Adapt

- Turn generic “verify the deployed version” into an exact evidence tuple:
  deployment ID newer than a captured baseline, full commit SHA match,
  `is_webhook=true`, and `status=finished`.
- Treat `instant_deploy` and continuous auto-deploy as separate controls.
- Route Git-backed Compose requiring auto-deploy to an Application with
  `build_pack=dockercompose`; do not claim the same contract for raw Services.

### Reject

- A second GitHub Actions trigger calling `/api/v1/deploy` when native webhook
  auto-deploy is configured; duplicate triggers can race and deploy twice.
- A custom webhook receiver, signature verifier, queue, or replay service.
- Manual/API redeploy as proof of automatic deployment.
- An old deployment record with the same commit as proof of the current push.
- Empty test commits without explicit user approval.
- Compatibility layers for Applications that are not connected through a
  Coolify GitHub App; configuration stops with a precise prerequisite instead.

### Invent

- `configure-auto-deploy`: exact repository/source/App-installation preflight,
  minimal settings update, read-back verification, and history baseline capture.
- `verify-auto-deploy`: no manual deploy call; it waits for a post-baseline,
  commit-matching webhook deployment and requires successful terminal state.
- Project inspection for an existing Coolify GitHub Actions workflow so the
  operator can resolve a duplicate-trigger risk before enabling native webhook.
- Failure diagnostics for branch mismatch, App repository permission,
  `watch_paths`, GitHub webhook delivery, and `[skip ci]`/`[skip cd]` markers.

## Candidate-Specific Lessons

- Coolify official API/CLI: Application settings are flat API fields; source
  integration is identified through `source_id`; deployment history is stable
  at `/deployments/applications/{uuid}` and records `commit`/`is_webhook`.
  Implemented in `scripts/coolify_api.py` and
  `references/coolify-api-routing.md`.
- TerminalSkills `coolify`: a deploy API workflow is useful when explicitly
  requested, but is a conflicting second trigger in this native webhook job.
  Reflected in duplicate-workflow inspection and safety rules.
- `deploy-verify`: successful HTTP alone does not prove the intended version is
  live. Reflected in full-SHA and deployment-source matching.
- Hookdeck `github-webhooks`: generic handler correctness is valuable when the
  application owns the endpoint, but Coolify owns this endpoint. Rejecting that
  layer keeps the system smaller and avoids handling webhook secrets locally.

## Created Skill Advantages

- **Design advantage:** automatic deployment is a separate verified lifecycle,
  not an alias for `instant_deploy` or manual redeploy.
- **Design advantage:** source preflight, settings mutation, baseline capture,
  GitHub push, deployment provenance, commit reconciliation, and public health
  are distinct gates.
- **Validated advantage:** 30/30 trigger cases pass, including automatic-deploy
  configuration/verification and read-only/explanation boundaries.
- **Validated advantage:** 22 unit tests pass; tests reject manual deployments,
  pre-baseline records, missing GitHub App sources, and failed webhook terminal
  states.
- **Hypothesis:** the post-baseline provenance tuple should reduce false claims
  that auto-deploy works, but a real GitHub push -> Coolify webhook provider run
  remains missing evidence.

## Missing Evidence

- Provider-backed private GitHub App push webhook run for this new workflow
- Comparative A/B outcome against inspected candidate skills
- Human blind review
- Production adoption telemetry
- Public Release and isolated external installation for version 0.3.0
