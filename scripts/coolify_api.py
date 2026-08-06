#!/usr/bin/env python3
"""Small, secret-safe client for the Coolify v1 REST API."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable


TERMINAL_DEPLOYMENT_STATES = {"finished", "failed", "cancelled", "canceled"}
MASK = "***MASKED***"
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
            "User-Agent": "jong-coolify-deploy/0.2",
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


def credentials(base_url: str | None) -> tuple[str, str]:
    resolved_base = base_url or os.environ.get("COOLIFY_BASE_URL", "")
    token = (
        os.environ.get("COOLIFY_API_TOKEN")
        or os.environ.get("COOLIFY_ACCESS_TOKEN")
        or ""
    )
    if not resolved_base:
        raise ValueError("set COOLIFY_BASE_URL or pass --base-url")
    if not token:
        raise ValueError("set COOLIFY_API_TOKEN or COOLIFY_ACCESS_TOKEN")
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
