# End-to-End Deployment Workflow

This is the execution reference for a local repository to a self-hosted Coolify VPS.

## 1. Resolve the target

Collect or infer:

- local project directory
- desired public domain
- Coolify instance origin, normally `https://coolify.example.com`
- Coolify server and environment, normally `production`
- project/application name
- GitHub owner/repository and desired visibility
- source branch and whether every push should auto-deploy
- whether DNS can be changed automatically

If a requested domain or resource already belongs to another repository or environment, stop and surface the conflict.

## 2. Inspect without mutation

Run:

```bash
python3 scripts/inspect_project.py /path/to/project --pretty
git status --short --branch
gh auth status
```

Configure the user's Coolify origin and token outside the repository:

```bash
export COOLIFY_BASE_URL=https://coolify.example.com
export COOLIFY_API_TOKEN=...
python3 scripts/coolify_api.py health
```

Then inspect Coolify through its REST API:

1. API health
2. projects and environments
3. servers and destinations
4. applications/services/databases
5. exact resource details only for matching candidates

Coolify MCP may be used as an optional typed adapter when it targets the same
instance and team. It is not a prerequisite for deployment.

Do not infer the VPS from local Docker. Compare server identity before using any host-level Docker command.

## 3. Select the deployment shape

| Project shape | Coolify resource | Source |
| --- | --- | --- |
| Single runtime container, Dockerfile, Nixpacks app, static site | Application | GitHub repository, Dockerfile, or image |
| Git-backed Compose that must auto-deploy on push | Application (`dockercompose`) | GitHub repository |
| Raw Compose, one-click stack, or Service-managed lifecycle | Service | Raw Compose or Service repository source |
| Standalone database requested as a managed resource | Database | Coolify-managed database |

Prefer the existing project structure. Do not introduce Compose around a single application unless persistence or sidecars require it.

Native GitHub push auto-deploy in this skill is an Application contract. Do not
represent a raw Compose Service as having the same branch/webhook/deployment-history
evidence unless the running Coolify version exposes and verifies an equivalent
Service contract.

### Repository mode versus raw Compose

- Keep `build:` and external relative files only in repository mode.
- Raw Compose should use images and inline `content:` where required.
- Use `${VAR}` or `${VAR:-default}` for values that should appear in the Coolify UI.
- Do not expose HTTP services with host `ports:` when Traefik should route them.

## 4. Prepare the repository

Use existing dependency and build conventions:

- run project-defined test, lint, typecheck, and build scripts
- add only the missing production entrypoint
- add a real health endpoint or image-supported healthcheck
- preserve unrelated dirty files
- never stage `.env`, keys, credentials, database dumps, or generated secrets

For SPAs behind Nginx, configure deep-route fallback to `index.html`. For build-time frontend variables, mark them as build-time in Coolify; runtime-only variables cannot change an already-built static bundle.

## 5. Publish source

If `origin` exists, verify it is the intended repository. If no remote exists and source publication is authorized:

1. default to a private GitHub repository
2. add `origin`
3. commit only deployment-related files
4. push the current intended branch
5. verify the remote commit

Do not amend, force-push, rewrite history, or include unrelated changes.
Resolve and retain the full remote SHA with `git rev-parse HEAD`; short SHAs are
not sufficient for automatic-deployment verification.

## 6. Provision Coolify

For a new deployment:

1. create or select the exact project
2. select/create the environment
3. create an Application or Service
4. set domain/port/healthcheck
5. add environment variables with masked reporting
6. configure explicit persistent volumes
7. deploy only after configuration is complete
8. for a GitHub-backed Application, enable native push auto-deploy explicitly

For an existing deployment, capture:

- current resource UUID and status
- repository/branch or image
- current deployed commit/deployment
- domain and exposed port
- current Compose text when updating a Service
- environment-variable keys; values remain secret

Never reuse a resource only because its name looks similar.

Use the dedicated Coolify API endpoint matching the source: public Git,
private GitHub App, deploy key, Dockerfile, Docker image, or Docker Compose.
The bundled client covers health, inventory, Dockerfile/GitHub Applications,
auto-deploy preflight and configuration, deployment history/polling, logs, and
cleanup. Use a narrowly scoped API request for other official endpoints rather
than SSH or host-level Docker mutation.

## 7. Verify GitHub push auto-deploy

