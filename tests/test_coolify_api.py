import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.coolify_api import (
    CoolifyApiError,
    CoolifyClient,
    build_parser,
    credentials,
    deployment_uuid,
    execute,
    github_repository_slug,
    redact,
)


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, data, timeout):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "data": data,
                "timeout": timeout,
            }
        )
        return self.responses.pop(0)


class CoolifyApiTests(unittest.TestCase):
    def test_request_uses_instance_domain_and_bearer_token(self):
        transport = FakeTransport([(200, {}, b'{"status":"ok"}')])
        client = CoolifyClient(
            "https://coolify.example.com",
            "secret-token",
            transport=transport,
        )

        result = client.request("GET", "/health")

        self.assertEqual(result, {"status": "ok"})
        call = transport.calls[0]
        self.assertEqual(call["url"], "https://coolify.example.com/api/v1/health")
        self.assertEqual(call["headers"]["Authorization"], "Bearer secret-token")

    def test_create_dockerfile_builds_expected_payload(self):
        transport = FakeTransport([(201, {}, b'{"uuid":"app-1"}')])
        client = CoolifyClient("https://coolify.example.com", "token", transport=transport)

        client.create_dockerfile_application(
            project_uuid="project-1",
            server_uuid="server-1",
            environment_name="production",
            name="smoke",
            dockerfile="FROM nginx",
            domains="https://smoke.example.com",
        )

        call = transport.calls[0]
        payload = json.loads(call["data"])
        self.assertEqual(call["method"], "POST")
        self.assertTrue(call["url"].endswith("/api/v1/applications/dockerfile"))
        self.assertEqual(payload["project_uuid"], "project-1")
        self.assertEqual(payload["domains"], "https://smoke.example.com")
        self.assertEqual(
            base64.b64decode(payload["dockerfile"]).decode("utf-8"),
            "FROM nginx",
        )
        self.assertFalse(payload["instant_deploy"])

    def test_wait_for_deployment_stops_at_terminal_state(self):
        transport = FakeTransport(
            [
                (200, {}, b'{"status":"in_progress"}'),
                (200, {}, b'{"status":"finished"}'),
            ]
        )
        sleeps = []
        client = CoolifyClient(
            "https://coolify.example.com/api/v1",
            "token",
            transport=transport,
            sleeper=sleeps.append,
        )

        result = client.wait_for_deployment("deployment-1", timeout=10, interval=0.01)

        self.assertEqual(result["status"], "finished")
        self.assertEqual(sleeps, [0.01])

    def test_create_private_github_application_uses_typed_endpoint(self):
        transport = FakeTransport([(201, {}, b'{"uuid":"app-2"}')])
        client = CoolifyClient("https://coolify.example.com", "token", transport=transport)

        client.create_git_application(
            endpoint="/applications/private-github-app",
            project_uuid="project-1",
            server_uuid="server-1",
            environment_name="production",
            name="private-app",
            git_repository="https://github.com/acme/private-app",
            git_branch="main",
            build_pack="dockerfile",
            ports_exposes="8080",
            domains="https://private.example.com",
            github_app_uuid="github-app-1",
            dockerfile_location="/Dockerfile",
            auto_deploy_enabled=True,
        )

        call = transport.calls[0]
        payload = json.loads(call["data"])
        self.assertTrue(call["url"].endswith("/api/v1/applications/private-github-app"))
        self.assertEqual(payload["github_app_uuid"], "github-app-1")
        self.assertEqual(payload["dockerfile_location"], "/Dockerfile")
        self.assertEqual(payload["git_branch"], "main")
        self.assertTrue(payload["is_auto_deploy_enabled"])

    def test_cli_create_dockerfile_dispatch_keeps_auto_deploy_out_of_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            dockerfile = Path(directory) / "Dockerfile"
            dockerfile.write_text("FROM nginx\n", encoding="utf-8")
            args = build_parser().parse_args(
                [
                    "create-dockerfile",
                    "--project-uuid",
                    "project-1",
                    "--server-uuid",
                    "server-1",
                    "--name",
                    "smoke",
                    "--dockerfile",
                    str(dockerfile),
                ]
            )
            transport = FakeTransport([(201, {}, b'{"uuid":"app-1"}')])
            client = CoolifyClient(
                "https://coolify.example.com", "token", transport=transport
            )

            execute(client, args)

        payload = json.loads(transport.calls[0]["data"])
        self.assertNotIn("is_auto_deploy_enabled", payload)

    def test_cli_create_github_enables_auto_deploy_by_default(self):
        args = build_parser().parse_args(
            [
                "create-github",
                "--project-uuid",
                "project-1",
                "--server-uuid",
                "server-1",
                "--github-app-uuid",
                "github-app-1",
                "--name",
                "private-app",
                "--repository",
                "https://github.com/acme/private-app",
                "--branch",
                "main",
                "--build-pack",
                "dockerfile",
                "--port",
                "8080",
            ]
        )
        transport = FakeTransport([(201, {}, b'{"uuid":"app-2"}')])
        client = CoolifyClient(
            "https://coolify.example.com", "token", transport=transport
        )

        execute(client, args)

        payload = json.loads(transport.calls[0]["data"])
        self.assertTrue(payload["is_auto_deploy_enabled"])

    def test_configure_auto_deploy_checks_github_app_and_reads_setting_back(self):
        application_before = {
            "uuid": "app-2",
            "name": "private-app",
            "git_repository": "https://github.com/acme/private-app.git",
            "git_branch": "develop",
            "source_id": 7,
            "settings": {"is_auto_deploy_enabled": False},
        }
        application_after = {
            **application_before,
            "git_branch": "main",
            "settings": {"is_auto_deploy_enabled": True},
        }
        github_apps = [{"id": 7, "uuid": "gh-7", "name": "Coolify GitHub"}]
        repositories = {
            "repositories": [{"full_name": "acme/private-app"}]
        }
        transport = FakeTransport(
            [
                (200, {}, json.dumps(application_before).encode()),
                (200, {}, json.dumps(github_apps).encode()),
                (200, {}, json.dumps(repositories).encode()),
                (200, {}, b'{"uuid":"app-2"}'),
                (200, {}, json.dumps(application_after).encode()),
                (200, {}, json.dumps(github_apps).encode()),
                (200, {}, json.dumps(repositories).encode()),
                (
                    200,
                    {},
                    b'{"count":1,"deployments":[{"id":12,"deployment_uuid":"old"}]}',
                ),
            ]
        )
        client = CoolifyClient("https://coolify.example.com", "token", transport=transport)

        result = client.configure_auto_deploy(
            "app-2",
            repository="acme/private-app",
            branch="main",
        )

        self.assertFalse(result["before"]["auto_deploy_enabled"])
        self.assertTrue(result["after"]["auto_deploy_enabled"])
        self.assertEqual(result["after"]["configured_branch"], "main")
        self.assertEqual(result["verification_baseline_id"], 12)
        patch_call = transport.calls[3]
        self.assertEqual(patch_call["method"], "PATCH")
        self.assertTrue(patch_call["url"].endswith("/api/v1/applications/app-2"))
        self.assertEqual(
            json.loads(patch_call["data"]),
            {"git_branch": "main", "is_auto_deploy_enabled": True},
        )

    def test_configure_auto_deploy_rejects_application_without_github_app(self):
        transport = FakeTransport(
            [
                (
                    200,
                    {},
                    b'{"git_repository":"acme/private-app","source_id":null}',
                )
            ]
        )
        client = CoolifyClient("https://coolify.example.com", "token", transport=transport)

        with self.assertRaisesRegex(ValueError, "not connected through a Coolify GitHub App"):
            client.configure_auto_deploy(
                "app-2",
                repository="acme/private-app",
                branch="main",
            )

        self.assertEqual(len(transport.calls), 1)

    def test_wait_for_webhook_deployment_ignores_manual_match_and_waits_for_webhook(self):
        commit = "a" * 40
        manual = {
            "id": 3,
            "deployment_uuid": "manual-1",
            "commit": commit,
            "status": "finished",
            "is_webhook": False,
            "is_api": True,
        }
        webhook = {
            "id": 4,
            "deployment_uuid": "webhook-1",
            "application_name": "private-app",
            "commit": commit,
            "status": "in_progress",
            "is_webhook": True,
            "is_api": False,
        }
        finished = {**webhook, "status": "finished"}
        old_webhook = {
            "id": 2,
            "deployment_uuid": "webhook-old",
            "commit": commit,
            "status": "finished",
            "is_webhook": True,
        }
        transport = FakeTransport(
            [
                (
                    200,
                    {},
                    json.dumps(
                        {"count": 2, "deployments": [manual, old_webhook]}
                    ).encode(),
                ),
                (
                    200,
                    {},
                    json.dumps({"count": 2, "deployments": [webhook, manual]}).encode(),
                ),
                (200, {}, json.dumps(finished).encode()),
            ]
        )
        sleeps = []
        client = CoolifyClient(
            "https://coolify.example.com",
            "token",
            transport=transport,
            sleeper=sleeps.append,
        )

        result = client.wait_for_webhook_deployment(
            "app-2",
            commit=commit,
            after_id=3,
            timeout=10,
            interval=0.01,
        )

        self.assertEqual(result["deployment_uuid"], "webhook-1")
        self.assertEqual(result["commit"], commit)
        self.assertTrue(result["is_webhook"])
        self.assertEqual(sleeps, [0.01])
        self.assertIn("take=100", transport.calls[0]["url"])
        self.assertTrue(
            transport.calls[2]["url"].endswith("/api/v1/deployments/webhook-1")
        )

    def test_wait_for_webhook_deployment_rejects_failed_terminal_state(self):
        commit = "b" * 40
        failed = {
            "id": 5,
            "deployment_uuid": "webhook-2",
            "commit": commit,
            "status": "failed",
            "is_webhook": True,
        }
        transport = FakeTransport(
            [
                (
                    200,
                    {},
                    json.dumps({"count": 1, "deployments": [failed]}).encode(),
                ),
                (200, {}, json.dumps(failed).encode()),
            ]
        )
        client = CoolifyClient("https://coolify.example.com", "token", transport=transport)

        with self.assertRaisesRegex(CoolifyApiError, "terminal status failed"):
            client.wait_for_webhook_deployment(
                "app-2",
                commit=commit,
                after_id=0,
                timeout=10,
                interval=0.01,
            )

    def test_github_repository_slug_accepts_https_ssh_and_short_forms(self):
        self.assertEqual(
            github_repository_slug("https://github.com/acme/private-app.git"),
            "acme/private-app",
        )
        self.assertEqual(
            github_repository_slug("git@github.com:acme/private-app.git"),
            "acme/private-app",
        )
        self.assertEqual(github_repository_slug("acme/private-app"), "acme/private-app")

    def test_redaction_masks_secret_values_but_keeps_env_keys(self):
        result = redact(
            {
                "key": "DATABASE_URL",
                "value": "postgres://secret",
                "nested": {"api_token": "token-value"},
            }
        )

        self.assertEqual(result["key"], "DATABASE_URL")
        self.assertEqual(result["value"], "***MASKED***")
        self.assertEqual(result["nested"]["api_token"], "***MASKED***")

    def test_redaction_keeps_validation_error_messages(self):
        result = redact(
            {
                "message": "Validation failed.",
                "errors": {"dockerfile": "The dockerfile field must be base64 encoded."},
            }
        )

        self.assertEqual(
            result["errors"]["dockerfile"],
            "The dockerfile field must be base64 encoded.",
        )

    def test_deployment_uuid_supports_deployments_array(self):
        self.assertEqual(
            deployment_uuid({"deployments": [{"deployment_uuid": "dep-1"}]}),
            "dep-1",
        )

    def test_credentials_reuse_existing_codex_coolify_config(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            access_key = "COOLIFY_ACCESS_" + "TOKEN"
            fixture = "".join(("existing", "-", "fixture"))
            config.write_text(
                f"""
[mcp_servers.coolify.env]
COOLIFY_BASE_URL = "https://coolify.example.com"
{access_key} = "{fixture}"
""".strip(),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"CODEX_CONFIG_PATH": str(config)},
                clear=True,
            ):
                base_url, token = credentials(None)

        self.assertEqual(base_url, "https://coolify.example.com")
        self.assertEqual(token, fixture)

    def test_environment_credentials_override_codex_config(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            access_key = "COOLIFY_ACCESS_" + "TOKEN"
            api_env_name = "COOLIFY_API_" + "TOKEN"
            config_fixture = "".join(("config", "-", "fixture"))
            env_fixture = "".join(("environment", "-", "fixture"))
            config.write_text(
                f"""
[mcp_servers.coolify.env]
COOLIFY_BASE_URL = "https://config.example.com"
{access_key} = "{config_fixture}"
""".strip(),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "CODEX_CONFIG_PATH": str(config),
                    "COOLIFY_BASE_URL": "https://env.example.com",
                    api_env_name: env_fixture,
                },
                clear=True,
            ):
                base_url, token = credentials(None)

        self.assertEqual(base_url, "https://env.example.com")
        self.assertEqual(token, env_fixture)


if __name__ == "__main__":
    unittest.main()
