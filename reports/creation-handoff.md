# Creation Handoff

## Result

- Skill: `jong-coolify-deploy` `0.3.0`
- Job: deploy a local Git repository to self-hosted Coolify and prove that a later GitHub push automatically deployed the exact commit
- Local path: redacted from the public package
- Publication status: governed `v0.3.0` publication approved; Release and
  isolated-install proof are release-time gates and are not pre-claimed here

## Reference Skills Studied

- Coolify official API/CLI source: first-party trust anchor. Confirmed
  Application auto-deploy settings, GitHub App sources, deployment history,
  `commit`, and `is_webhook`; implemented in `scripts/coolify_api.py`.
- TerminalSkills `coolify`: 53 skills.sh installs in the 2026-08-12 catalog
  snapshot; repository 128 stars. Its explicit GitHub Actions deploy API route
  clarified why native webhook and CI triggers must not coexist.
- `jonmumm/skills` `deploy-verify`: 23 skills.sh installs; repository 2 stars.
  Its expected-version check became full-SHA deployment reconciliation.
- Hookdeck `github-webhooks`: 282 skills.sh installs; repository 80 stars. Its
  generic handler was inspected but rejected because Coolify already receives
  and validates GitHub webhooks.

## Absorbed And Rejected

- Keep: native GitHub App integration, typed REST APIs, terminal deployment
  status, and deployed-version reconciliation.
- Adapt: version reconciliation now also requires a post-baseline deployment and
  `is_webhook=true` provenance.
- Reject: duplicate GitHub Actions `/deploy`, custom webhook handlers, manual
  redeploy as proof, old matching records, and unauthorized empty commits.
- Invent: auto-deploy source preflight, settings read-back, deployment-history
  baseline, commit-bound webhook wait, and duplicate workflow detection.

## Advantages And Highlights

- **Design advantage:** `instant_deploy`, manual deploy, and continuous GitHub
  push auto-deploy have separate commands and evidence.
- **Design advantage:** `configure-auto-deploy` updates only branch and
  auto-deploy settings after exact repository/GitHub App access checks.
- **Validated advantage:** 30/30 trigger cases pass with no false positives or
  negatives.
- **Validated advantage:** 22 unit tests pass, including rejection of manual,
  failed, stale, and unbound-source evidence.
- **Validated advantage:** existing provider evidence still proves Dockerfile
  REST deployment, TLS, routes, health, logs, and exact-UUID cleanup.
- **Hypothesis:** the new evidence tuple should prevent false auto-deploy
  completion claims; a live GitHub push provider run remains missing evidence.

## Verification And Limits

- Trigger evaluation: 30/30 passed
- Package validation: passed with no warnings
- Unit tests: 22 passed
- Python compilation: passed
- Skill IR: regenerated for 0.3.0
- Secret scan: passed with no findings
- Local release check: passed with 7 pass, 2 expected warnings, and 0 blocks;
  warnings are the uncommitted local worktree and remote clean-install evidence
  unavailable before publication
- Local install discovery: exactly one root skill found
- Provider-backed Dockerfile deployment: previously passed
- Provider-backed GitHub App push auto-deploy: missing evidence
- Human blind review and production adoption telemetry: missing evidence
- Public publication and remote isolated install: release-time verification
  pending at artifact creation; do not treat this source report as proof
