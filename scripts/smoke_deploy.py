#!/usr/bin/env python3
"""Create, verify, and clean up a minimal Coolify application from /tmp."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from coolify_api import CoolifyApiError, CoolifyClient, credentials, deployment_uuid, redact
from verify_deployment import verify_target


DOCKERFILE = """\
FROM nginx:1.27-alpine
RUN printf '%s\\n' \
  'server {' \
  '  listen 80;' \
  '  location = /healthz { default_type text/plain; return 200 "ok"; }' \
  '  location / { root /usr/share/nginx/html; try_files $uri /index.html; }' \
  '}' > /etc/nginx/conf.d/default.conf
RUN printf '%s\\n' '<!doctype html><title>jong-coolify-deploy smoke</title><h1>ok</h1>' \
  > /usr/share/nginx/html/index.html
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url")
    parser.add_argument("--project-uuid", required=True)
    parser.add_argument("--server-uuid", required=True)
    parser.add_argument("--environment-name", default="production")
    parser.add_argument("--domain", help="Full URL, for example https://smoke.example.com")
    parser.add_argument("--deploy-timeout", type=float, default=900)
    parser.add_argument("--verify-timeout", type=float, default=180)
    parser.add_argument("--verify-interval", type=float, default=10)
    parser.add_argument("--request-timeout", type=float, default=30)
    parser.add_argument("--keep", action="store_true", help="Keep the temporary application")
    return parser


def wait_for_public_url(
    target_url: str,
    *,
    timeout: float,
    interval: float,
    request_timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    attempts = 0
    latest: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        attempts += 1
        latest = verify_target(
            target_url,
            ["/", "/deep/route"],
            "/healthz",
            "ok",
            request_timeout,
            target_url.startswith("https://"),
        )
        if latest["ok"]:
            latest["attempts"] = attempts
            return latest
        time.sleep(interval)
    latest = latest or {"ok": False, "error": "verification was not attempted"}
    latest["attempts"] = attempts
    return latest


def run(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    base_url, token = credentials(args.base_url)
    client = CoolifyClient(base_url, token, timeout=args.request_timeout)
    suffix = str(int(time.time()))
    name = f"jong-coolify-smoke-{suffix}"
    report: dict[str, Any] = {
        "ok": False,
        "name": name,
        "tmp_dir": None,
        "application_uuid": None,
        "deployment_uuid": None,
        "deployment_status": None,
        "verification": None,
        "logs_checked": False,
        "cleanup": {"requested": not args.keep, "ok": None, "error": None},
    }
    application_uuid: str | None = None
    exit_code = 2

    with tempfile.TemporaryDirectory(prefix="jong-coolify-smoke-", dir="/tmp") as tmp_dir:
        report["tmp_dir"] = tmp_dir
        dockerfile_path = Path(tmp_dir) / "Dockerfile"
        dockerfile_path.write_text(DOCKERFILE, encoding="utf-8")
        try:
            created = client.create_dockerfile_application(
                project_uuid=args.project_uuid,
                server_uuid=args.server_uuid,
                environment_name=args.environment_name,
                name=name,
                dockerfile=dockerfile_path.read_text(encoding="utf-8"),
                domains=args.domain,
            )
            if not isinstance(created, dict) or not created.get("uuid"):
                raise ValueError("Coolify create response did not contain application uuid")
            application_uuid = str(created["uuid"])
            report["application_uuid"] = application_uuid

            triggered = client.deploy(application_uuid)
            deploy_uuid = deployment_uuid(triggered)
            report["deployment_uuid"] = deploy_uuid
            deployment = client.wait_for_deployment(
                deploy_uuid,
                timeout=args.deploy_timeout,
            )
            status = str(deployment.get("status", "")) if isinstance(deployment, dict) else ""
            report["deployment_status"] = status

            logs = client.request(
                "GET",
                f"/applications/{application_uuid}/logs",
                query={"lines": 80},
            )
            report["logs_checked"] = logs is not None

            if status.lower() != "finished":
                report["error"] = f"deployment ended with status {status or 'unknown'}"
                return report, exit_code

            app = client.request("GET", f"/applications/{application_uuid}")
            target_url = args.domain
            if not target_url and isinstance(app, dict):
                target_url = app.get("fqdn")
            if not target_url:
                report["error"] = "deployment finished but no public URL is available"
                return report, exit_code

            verification = wait_for_public_url(
                str(target_url).split(",", 1)[0],
                timeout=args.verify_timeout,
                interval=args.verify_interval,
                request_timeout=args.request_timeout,
            )
            report["verification"] = verification
            report["ok"] = verification["ok"]
            exit_code = 0 if report["ok"] else 2
            return report, exit_code
        finally:
            if application_uuid and not args.keep:
                try:
                    client.request("DELETE", f"/applications/{application_uuid}")
                    report["cleanup"]["ok"] = True
                except CoolifyApiError as exc:
                    report["cleanup"]["ok"] = False
                    report["cleanup"]["error"] = str(exc)


def main() -> int:
    args = build_parser().parse_args()
    try:
        report, exit_code = run(args)
    except (CoolifyApiError, OSError, ValueError) as exc:
        report = {"ok": False, "error": str(exc)}
        exit_code = 2
    print(json.dumps(redact(report), ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
