#!/usr/bin/env python3
"""Verify a deployed HTTP(S) application and emit JSON evidence."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


REDIRECT_CODES = {301, 302, 307, 308}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(url: str, timeout: float, follow_redirects: bool = True) -> dict[str, Any]:
    opener = urllib.request.build_opener() if follow_redirects else urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": "jong-coolify-deploy/0.1"})
    try:
        with opener.open(req, timeout=timeout) as response:
            body = response.read(65536)
            return {
                "status": response.getcode(),
                "final_url": response.geturl(),
                "content_type": response.headers.get_content_type(),
                "location": response.headers.get("Location"),
                "body": body.decode("utf-8", errors="replace"),
                "error": None,
            }
    except urllib.error.HTTPError as exc:
        body = exc.read(65536)
        return {
            "status": exc.code,
            "final_url": exc.geturl(),
            "content_type": exc.headers.get_content_type(),
            "location": exc.headers.get("Location"),
            "body": body.decode("utf-8", errors="replace"),
            "error": None,
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "status": None,
            "final_url": url,
            "content_type": None,
            "location": None,
            "body": "",
            "error": str(exc),
        }


def endpoint_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/") + "/"
    return urllib.parse.urljoin(base, path.lstrip("/"))


def verify_endpoint(base_url: str, path: str, timeout: float) -> dict[str, Any]:
    result = request(endpoint_url(base_url, path), timeout)
    result["path"] = path
    result["ok"] = result["error"] is None and 200 <= (result["status"] or 0) < 400
    result.pop("body", None)
    return result


def verify_target(
    base_url: str,
    paths: list[str],
    health_path: str | None,
    expected_health_body: str | None,
    timeout: float,
    check_http_redirect: bool,
) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"invalid URL: {base_url}")

    checks = [verify_endpoint(base_url, path, timeout) for path in paths]
    health: dict[str, Any] | None = None
    if health_path:
        raw = request(endpoint_url(base_url, health_path), timeout)
        body_matches = expected_health_body is None or raw["body"].strip() == expected_health_body
        health = {
            "path": health_path,
            "status": raw["status"],
            "content_type": raw["content_type"],
            "error": raw["error"],
            "body_matches": body_matches,
            "ok": raw["error"] is None and raw["status"] == 200 and body_matches,
        }

    redirect: dict[str, Any] | None = None
    if check_http_redirect and parsed.scheme == "https":
        http_url = urllib.parse.urlunparse(parsed._replace(scheme="http"))
        raw = request(http_url, timeout, follow_redirects=False)
        location = raw["location"] or ""
        redirect = {
            "status": raw["status"],
            "location": location,
            "error": raw["error"],
            "ok": raw["status"] in REDIRECT_CODES and location.startswith("https://"),
        }

    ok = all(item["ok"] for item in checks)
    ok = ok and (health is None or health["ok"])
    ok = ok and (redirect is None or redirect["ok"])
    return {
        "ok": ok,
        "base_url": base_url,
        "tls_verified": parsed.scheme == "https" and all(item["error"] is None for item in checks),
        "paths": checks,
        "health": health,
        "http_redirect": redirect,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--health-path", default="/healthz")
    parser.add_argument("--no-health", action="store_true")
    parser.add_argument("--expect-health-body")
    parser.add_argument("--check-http-redirect", action="store_true")
    parser.add_argument("--timeout", type=float, default=20)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    paths = args.path or ["/"]
    health_path = None if args.no_health else args.health_path
    try:
        report = verify_target(
            args.url,
            paths,
            health_path,
            args.expect_health_body,
            args.timeout,
            args.check_http_redirect,
        )
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
