#!/usr/bin/env python3
"""Inspect a local repository for Coolify deployment readiness."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


COMPOSE_FILES = (
    "compose.yml",
    "compose.yaml",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.coolify.yml",
    "compose.coolify.yaml",
)
LOCKFILES = {
    "package-lock.json": "npm",
    "pnpm-lock.yaml": "pnpm",
    "yarn.lock": "yarn",
    "bun.lock": "bun",
    "bun.lockb": "bun",
}
SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".jks"}
SECRET_NAMES = {
    ".env",
    "credentials.json",
    "secrets.json",
    "id_rsa",
    "id_ed25519",
}
SAFE_SECRET_EXAMPLES = (".example", ".sample", ".template", ".dist")
WORKFLOW_SUFFIXES = {".yml", ".yaml"}
COOLIFY_DEPLOY_MARKERS = (
    "/api/v1/deploy",
    "coolify deploy",
    "coolify-deploy",
)


def run_git(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(project), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def git_value(project: Path, *args: str) -> str | None:
    result = run_git(project, *args)
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def parse_status(output: str) -> list[str]:
    paths: list[str] = []
    for line in output.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path)
    return paths


def package_details(project: Path) -> dict[str, Any]:
    path = project / "package.json"
    if not path.exists():
        return {"exists": False, "scripts": {}, "name": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"exists": True, "error": str(exc), "scripts": {}, "name": None}
    scripts = data.get("scripts") if isinstance(data.get("scripts"), dict) else {}
    return {"exists": True, "scripts": scripts, "name": data.get("name")}


def likely_secret_path(path: str) -> bool:
    candidate = Path(path)
    lowered = candidate.name.lower()
    if lowered.endswith(SAFE_SECRET_EXAMPLES):
        return False
    if lowered in SECRET_NAMES or candidate.suffix.lower() in SECRET_SUFFIXES:
        return True
    return "credential" in lowered or lowered.startswith("secret")


def tracked_secret_paths(project: Path, git_repo: bool) -> list[str]:
    if not git_repo:
        return []
    result = run_git(project, "ls-files", "-z")
    if result.returncode != 0:
        return []
    paths = [item for item in result.stdout.split("\0") if item]
    return sorted(path for path in paths if likely_secret_path(path))


def package_manager(project: Path) -> str | None:
    for filename, manager in LOCKFILES.items():
        if (project / filename).exists():
            return manager
    return None


def coolify_deploy_workflows(project: Path) -> list[str]:
    workflows = project / ".github" / "workflows"
    if not workflows.is_dir():
        return []
    matches: list[str] = []
    for path in sorted(workflows.iterdir()):
        if not path.is_file() or path.suffix.lower() not in WORKFLOW_SUFFIXES:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        if any(marker in content for marker in COOLIFY_DEPLOY_MARKERS):
            matches.append(path.relative_to(project).as_posix())
    return matches


def inspect_project(project: Path) -> dict[str, Any]:
    project = project.expanduser().resolve()
    if not project.is_dir():
        raise ValueError(f"project directory not found: {project}")

    git_repo = run_git(project, "rev-parse", "--is-inside-work-tree").returncode == 0
    status = run_git(project, "status", "--porcelain") if git_repo else None
    dirty_paths = parse_status(status.stdout) if status else []
    compose_file = next((name for name in COMPOSE_FILES if (project / name).exists()), None)
    dockerfile = next(
        (name for name in ("Dockerfile", "Dockerfile.prod") if (project / name).exists()),
        None,
    )
    package = package_details(project)
    scripts = package.get("scripts", {})
    gates = [name for name in ("test", "lint", "typecheck", "build") if name in scripts]
    remote = git_value(project, "remote", "get-url", "origin") if git_repo else None
    secret_paths = tracked_secret_paths(project, git_repo)
    deploy_workflows = coolify_deploy_workflows(project)

    warnings: list[str] = []
    if dirty_paths:
        warnings.append("worktree has changes; preserve unrelated paths")
    if not remote:
        warnings.append("origin remote is missing")
    if secret_paths:
        warnings.append("tracked filenames may contain secrets")
    if deploy_workflows:
        warnings.append(
            "existing GitHub workflow may already trigger Coolify; avoid duplicate auto-deploy"
        )
    if not dockerfile and not compose_file and not package.get("exists"):
        warnings.append("no Dockerfile, Compose file, or package.json detected")

    return {
        "project_dir": str(project),
        "git": {
            "is_repository": git_repo,
            "branch": git_value(project, "branch", "--show-current") if git_repo else None,
            "commit": git_value(project, "rev-parse", "HEAD") if git_repo else None,
            "origin": remote,
            "dirty_paths": dirty_paths,
            "coolify_deploy_workflows": deploy_workflows,
        },
        "project": {
            "package_name": package.get("name"),
            "package_manager": package_manager(project),
            "package_scripts": sorted(scripts),
            "recommended_quality_gates": gates,
            "dockerfile": dockerfile,
            "compose_file": compose_file,
            "recommended_resource_type": "service" if compose_file else "application",
            "git_auto_deploy_resource_type": "application",
            "git_auto_deploy_build_pack": (
                "dockercompose" if compose_file else None
            ),
            "recommended_build_mode": (
                "compose"
                if compose_file
                else "dockerfile"
                if dockerfile
                else "buildpack"
                if package.get("exists")
                else "unknown"
            ),
        },
        "security": {
            "tracked_secret_like_paths": secret_paths,
            "secret_values_read": False,
        },
        "warnings": warnings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", nargs="?", default=".")
    parser.add_argument("--pretty", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = inspect_project(Path(args.project_dir))
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
