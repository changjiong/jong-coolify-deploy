#!/usr/bin/env python3
"""Small, secret-safe client for the Coolify v1 REST API."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable


TERMINAL_DEPLOYMENT_STATES = {
    "finished",
    "failed",
    "cancelled",
    "canceled",
    "cancelled-by-user",
}
SUCCESSFUL_DEPLOYMENT_STATES = {"finished"}
MASK = "***MASKED***"
GIT_COMMIT_PATTERN = re.compile(r"^[0-9a-fA-F]{40,64}$")
Transport = Callable[
    [str, str, dict[str, str], bytes | None, float],
    tuple[int, dict[str, str], bytes],
]


class CoolifyApiError(RuntimeError):
    """Raised when Coolify returns an unsuccessful response."""

    def __init__(self, method: str, path: str, status: int | None, detail: str):
        self.method = method
        self.path = path
        self.status = status
        super().__init__(f"{method} {path} failed ({status}): {detail}")


def default_transport(
    method: str,
    url: str,
    headers: dict[str, str],
    data: bytes | None,
    timeout: float,
) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CoolifyApiError(method, urllib.parse.urlparse(url).path, None, str(exc)) from exc


def api_root(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if not base:
        raise ValueError("Coolify base URL is empty")
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"invalid Coolify base URL: {base_url}")
    return base if base.endswith("/api/v1") else f"{base}/api/v1"


def decode_body(body: bytes) -> Any:
    if not body:
        return None
    text = body.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def sensitive_key(key: str) -> bool:
    lowered = key.lower()
    exact = {
        "access_token",
        "api_token",
        "authorization",
        "dockerfile",
        "docker_compose_raw",
        "password",
        "private_key",
        "secret",
        "token",
        "value",
    }
    suffixes = ("_password", "_secret", "_token", "_value")
    return lowered in exact or lowered.endswith(suffixes)


def redact(value: Any, *, validation_errors: bool = False) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                redact(item, validation_errors=True)
                if str(key).lower() == "errors"
                else MASK
                if sensitive_key(str(key)) and not validation_errors
                else redact(item, validation_errors=validation_errors)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item, validation_errors=validation_errors) for item in value]
    return value


def error_detail(payload: Any) -> str:
    safe = redact(payload)
    text = json.dumps(safe, ensure_ascii=False) if not isinstance(safe, str) else safe
    return text[:1000]


def github_repository_slug(repository: str) -> str:
    value = repository.strip().rstrip("/")
    if value.startswith("git@") and ":" in value:
        path = value.split(":", 1)[1]
    else:
        parsed = urllib.parse.urlparse(value)
        path = parsed.path if parsed.scheme or parsed.netloc else value
    parts = [part for part in path.strip("/").split("/") if part]
    if len(parts) != 2:
        raise ValueError(f"expected a GitHub OWNER/REPO repository, got: {repository}")
    owner, name = parts
    if name.endswith(".git"):
        name = name[:-4]
    if not owner or not name:
        raise ValueError(f"expected a GitHub OWNER/REPO repository, got: {repository}")
    return f"{owner}/{name}"


def boolean_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value == 1
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def deployment_summary(deployment: dict[str, Any]) -> dict[str, Any]:
    return {
        key: deployment.get(key)
        for key in (
            "deployment_uuid",
            "application_name",
            "status",
            "commit",
            "commit_message",
            "is_webhook",
            "is_api",
            "created_at",
            "finished_at",
        )
        if key in deployment
    }


class CoolifyClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 30,
        transport: Transport = default_transport,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        if not token.strip():
            raise ValueError("Coolify API token is empty")
        self.root = api_root(base_url)
        self.token = token.strip()
        self.timeout = timeout
        self.transport = transport
        self.sleeper = sleeper

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: Any = None,
        query: dict[str, Any] | None = None,
    ) -> Any:
        normalized_path = "/" + path.lstrip("/")
        url = f"{self.root}{normalized_path}"
        if query:
            encoded = urllib.parse.urlencode(
                {key: value for key, value in query.items() if value is not None}
            )
            url = f"{url}?{encoded}"
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "jong-coolify-deploy/0.3.0",
        }
        status, _, raw = self.transport(method.upper(), url, headers, body, self.timeout)
        result = decode_body(raw)
        if not 200 <= status < 300:
            raise CoolifyApiError(method.upper(), normalized_path, status, error_detail(result))
        return result

    def create_dockerfile_application(
        self,
        *,
        project_uuid: str,
        server_uuid: str,
        environment_name: str,
        name: str,
        dockerfile: str,
        domains: str | None = None,
        ports_exposes: str = "80",
        health_check_path: str = "/healthz",
        instant_deploy: bool = False,
    ) -> Any:
        payload = {
            "project_uuid": project_uuid,
            "server_uuid": server_uuid,
            "environment_name": environment_name,
            "name": name,
            "dockerfile": base64.b64encode(dockerfile.encode("utf-8")).decode("ascii"),
            "ports_exposes": ports_exposes,
            "health_check_enabled": True,
            "health_check_path": health_check_path,
            "instant_deploy": instant_deploy,
        }
        if domains:
            payload["domains"] = domains
        return self.request("POST", "/applications/dockerfile", payload=payload)

    def create_git_application(
        self,
        *,
        endpoint: str,
        project_uuid: str,
        server_uuid: str,
        environment_name: str,
        name: str,
        git_repository: str,
        git_branch: str,
        build_pack: str,
        ports_exposes: str,
        domains: str | None = None,
        github_app_uuid: str | None = None,
        dockerfile_location: str | None = None,
        base_directory: str | None = None,
        publish_directory: str | None = None,
        health_check_path: str = "/healthz",
        instant_deploy: bool = False,
        auto_deploy_enabled: bool,
    ) -> Any:
        payload = {
            "project_uuid": project_uuid,
            "server_uuid": server_uuid,
            "environment_name": environment_name,
            "name": name,
            "git_repository": git_repository,
            "git_branch": git_branch,
            "build_pack": build_pack,
            "ports_exposes": ports_exposes,
            "health_check_enabled": True,
            "health_check_path": health_check_path,
            "instant_deploy": instant_deploy,
            "is_auto_deploy_enabled": auto_deploy_enabled,
        }
        optional = {
            "domains": domains,
            "github_app_uuid": github_app_uuid,
            "dockerfile_location": dockerfile_location,
            "base_directory": base_directory,
            "publish_directory": publish_directory,
        }
        payload.update({key: value for key, value in optional.items() if value})
        return self.request("POST", endpoint, payload=payload)

    def get_application(self, application_uuid: str) -> dict[str, Any]:
        application = self.request("GET", f"/applications/{application_uuid}")
        if not isinstance(application, dict):
            raise ValueError("Coolify application response must be an object")
        return application

    def inspect_auto_deploy_source(
        self,
        application_uuid: str,
        *,
        repository: str,
        branch: str,
    ) -> dict[str, Any]:
        if not branch.strip():
            raise ValueError("auto-deploy branch is empty")
        expected_repository = github_repository_slug(repository)
        application = self.get_application(application_uuid)
        actual_repository = github_repository_slug(
            str(application.get("git_repository") or "")
        )
        if actual_repository.casefold() != expected_repository.casefold():
            raise ValueError(
                "application repository mismatch: "
                f"expected {expected_repository}, got {actual_repository}"
            )

        source_id = application.get("source_id")
        if source_id is None:
            raise ValueError(
                "application is not connected through a Coolify GitHub App; "
                "native push auto-deploy cannot be verified"
            )
        github_apps = self.request("GET", "/github-apps")
        if not isinstance(github_apps, list):
            raise ValueError("Coolify GitHub Apps response must be an array")
        github_app = next(
            (
                item
                for item in github_apps
                if isinstance(item, dict) and str(item.get("id")) == str(source_id)
            ),
            None,
        )
        if github_app is None:
            raise ValueError(
                f"application source_id {source_id} does not match an accessible GitHub App"
            )

        repositories_payload = self.request(
            "GET", f"/github-apps/{source_id}/repositories"
        )
        repositories = (
            repositories_payload.get("repositories")
            if isinstance(repositories_payload, dict)
            else None
        )
        if not isinstance(repositories, list):
            raise ValueError("Coolify GitHub App repositories response must contain an array")
        accessible_repositories = {
            str(item.get("full_name", "")).casefold()
            for item in repositories
            if isinstance(item, dict) and item.get("full_name")
        }
        if expected_repository.casefold() not in accessible_repositories:
            raise ValueError(
                f"GitHub App installation cannot access {expected_repository}"
            )

        settings = application.get("settings")
        auto_deploy_enabled = boolean_value(
            settings.get("is_auto_deploy_enabled")
            if isinstance(settings, dict)
            else False
        )
        return {
            "application_uuid": application_uuid,
            "application_name": application.get("name"),
            "repository": actual_repository,
            "configured_branch": application.get("git_branch"),
            "target_branch": branch,
            "auto_deploy_enabled": auto_deploy_enabled,
            "watch_paths": application.get("watch_paths") or None,
            "github_app": {
                "id": github_app.get("id"),
                "uuid": github_app.get("uuid"),
                "name": github_app.get("name"),
            },
        }

    def configure_auto_deploy(
        self,
        application_uuid: str,
        *,
        repository: str,
        branch: str,
    ) -> dict[str, Any]:
        before = self.inspect_auto_deploy_source(
            application_uuid,
            repository=repository,
            branch=branch,
        )
        self.request(
            "PATCH",
            f"/applications/{application_uuid}",
            payload={
                "git_branch": branch,
                "is_auto_deploy_enabled": True,
            },
        )
        after = self.inspect_auto_deploy_source(
            application_uuid,
            repository=repository,
            branch=branch,
        )
        if after["configured_branch"] != branch:
            raise ValueError(
                "Coolify did not persist the requested auto-deploy branch: "
                f"expected {branch}, got {after['configured_branch']}"
            )
        if not after["auto_deploy_enabled"]:
            raise ValueError("Coolify did not persist is_auto_deploy_enabled=true")
        history = self.list_application_deployments(application_uuid, take=100)
        baseline_id = max(
            (
                int(item.get("id") or 0)
                for item in history["deployments"]
                if isinstance(item, dict)
            ),
            default=0,
        )
        return {
            "before": before,
            "after": after,
            "verification_baseline_id": baseline_id,
        }

    def list_application_deployments(
        self,
        application_uuid: str,
        *,
        skip: int = 0,
        take: int = 25,
    ) -> dict[str, Any]:
        result = self.request(
            "GET",
            f"/deployments/applications/{application_uuid}",
            query={"skip": skip, "take": take},
        )
        if not isinstance(result, dict) or not isinstance(result.get("deployments"), list):
            raise ValueError("Coolify deployment history response must contain deployments")
        return result

    def wait_for_webhook_deployment(
        self,
        application_uuid: str,
        *,
        commit: str,
        after_id: int,
        timeout: float = 600,
        interval: float = 2,
    ) -> dict[str, Any]:
        normalized_commit = commit.strip().lower()
        if not GIT_COMMIT_PATTERN.fullmatch(normalized_commit):
            raise ValueError("commit must be a full 40-64 character hexadecimal Git SHA")
        if after_id < 0:
            raise ValueError("after_id must be zero or greater")

        deadline = time.monotonic() + timeout
        history_path = f"/deployments/applications/{application_uuid}"
        while time.monotonic() < deadline:
            history = self.list_application_deployments(application_uuid, take=100)
            deployments = history["deployments"]
            matches = [
                item
                for item in deployments
                if isinstance(item, dict)
                and int(item.get("id") or 0) > after_id
                and str(item.get("commit", "")).lower() == normalized_commit
                and boolean_value(item.get("is_webhook"))
            ]
            if matches:
                deployment = max(matches, key=lambda item: int(item.get("id") or 0))
                deployment_id = deployment.get("deployment_uuid")
                if not deployment_id:
                    raise ValueError("matching webhook deployment has no deployment_uuid")
                status = str(deployment.get("status", "")).lower()
                if status in TERMINAL_DEPLOYMENT_STATES:
                    deployment = self.request(
                        "GET", f"/deployments/{deployment_id}"
                    )
                    status = str(deployment.get("status", "")).lower()
                else:
                    remaining = max(0.1, deadline - time.monotonic())
                    deployment = self.wait_for_deployment(
                        str(deployment_id),
                        timeout=remaining,
                        interval=interval,
                    )
                    status = str(deployment.get("status", "")).lower()
                if str(deployment.get("commit", "")).lower() != normalized_commit:
                    raise ValueError("deployment commit changed while waiting")
                if not boolean_value(deployment.get("is_webhook")):
                    raise ValueError("matching deployment was not triggered by a webhook")
                if status not in SUCCESSFUL_DEPLOYMENT_STATES:
                    raise CoolifyApiError(
                        "GET",
                        f"/deployments/{deployment_id}",
                        None,
                        f"webhook deployment reached terminal status {status}",
                    )
                return deployment_summary(deployment)
            self.sleeper(interval)
        raise CoolifyApiError(
            "GET",
            history_path,
            None,
            "timed out waiting for a GitHub webhook deployment matching "
            f"application={application_uuid} commit={normalized_commit} after_id={after_id}; "
            "check the "
            "GitHub App installation, target branch, watch_paths, webhook delivery, "
            "and [skip ci]/[skip cd] commit markers",
        )

    def verify_auto_deploy(
        self,
        application_uuid: str,
        *,
        repository: str,
        branch: str,
        commit: str,
        after_id: int,
        timeout: float = 600,
        interval: float = 2,
    ) -> dict[str, Any]:
        configuration = self.inspect_auto_deploy_source(
            application_uuid,
            repository=repository,
            branch=branch,
        )
        if configuration["configured_branch"] != branch:
            raise ValueError(
                "application branch mismatch: "
                f"expected {branch}, got {configuration['configured_branch']}"
            )
        if not configuration["auto_deploy_enabled"]:
            raise ValueError("application auto-deploy is disabled")
        deployment = self.wait_for_webhook_deployment(
            application_uuid,
            commit=commit,
            after_id=after_id,
            timeout=timeout,
            interval=interval,
        )
        return {
            "verified": True,
            "trigger": "github_push_webhook",
            "configuration": configuration,
            "deployment": deployment,
        }

    def deploy(self, application_uuid: str, *, force: bool = False) -> Any:
        return self.request(
            "GET",
            "/deploy",
            query={"uuid": application_uuid, "force": str(force).lower()},
        )

    def wait_for_deployment(
        self,
        deployment_uuid: str,
        *,
        timeout: float = 600,
        interval: float = 5,
    ) -> Any:
        deadline = time.monotonic() + timeout
        latest: Any = None
        while time.monotonic() < deadline:
            latest = self.request("GET", f"/deployments/{deployment_uuid}")
            status = str(latest.get("status", "")).lower() if isinstance(latest, dict) else ""
            if status in TERMINAL_DEPLOYMENT_STATES:
                return latest
            self.sleeper(interval)
        raise CoolifyApiError(
            "GET",
            f"/deployments/{deployment_uuid}",
            None,
            f"timed out after {timeout:g}s; last response={error_detail(latest)}",
        )


def codex_config_env() -> dict[str, str]:
    path = Path(
        os.environ.get("CODEX_CONFIG_PATH", "~/.codex/config.toml")
    ).expanduser()
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as handle:
            config = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"unable to read Codex config: {path}") from exc
    env = (
        config.get("mcp_servers", {})
        .get("coolify", {})
        .get("env", {})
    )
    if not isinstance(env, dict):
        return {}
    return {
        key: str(value)
        for key, value in env.items()
        if key in {"COOLIFY_BASE_URL", "COOLIFY_API_TOKEN", "COOLIFY_ACCESS_TOKEN"}
    }


def credentials(base_url: str | None) -> tuple[str, str]:
    config_env = codex_config_env()
    resolved_base = (
        base_url
        or os.environ.get("COOLIFY_BASE_URL")
        or config_env.get("COOLIFY_BASE_URL", "")
    )
    token = (
        os.environ.get("COOLIFY_API_TOKEN")
        or os.environ.get("COOLIFY_ACCESS_TOKEN")
        or config_env.get("COOLIFY_API_TOKEN")
        or config_env.get("COOLIFY_ACCESS_TOKEN")
        or ""
    )
    if not resolved_base:
        raise ValueError(
            "set COOLIFY_BASE_URL, pass --base-url, or configure "
            "mcp_servers.coolify.env.COOLIFY_BASE_URL in ~/.codex/config.toml"
        )
    if not token:
        raise ValueError(
            "set COOLIFY_API_TOKEN/COOLIFY_ACCESS_TOKEN or configure the matching "
            "key under mcp_servers.coolify.env in ~/.codex/config.toml"
        )
    return resolved_base, token


def deployment_uuid(payload: Any) -> str:
    if isinstance(payload, dict):
        direct = payload.get("deployment_uuid")
        if direct:
            return str(direct)
        deployments = payload.get("deployments")
        if isinstance(deployments, list) and deployments:
            first = deployments[0]
            if isinstance(first, dict) and first.get("deployment_uuid"):
                return str(first["deployment_uuid"])
    raise ValueError("Coolify deploy response did not contain deployment_uuid")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", help="Coolify origin, for example https://coolify.example.com")
    parser.add_argument("--timeout", type=float, default=30)
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in (
        "health",
        "list-projects",
        "list-servers",
        "list-applications",
        "list-github-apps",
    ):
        subparsers.add_parser(name)

    get_app = subparsers.add_parser("get-application")
    get_app.add_argument("uuid")

    create = subparsers.add_parser("create-dockerfile")
    create.add_argument("--project-uuid", required=True)
    create.add_argument("--server-uuid", required=True)
    create.add_argument("--environment-name", default="production")
    create.add_argument("--name", required=True)
    create.add_argument("--dockerfile", type=Path, required=True)
    create.add_argument("--domain")
    create.add_argument("--port", default="80")
    create.add_argument("--health-path", default="/healthz")
    create.add_argument("--instant-deploy", action="store_true")

    def add_git_arguments(command: argparse.ArgumentParser) -> None:
        command.add_argument("--project-uuid", required=True)
        command.add_argument("--server-uuid", required=True)
        command.add_argument("--environment-name", default="production")
        command.add_argument("--name", required=True)
        command.add_argument("--repository", required=True)
        command.add_argument("--branch", required=True)
        command.add_argument(
            "--build-pack",
            required=True,
            choices=("nixpacks", "static", "dockerfile", "dockercompose"),
        )
        command.add_argument("--domain")
        command.add_argument("--port", required=True)
        command.add_argument("--dockerfile-location")
        command.add_argument("--base-directory")
        command.add_argument("--publish-directory")
        command.add_argument("--health-path", default="/healthz")
        command.add_argument("--instant-deploy", action="store_true")

    public = subparsers.add_parser("create-public")
    add_git_arguments(public)

    github = subparsers.add_parser("create-github")
    add_git_arguments(github)
    github.add_argument("--github-app-uuid", required=True)
    github.add_argument(
        "--no-auto-deploy",
        action="store_false",
        dest="auto_deploy",
        default=True,
        help="create the application with GitHub push auto-deploy disabled",
    )

    configure_auto = subparsers.add_parser("configure-auto-deploy")
    configure_auto.add_argument("uuid")
    configure_auto.add_argument("--repository", required=True)
    configure_auto.add_argument("--branch", required=True)

    verify_auto = subparsers.add_parser("verify-auto-deploy")
    verify_auto.add_argument("uuid")
    verify_auto.add_argument("--repository", required=True)
    verify_auto.add_argument("--branch", required=True)
    verify_auto.add_argument("--commit", required=True)
    verify_auto.add_argument(
        "--after-id",
        type=int,
        required=True,
        help="verification_baseline_id returned by configure-auto-deploy before the test push",
    )
    verify_auto.add_argument("--wait-timeout", type=float, default=600)
    verify_auto.add_argument("--interval", type=float, default=2)

    list_deployments = subparsers.add_parser("list-deployments")
    list_deployments.add_argument("uuid")
    list_deployments.add_argument("--skip", type=int, default=0)
    list_deployments.add_argument("--take", type=int, default=25)

    deploy_parser = subparsers.add_parser("deploy")
    deploy_parser.add_argument("uuid")
    deploy_parser.add_argument("--force", action="store_true")
    deploy_parser.add_argument("--wait", action="store_true")
    deploy_parser.add_argument("--wait-timeout", type=float, default=600)
    deploy_parser.add_argument("--interval", type=float, default=5)

    logs = subparsers.add_parser("logs")
    logs.add_argument("uuid")
    logs.add_argument("--lines", type=int, default=100)

    envs = subparsers.add_parser("list-envs")
    envs.add_argument("uuid")

    apply_envs = subparsers.add_parser("apply-env-file")
    apply_envs.add_argument("uuid")
    apply_envs.add_argument("--file", type=Path, required=True)

    delete = subparsers.add_parser("delete-application")
    delete.add_argument("uuid")
    delete.add_argument("--yes", action="store_true")
    return parser


def execute(client: CoolifyClient, args: argparse.Namespace) -> Any:
    if args.command == "health":
        return client.request("GET", "/health")
    if args.command == "list-projects":
        return client.request("GET", "/projects")
    if args.command == "list-servers":
        return client.request("GET", "/servers")
    if args.command == "list-applications":
        return client.request("GET", "/applications")
    if args.command == "list-github-apps":
        return client.request("GET", "/github-apps")
    if args.command == "get-application":
        return client.request("GET", f"/applications/{args.uuid}")
    if args.command == "create-dockerfile":
        dockerfile = args.dockerfile.read_text(encoding="utf-8")
        return client.create_dockerfile_application(
            project_uuid=args.project_uuid,
            server_uuid=args.server_uuid,
            environment_name=args.environment_name,
            name=args.name,
            dockerfile=dockerfile,
            domains=args.domain,
            ports_exposes=args.port,
            health_check_path=args.health_path,
            instant_deploy=args.instant_deploy,
        )
    if args.command == "configure-auto-deploy":
        return client.configure_auto_deploy(
            args.uuid,
            repository=args.repository,
            branch=args.branch,
        )
    if args.command == "verify-auto-deploy":
        return client.verify_auto_deploy(
            args.uuid,
            repository=args.repository,
            branch=args.branch,
            commit=args.commit,
            after_id=args.after_id,
            timeout=args.wait_timeout,
            interval=args.interval,
        )
    if args.command == "list-deployments":
        return client.list_application_deployments(
            args.uuid,
            skip=args.skip,
            take=args.take,
        )
    if args.command in {"create-public", "create-github"}:
        return client.create_git_application(
            endpoint=(
                "/applications/public"
                if args.command == "create-public"
                else "/applications/private-github-app"
            ),
            project_uuid=args.project_uuid,
            server_uuid=args.server_uuid,
            environment_name=args.environment_name,
            name=args.name,
            git_repository=args.repository,
            git_branch=args.branch,
            build_pack=args.build_pack,
            ports_exposes=args.port,
            domains=args.domain,
            github_app_uuid=(
                args.github_app_uuid if args.command == "create-github" else None
            ),
            dockerfile_location=args.dockerfile_location,
            base_directory=args.base_directory,
            publish_directory=args.publish_directory,
            health_check_path=args.health_path,
            instant_deploy=args.instant_deploy,
            auto_deploy_enabled=(
                args.auto_deploy if args.command == "create-github" else False
            ),
        )
    if args.command == "deploy":
        triggered = client.deploy(args.uuid, force=args.force)
        if not args.wait:
            return triggered
        return {
            "trigger": triggered,
            "deployment": client.wait_for_deployment(
                deployment_uuid(triggered),
                timeout=args.wait_timeout,
                interval=args.interval,
            ),
        }
    if args.command == "logs":
        return client.request(
            "GET",
            f"/applications/{args.uuid}/logs",
            query={"lines": args.lines},
        )
    if args.command == "list-envs":
        return client.request("GET", f"/applications/{args.uuid}/envs")
    if args.command == "apply-env-file":
        values = json.loads(args.file.read_text(encoding="utf-8"))
        if not isinstance(values, list):
            raise ValueError("environment file must contain a JSON array")
        for item in values:
            if not isinstance(item, dict) or not item.get("key") or "value" not in item:
                raise ValueError("each environment entry requires key and value")
        return client.request(
            "PATCH",
            f"/applications/{args.uuid}/envs/bulk",
            payload={"data": values},
        )
    if args.command == "delete-application":
        if not args.yes:
            raise ValueError("delete requires --yes and an exact application UUID")
        return client.request("DELETE", f"/applications/{args.uuid}")
    raise ValueError(f"unsupported command: {args.command}")


def main() -> int:
    args = build_parser().parse_args()
    try:
        base_url, token = credentials(args.base_url)
        client = CoolifyClient(base_url, token, timeout=args.timeout)
        result = execute(client, args)
    except (CoolifyApiError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, "result": redact(result)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
