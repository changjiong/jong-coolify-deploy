# Coolify API Routing

Use the Coolify v1 REST API as the default remote control plane. The user's
instance domain replaces the example origin:

```bash
export COOLIFY_BASE_URL=https://coolify.example.com
export COOLIFY_API_TOKEN=...
python3 scripts/coolify_api.py health
```

The bundled client appends `/api/v1`, sends `Authorization: Bearer`, masks
secret-like response fields, Base64-encodes Dockerfile content as required by
Coolify, and never accepts the token as a command-line argument.

## Availability gate

1. Confirm `COOLIFY_BASE_URL` is the exact self-hosted Coolify origin.
2. Load `COOLIFY_API_TOKEN` or `COOLIFY_ACCESS_TOKEN` from the environment.
3. Run `coolify_api.py health`.
4. List servers, projects, environments, and applications before any write.
5. Match the target by repository, domain, project, and environment.

If the API is unavailable, stop remote writes. Coolify MCP may be used as an
optional typed adapter only when it targets the same instance and team. Do not
silently downgrade to SSH or direct Docker mutations on the VPS.

## Read sequence

```bash
python3 scripts/coolify_api.py list-servers
python3 scripts/coolify_api.py list-projects
python3 scripts/coolify_api.py list-applications
python3 scripts/coolify_api.py get-application APP_UUID
python3 scripts/coolify_api.py list-deployments APP_UUID --take 25
```

Fetch detailed data only for exact candidates. Do not dump complete application
objects into the final report; report names, short UUIDs, masked variable keys,
source, domains, status, and health.

## Application writes

Coolify exposes dedicated application create endpoints for public Git
repositories, private GitHub App repositories, deploy-key repositories,
Dockerfiles, Docker images, and Docker Compose.

Use the endpoint matching the real source. Do not convert a private repository
to public merely to simplify deployment.

For a private repository connected through a Coolify GitHub App:

```bash
python3 scripts/coolify_api.py list-github-apps
python3 scripts/coolify_api.py create-github \
  --project-uuid PROJECT_UUID \
  --server-uuid SERVER_UUID \
  --github-app-uuid GITHUB_APP_UUID \
  --name app-name \
  --repository https://github.com/OWNER/REPO \
  --branch main \
  --build-pack dockerfile \
  --dockerfile-location /Dockerfile \
  --port 80 \
  --domain https://app.example.com
```

Use `create-public` with the same source/build arguments for a genuinely public
repository.

GitHub App repository Applications created by `create-github` enable
`is_auto_deploy_enabled` by default. Pass `--no-auto-deploy` only when the user
explicitly wants manual deployments. `instant_deploy` remains a separate flag:
it controls the first deployment during creation and does not listen for later
pushes.

For a minimal Dockerfile application:

```bash
python3 scripts/coolify_api.py create-dockerfile \
  --project-uuid PROJECT_UUID \
  --server-uuid SERVER_UUID \
  --environment-name production \
  --name app-name \
  --dockerfile Dockerfile \
  --domain https://app.example.com
```

Then deploy and wait:

```bash
python3 scripts/coolify_api.py deploy APP_UUID --wait
```

## GitHub push auto-deploy

For an existing GitHub-backed Application, configure the native webhook path:

```bash
python3 scripts/coolify_api.py configure-auto-deploy APP_UUID \
  --repository https://github.com/OWNER/REPO \
  --branch main
```

The command performs read-only preflight before `PATCH /applications/{uuid}`:

- exact repository match
- Application has a Coolify GitHub App `source_id`
- source ID matches an accessible GitHub App
- the App installation can enumerate the exact repository

It updates only `git_branch` and `is_auto_deploy_enabled`, reads the Application
back, and returns `verification_baseline_id`, the greatest existing deployment
ID. It does not push code.

After pushing a new real commit, verify the automatic trigger:

```bash
python3 scripts/coolify_api.py verify-auto-deploy APP_UUID \
  --repository https://github.com/OWNER/REPO \
  --branch main \
  --commit FULL_REMOTE_SHA \
  --after-id VERIFICATION_BASELINE_ID \
  --wait-timeout 600
```

The client polls `GET /deployments/applications/{uuid}`, selects only a record
newer than the baseline with exact `commit` and `is_webhook=true`, then polls
`GET /deployments/{deployment_uuid}` to a terminal state. Only `finished`
passes. Manual/API deployments are rejected as evidence even if their commit
matches.

Do not pair this native path with a GitHub Actions call to `/deploy`; two
triggers can enqueue duplicate deployments. If the Application is not connected
through a Coolify GitHub App, stop and report that integration as a prerequisite
instead of silently installing a second token-bearing workflow.

## Environment variables

Use the application or service environment-variable endpoints. Prefer bulk
updates from a local JSON file or a secret manager rather than `KEY=value`
command-line arguments, which can leak through shell history or process lists.

```bash
python3 scripts/coolify_api.py apply-env-file APP_UUID --file /secure/path/env.json
python3 scripts/coolify_api.py list-envs APP_UUID
```

The JSON file is an array accepted by Coolify's bulk environment endpoint:

```json
[
  {
    "key": "APP_ENV",
    "value": "production",
    "is_build_time": false,
    "is_preview": false,
    "is_literal": true
  }
]
```

Rules:

- values remain outside Git and reports
- report keys only
- set build-time flags only for variables consumed during image build
- preserve literal-variable semantics when Coolify should not interpolate a value
- verify required keys after the update without revealing values

## Services and Compose

Use Coolify Service APIs for multi-container Compose stacks. Keep editable
values as `${VAR}` or `${VAR:-default}` and define named volumes explicitly.
Do not publish HTTP services through host `ports:` when Coolify Traefik should
route them.

## Deployment and logs

1. Configure the resource completely.
2. For an initial/manual deployment, trigger `GET /deploy?uuid=RESOURCE_UUID`.
3. Extract `deployment_uuid`.
4. Poll `GET /deployments/{deployment_uuid}` to a terminal state.
5. Read a bounded application/deployment log tail.
6. Verify the public URL independently.

For automatic deployment verification, do not execute step 2. Capture the
history baseline before a real GitHub push and wait for the newer webhook record
as described above.

## Cleanup and rollback

Delete only resources created by the current smoke run and only by their exact
UUID. Existing applications, services, databases, volumes, DNS records, and
Git history always require explicit approval.

The `/tmp` smoke runner creates an isolated Dockerfile application and removes
that exact application unless `--keep` is set. It waits for deployment first,
then retries public TLS and health verification for a bounded period so ACME
certificate issuance can finish:

```bash
python3 scripts/smoke_deploy.py \
  --project-uuid PROJECT_UUID \
  --server-uuid SERVER_UUID \
  --domain https://smoke.example.com
```