Use Coolify's GitHub App webhook as the single trigger. Do not create a GitHub
Actions workflow or store another Coolify API token when native integration is
available.

1. Confirm the Application repository and target branch match the intended remote.
2. Inspect `.github/workflows` for an existing Coolify deploy trigger. Do not leave native webhook and CI deploy enabled together.
3. Confirm `source_id` resolves to an accessible Coolify GitHub App.
4. Confirm that GitHub App installation can enumerate the exact repository.
5. Enable `is_auto_deploy_enabled=true` and set the target `git_branch`.
6. Record `verification_baseline_id` before the test push.
7. Push a new task-scoped commit to the configured branch.
8. Resolve the full remote commit SHA.
9. Wait for a deployment with all of these properties:
   - deployment `id` is greater than the captured baseline
   - `commit` equals the pushed full SHA
   - `is_webhook=true`
   - terminal `status=finished`
10. Check the deployment log and public URL independently.

```bash
python3 scripts/coolify_api.py configure-auto-deploy APP_UUID \
  --repository https://github.com/OWNER/REPO \
  --branch main

# Push a real scoped commit after recording verification_baseline_id.
git push origin main

python3 scripts/coolify_api.py verify-auto-deploy APP_UUID \
  --repository https://github.com/OWNER/REPO \
  --branch main \
  --commit FULL_REMOTE_SHA \
  --after-id VERIFICATION_BASELINE_ID
```

The verification command never calls `/deploy`. A manual/API deployment with
the same commit cannot satisfy the `is_webhook=true` and newer-ID requirements.
Do not create an empty commit solely for testing unless the user explicitly
authorizes it; use the next real task-scoped source commit.

## 8. Domain and networking

Applications:

- set `fqdn`
- expose the container HTTP port
- use `custom_network_aliases` for internal callers

Services:

- attach the proxied service to the Coolify network
- configure Traefik labels or Coolify service URL variables
- set the load-balancer server port to the container port
- avoid host HTTP port mappings

DNS:

- verify authoritative A/AAAA/CNAME records
- create only the exact requested hostname when provider credentials are available
- do not delete conflicting records without confirmation
- otherwise report the exact record required

## 9. Deploy and verify

Wait for a terminal deployment status. Then check:

1. Coolify resource status
2. deployment status and log tail
3. application logs when runtime errors are possible
4. DNS target
5. HTTP to HTTPS redirect
6. TLS validation
7. health endpoint
8. root and representative deep routes
9. static cache headers when relevant
10. internal alias from the caller network when relevant
11. persistent storage list and backup implications

Use:

```bash
python3 scripts/verify_deployment.py \
  --url https://app.example.com \
  --health-path /healthz \
  --path / \
  --check-http-redirect
```

For a disposable provider-backed smoke test, create the minimal Dockerfile
under `/tmp`, deploy it through the same Coolify API, verify it, and remove the
exact application UUID:

```bash
python3 scripts/smoke_deploy.py \
  --project-uuid PROJECT_UUID \
  --server-uuid SERVER_UUID \
  --domain https://smoke.example.com
```

## 10. Failure handling

- Build failure: inspect the failed deployment logs before changing code.
- Running but unhealthy: compare healthcheck command with tools available in the runtime image.
- Public URL works but internal alias fails: verify shared network and canonical alias field.
- Domain returns 503: verify DNS, Traefik rule, container port, and network attachment.
- App works but Coolify says unhealthy: prove public/runtime health before changing healthcheck semantics.
- No webhook deployment appears: check GitHub App installation/repository access, configured branch, GitHub webhook delivery, `watch_paths`, and `[skip ci]`/`[skip cd]` commit markers.
- A deployment appears but `is_webhook=false`: it was manually/API triggered and does not prove automatic redeployment.
- Commit mismatch: do not accept the deployment; verify the pushed remote SHA and the Application branch.
- Webhook deployment fails: inspect that exact deployment UUID and keep auto-deploy configured; do not hide the failure with a manual redeploy.

Change one cause at a time and rerun the original failing check.

## 11. Completion handoff

Report:

- public URL and final state
- source repository, branch, commit
- auto-deploy enabled state, verification baseline, webhook deployment UUID, source flag, and exact commit match
- Coolify project/environment/resource
- configuration and environment-variable keys changed
- persistence and backup status
- DNS/TLS/health/log/route evidence
- rollback boundary
- unresolved risks and `missing evidence`
