---
name: jong-coolify-deploy
description: |
  Deploy a local Git repository end to end to a self-hosted VPS managed by Coolify. Use when the user asks to deploy or publish the current or named local project to their own Coolify server, perform a one-click local repo -> private GitHub -> Coolify VPS delivery, choose Application versus Docker Compose Service, expose editable environment variables, configure domains and Traefik reachability, persistence and health checks, trigger deployment, and verify HTTPS, logs, and runtime status. Also trigger for Chinese requests such as “把当前项目部署到 Coolify”, “发布到自有 VPS”, “用这个域名一键部署”, or “改造后部署到我的服务器”. Do not use for Vercel or Cloudflare Pages delivery, generic SSH-only VPS provisioning without Coolify, pure DNS explanations, local-only Docker runs, or routine restart/log inspection without a deployment objective.
---

# Jong Coolify Deploy

Own the complete delivery path from a local repository to a verified public URL on a user-controlled Coolify VPS.

## Boundary

This skill owns:

- local repository readiness and minimal deployment configuration
- GitHub repository creation or connection when Coolify needs a source
- Coolify project, environment, Application or Service provisioning
- editable environment variables, domains, persistence, health checks, and internal reachability
- deployment, logs, DNS/TLS checks, and final evidence

Route elsewhere for Vercel/Cloudflare Pages, generic VPS provisioning, pure DNS education, or routine operations without a deployment outcome.

## Core Workflow

1. Inspect the local project and unrelated worktree changes.
2. Confirm Coolify REST API health, target server, project/environment, domain, and source repository.
3. Run repository-defined tests, lint, typecheck, and build commands that are relevant to deployment.
4. Add only the minimal Dockerfile, Compose, healthcheck, or runtime configuration required for production.
5. Publish only task-related source changes to the intended GitHub repository.
6. Create or update the exact Coolify resource, deploy it, and wait for a terminal deployment state.
7. Verify status, logs, DNS, HTTPS, health path, deep routes, persistence, and internal aliases when applicable.
8. Report the URL, source commit, Coolify resource, changes, verification evidence, rollback boundary, and unresolved risks.

## Resource Choice

- Use a Coolify **Application** for one runtime container or a repository/Dockerfile app.
- Use a Coolify **Service** for Docker Compose, multiple containers, sidecars, explicit volumes, or complex Traefik labels.
- Reuse an exact existing resource only after matching repository, domain, and environment. Never reuse by a similar name alone.

## Safety

- Use the bundled Coolify REST client against the user's own instance domain. Coolify MCP is an optional typed adapter, not a dependency.
- In Codex, reuse `mcp_servers.coolify.env` from `~/.codex/config.toml` when explicit environment variables are absent. Never reveal or copy those values.
- Never silently downgrade an unavailable API to SSH or direct Docker mutations on the VPS.
- Never expose tokens, passwords, private keys, DSNs, or revealed environment-variable values.
- Never delete applications, services, databases, volumes, DNS records, or Git history without explicit approval.
- Preserve unrelated local changes and stage only deployment-related files.
- Capture the previous resource/deployment identity before modifying an existing production resource.
- Treat local Docker as unrelated to the VPS unless the host identity is proven.

## Output Contract

Return:

- public URL and final runtime status
- GitHub repository, branch, and deployed commit
- Coolify project/environment/resource name and short UUID
- environment-variable keys changed, with values masked
- persistence and backup implications
- DNS/TLS, health, logs, and route verification results
- rollback boundary and any `missing evidence`

## References

- End-to-end workflow: `references/deployment-workflow.md`
- Coolify API routing: `references/coolify-api-routing.md`
- Safety and rollback: `references/safety-rollback.md`
- Project inspection: `scripts/inspect_project.py`
- Coolify REST client: `scripts/coolify_api.py`
- Minimal `/tmp` deployment smoke test: `scripts/smoke_deploy.py`
- Public verification: `scripts/verify_deployment.py`
