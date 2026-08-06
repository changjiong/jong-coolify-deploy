from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from inspect_project import inspect_project


def git(project: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(project), *args],
        check=True,
        text=True,
        capture_output=True,
    )


class InspectProjectTests(unittest.TestCase):
    def test_application_project_detects_scripts_and_remote(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / "Dockerfile").write_text("FROM nginx:alpine\n", encoding="utf-8")
            (project / "package-lock.json").write_text("{}\n", encoding="utf-8")
            (project / "package.json").write_text(
                json.dumps({"name": "demo", "scripts": {"test": "x", "build": "y"}}),
                encoding="utf-8",
            )
            git(project, "init")
            git(project, "remote", "add", "origin", "https://github.com/example/demo.git")

            report = inspect_project(project)

            self.assertEqual("application", report["project"]["recommended_resource_type"])
            self.assertEqual("dockerfile", report["project"]["recommended_build_mode"])
            self.assertEqual("npm", report["project"]["package_manager"])
            self.assertEqual(["test", "build"], report["project"]["recommended_quality_gates"])
            self.assertEqual("https://github.com/example/demo.git", report["git"]["origin"])

    def test_compose_project_prefers_service(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / "compose.yml").write_text("services: {}\n", encoding="utf-8")

            report = inspect_project(project)

            self.assertEqual("service", report["project"]["recommended_resource_type"])
            self.assertEqual("compose", report["project"]["recommended_build_mode"])

    def test_tracked_secret_filename_is_reported_without_reading_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / ".env").write_text("TOKEN=do-not-read\n", encoding="utf-8")
            (project / ".env.example").write_text("TOKEN=\n", encoding="utf-8")
            git(project, "init")
            git(project, "add", ".env", ".env.example")

            report = inspect_project(project)

            self.assertEqual([".env"], report["security"]["tracked_secret_like_paths"])
            self.assertFalse(report["security"]["secret_values_read"])


if __name__ == "__main__":
    unittest.main()
