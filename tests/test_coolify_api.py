import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.coolify_api import CoolifyClient, credentials, deployment_uuid, redact


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
        )

        call = transport.calls[0]
        payload = json.loads(call["data"])
        self.assertTrue(call["url"].endswith("/api/v1/applications/private-github-app"))
        self.assertEqual(payload["github_app_uuid"], "github-app-1")
        self.assertEqual(payload["dockerfile_location"], "/Dockerfile")
        self.assertEqual(payload["git_branch"], "main")

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
