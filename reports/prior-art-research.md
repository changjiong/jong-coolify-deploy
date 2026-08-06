# Prior-Art Research

- Researched at: 2026-08-06
- Queries:
  - `coolify deploy local repository self hosted vps`
  - `coolify deployment automation custom domain`
  - `docker compose deploy github self hosted server`
- Catalogs: skills.sh, SkillsMP, GitHub source, local installed skills
- Rating evidence: unavailable
- Catalog metrics: skills.sh installs are adoption telemetry; GitHub stars are repository attention, not quality ratings

## Shortlist

| Candidate | Relevance | skills.sh installs | GitHub stars | Maintenance/trust evidence | Adopt | Reject | License |
| --- | --- | ---: | ---: | --- | --- | --- | --- |
| `qiaomu-website-develop` | End-to-end local repo, GitHub, provider, DNS, HTTPS delivery | missing evidence | 17 | Source inspected; pushed 2026-05-19 | Preflight -> build -> source -> deploy -> domain -> verify | Vercel/Wrangler-specific operations | MIT |
| Coolify official API | First-party REST control plane | official docs | n/a | Primary source | Instance-domain API, Bearer auth, typed resource endpoints, deployment polling | Product-specific payloads stay in references/scripts | official product documentation |
| local `coolify-deploy` | Coolify deployment decisions | local only | n/a | Installed local reference | Application/Service choice, persistence, aliases, completion evidence | Narrow troubleshooting details stay in references | license evidence unavailable |
| `StuMason/coolify-mcp` `coolify` | Exact MCP-first resource hierarchy and tools | 5 | 543 | MIT; pushed 2026-08-05 | MCP-first routing, list/get split, diagnose before act | Broad routine operations are outside this skill trigger | MIT |
| `joshuadavidthomas/agent-skills` `coolify-compose` | Compose conversion and Coolify variables | missing evidence | 38 | MIT; pushed 2026-07-20 | repository/raw Compose distinction, editable variables, no host HTTP ports | Template metadata not required for private app delivery | MIT |

## Inspected but rejected as a primary anchor

`ajmcclary/Coolify-Manager` had 416 skills.sh installs and 13 GitHub stars on 2026-08-06. It contributed the “diagnose before operation” pattern, but its WordPress fixes, Coolify CLI installer, direct API fallback, and broad management scope do not match the local-repo-to-VPS delivery job. GitHub did not expose a detected license, while its README claims MIT; license evidence is therefore incomplete.

## Keep / Adapt / Reject / Invent

### Keep

- End-to-end delivery sequence from `qiaomu-website-develop`.
- Application versus Service and persistence decisions from local `coolify-deploy`.
- resource hierarchy and bounded diagnostics from `coolify-mcp`.
- first-party REST endpoints and Bearer authentication from Coolify official API documentation.
- Compose repository mode, `${VAR}` editability, healthchecks, and Traefik port discipline from `coolify-compose`.

### Adapt

- Replace Vercel/Wrangler provider steps with GitHub + Coolify REST API + self-hosted VPS.
- Replace generic provider verification with Coolify deployment status, logs, runtime health, DNS, TLS, routes, storage, and internal aliases.
- Keep DNS automation optional and exact-hostname scoped.

### Reject

- SSH or host-Docker fallback as a parallel default path.
- WordPress-specific repair rules.
- Automatic deletion of conflicting DNS records.
- Host HTTP port mappings behind Coolify Traefik.
- Resource reuse by similar name.
- Compatibility layers between obsolete and current deployment shapes.

### Invent

- One natural-language deployment contract spanning local source through runtime evidence.
- A local inspector that reports resource shape, quality scripts, dirty paths, remote state, and secret-like tracked filenames without reading values.
- Exact existing-resource identity matching by repo + domain + project/environment.
- Evidence-bound completion and an explicit rollback capture contract.
- An API health/authentication gate with no hidden SSH fallback.
- An optional MCP adapter that must target the same Coolify instance and team.

## Candidate-specific lessons

- `qiaomu-website-develop`: orchestration is easier to trust when each external boundary has a preflight and a final public check. Implemented in `references/deployment-workflow.md`.
- local `coolify-deploy`: persistence and internal aliases must be explicit, not inferred. Implemented in the resource and networking sections.
- Coolify official API: use the user's instance origin, Bearer token, typed endpoints, deployment UUID polling, and bounded logs. Implemented in `scripts/coolify_api.py` and `references/coolify-api-routing.md`.
- `coolify-mcp`: start with summarized reads, diagnose before mutating, and verify after deploy. Retained as an optional adapter in `references/coolify-api-routing.md`.
- `coolify-compose`: repository mode preserves build contexts and files; editable variables require Coolify-aware syntax. Implemented in the Compose branch of the workflow.
- `Coolify-Manager`: broad operations and domain-specific troubleshooting make routing noisy. Its scope was deliberately excluded.

## Created skill advantages

- **Design advantage:** one bounded workflow owns the complete local repo -> GitHub -> Coolify VPS -> verified URL job.
- **Design advantage:** the package separates orchestration, API routing, safety/rollback, deterministic inspection, provider smoke testing, and verification.
- **Validated advantage:** trigger evaluation passes 23/23 recorded trigger cases.
- **Hypothesis:** the inspector and evidence contract should reduce wrong-resource reuse and false completion claims, but provider-backed comparison is missing evidence.

## Missing evidence

- Public user ratings/reviews for candidates
- Provider-backed A/B deployment runs
- Human blind review
- Production adoption telemetry
- Public Release and isolated external installation
