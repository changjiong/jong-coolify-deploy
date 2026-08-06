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
| Existing Compose, multiple containers, explicit volumes, sidecars | Service | Repository Compose or raw Compose |
| Standalone database requested as a managed resource | Database | Coolify-managed database |

Prefer the existing project structure. Do not introduce Compose around a single application unless persistence or sidecars require it.

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

## 6. Provision Coolify

For a new deployment:

1. create or select the exact project
2. select/create the environment
3. create an Application or Service
4. set domain/port/healthcheck
5. add environment variables with masked reporting
6. configure explicit persistent volumes
7. deploy only after configuration is complete

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
The bundled client covers health, inventory, Dockerfile applications,
deployment polling, logs, and cleanup. Use a narrowly scoped API request for
other official endpoints rather than SSH or host-level Docker mutation.

## 7. Domain and networking

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

## 8. Deploy and verify

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

## 9. Failure handling

- Build failure: inspect the failed deployment logs before changing code.
- Running but unhealthy: compare healthcheck command with tools available in the runtime image.
- Public URL works but internal alias fails: verify shared network and canonical alias field.
- Domain returns 503: verify DNS, Traefik rule, container port, and network attachment.
- App works but Coolify says unhealthy: prove public/runtime health before changing healthcheck semantics.

Change one cause at a time and rerun the original failing check.

## 10. Completion handoff

Report:

- public URL and final state
- source repository, branch, commit
- Coolify project/environment/resource
- configuration and environment-variable keys changed
- persistence and backup status
- DNS/TLS/health/log/route evidence
- rollback boundary
- unresolved risks and `missing evidence`
