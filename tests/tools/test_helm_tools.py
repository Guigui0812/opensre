"""Tests for Helm investigation tools."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.services.helm import (
    helm_extract_params,
    helm_is_available,
)


class _FakeHelmSubprocess:
    """Mock subprocess for Helm command testing."""

    def __init__(self, results: dict[str, tuple[bool, str, str]] | None = None) -> None:
        self.results: dict[str, tuple[bool, str, str]] = results or {}
        self.default_result: tuple[bool, str, str] = (True, "{}", "")

    def __call__(self, cmd: list[str], **kwargs: Any) -> MagicMock:
        result = MagicMock()

        # Build a key from the command for lookup
        cmd_key = " ".join(cmd)
        success, stdout, stderr = self.results.get(cmd_key, self.default_result)

        result.returncode = 0 if success else 1
        result.stdout = stdout
        result.stderr = stderr
        result.capture_output = MagicMock(return_value=True)
        result.text = True
        result.timeout = kwargs.get("timeout", 30)

        return result


class TestHelmToolAvailability:
    """Tests for Helm tool availability."""

    def test_helm_list_releases_tool_availability(self) -> None:
        from app.tools.HelmListReleasesTool import helm_list_releases

        # Tool should be available when helm source is present
        sources = {"helm": {"kubeconfig": "/path/to/config"}}
        assert helm_is_available(sources) is True

        # Tool should not be available without helm source
        sources_empty = {}
        assert helm_is_available(sources_empty) is False

    def test_helm_list_releases_tool_extract_params(self) -> None:
        sources = {
            "helm": {
                "kubeconfig": "/path/to/config",
                "kube_context": "my-context",
                "namespace": "production",
            }
        }
        params = helm_extract_params(sources)

        assert params["kubeconfig"] == "/path/to/config"
        assert params["kube_context"] == "my-context"
        assert params["namespace"] == "production"

    def test_helm_check_drift_tool_availability(self) -> None:
        sources = {"helm": {"helm_path": "helm"}}
        assert helm_is_available(sources) is True

        sources_empty = {}
        assert helm_is_available(sources_empty) is False

    def test_helm_release_status_tool_availability(self) -> None:
        sources = {"helm": {"helm_path": "helm"}}
        assert helm_is_available(sources) is True

    def test_helm_release_history_tool_availability(self) -> None:
        sources = {"helm": {"helm_path": "helm"}}
        assert helm_is_available(sources) is True

    def test_helm_release_values_tool_availability(self) -> None:
        sources = {"helm": {"helm_path": "helm"}}
        assert helm_is_available(sources) is True

    def test_helm_release_manifest_tool_availability(self) -> None:
        sources = {"helm": {"helm_path": "helm"}}
        assert helm_is_available(sources) is True

    def test_helm_chart_metadata_tool_availability(self) -> None:
        sources = {"helm": {"helm_path": "helm"}}
        assert helm_is_available(sources) is True


class TestHelmListReleasesTool:
    """Tests for helm_list_releases tool."""

    def test_list_releases_returns_releases(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.tools.HelmListReleasesTool import helm_list_releases

        # Mock releases list output
        mock_releases = [
            {
                "name": "my-app",
                "namespace": "production",
                "revision": "1",
                "updated": "2024-01-01 00:00:00",
                "status": "deployed",
                "chart": "my-app-1.0.0",
                "app_version": "1.0.0",
            }
        ]
        mock_output = json.dumps(mock_releases)

        def mock_run(cmd: list[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            if "list" in cmd and "--output" in cmd and "json" in cmd:
                result.returncode = 0
                result.stdout = mock_output
                result.stderr = ""
            else:
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
            return result

        monkeypatch.setattr("app.services.helm.client.subprocess.run", mock_run)

        result = helm_list_releases(namespace="production")

        assert result["source"] == "helm"
        assert result["available"] is True
        assert result["namespace"] == "production"
        assert len(result["releases"]) == 1
        assert result["releases"][0]["name"] == "my-app"

    def test_list_releases_with_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.tools.HelmListReleasesTool import helm_list_releases

        def mock_run(cmd: list[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            # Helm binary check (version --client) succeeds
            if "version" in cmd and "--client" in cmd:
                result.returncode = 0
                result.stdout = "version: v3.12.0"
                result.stderr = ""
            # Helm list command fails
            elif "list" in cmd:
                result.returncode = 1
                result.stdout = ""
                result.stderr = "Error: unable to list releases"
            else:
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
            return result

        monkeypatch.setattr("app.services.helm.client.subprocess.run", mock_run)

        result = helm_list_releases()

        assert result["source"] == "helm"
        assert result["available"] is False
        assert "Error" in result["error"]

    def test_list_releases_with_custom_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.tools.HelmListReleasesTool import helm_list_releases

        mock_output = json.dumps([])

        def mock_run(cmd: list[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            result.stdout = mock_output
            result.stderr = ""
            return result

        monkeypatch.setattr("app.services.helm.client.subprocess.run", mock_run)

        result = helm_list_releases(
            namespace="custom-ns",
            kubeconfig="/path/to/config",
            kube_context="my-context",
        )

        assert result["source"] == "helm"
        assert result["available"] is True
        assert result["namespace"] == "custom-ns"


class TestHelmReleaseStatusTool:
    """Tests for helm_release_status tool."""

    def test_release_status_returns_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.tools.HelmReleaseStatusTool import helm_release_status

        mock_status = {
            "name": "my-app",
            "namespace": "production",
            "revision": "1",
            "status": "deployed",
            "chart": "my-app-1.0.0",
        }
        mock_output = json.dumps(mock_status)

        def mock_run(cmd: list[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            if "status" in cmd and "--output" in cmd and "json" in cmd:
                result.returncode = 0
                result.stdout = mock_output
                result.stderr = ""
            else:
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
            return result

        monkeypatch.setattr("app.services.helm.client.subprocess.run", mock_run)

        result = helm_release_status(release_name="my-app", namespace="production")

        assert result["source"] == "helm"
        assert result["available"] is True
        assert result["release_name"] == "my-app"
        assert result["status"]["status"] == "deployed"


class TestHelmReleaseHistoryTool:
    """Tests for helm_release_history tool."""

    def test_release_history_returns_history(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.tools.HelmReleaseHistoryTool import helm_release_history

        mock_history = [
            {
                "revision": 1,
                "updated": "2024-01-01 00:00:00",
                "status": "deployed",
                "chart": "my-app-1.0.0",
                "description": "Initial install",
            },
            {
                "revision": 2,
                "updated": "2024-01-02 00:00:00",
                "status": "deployed",
                "chart": "my-app-1.1.0",
                "description": "Upgrade",
            },
        ]
        mock_output = json.dumps(mock_history)

        def mock_run(cmd: list[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            if "history" in cmd and "--output" in cmd and "json" in cmd:
                result.returncode = 0
                result.stdout = mock_output
                result.stderr = ""
            else:
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
            return result

        monkeypatch.setattr("app.services.helm.client.subprocess.run", mock_run)

        result = helm_release_history(release_name="my-app", max_history=10)

        assert result["source"] == "helm"
        assert result["available"] is True
        assert result["total_revisions"] == 2


class TestHelmReleaseValuesTool:
    """Tests for helm_release_values tool."""

    def test_release_values_returns_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.tools.HelmReleaseValuesTool import helm_release_values

        mock_values = {"replicaCount": 3, "image": "nginx:latest"}
        mock_output = json.dumps(mock_values)

        def mock_run(cmd: list[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            if "get" in cmd and "values" in cmd and "--output" in cmd and "json" in cmd:
                result.returncode = 0
                result.stdout = mock_output
                result.stderr = ""
            else:
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
            return result

        monkeypatch.setattr("app.services.helm.client.subprocess.run", mock_run)

        result = helm_release_values(release_name="my-app")

        assert result["source"] == "helm"
        assert result["available"] is True
        assert result["values"] == mock_values


class TestHelmReleaseManifestTool:
    """Tests for helm_release_manifest tool."""

    def test_release_manifest_returns_manifest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.tools.HelmReleaseManifestTool import helm_release_manifest

        mock_manifest = """---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
  namespace: production
"""

        def mock_run(cmd: list[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            if "get" in cmd and "manifest" in cmd:
                result.returncode = 0
                result.stdout = mock_manifest
                result.stderr = ""
            else:
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
            return result

        monkeypatch.setattr("app.services.helm.client.subprocess.run", mock_run)

        result = helm_release_manifest(release_name="my-app")

        assert result["source"] == "helm"
        assert result["available"] is True
        assert "Deployment" in result["manifest"]


class TestHelmChartMetadataTool:
    """Tests for helm_chart_metadata tool."""

    def test_chart_metadata_returns_metadata(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.tools.HelmChartMetadataTool import helm_chart_metadata

        mock_info = {
            "chart": {
                "name": "my-app",
                "version": "1.0.0",
                "app_version": "1.0.0",
            },
            "info": {
                "description": "My application chart",
                "home": "https://example.com",
            },
        }
        mock_output = json.dumps(mock_info)

        def mock_run(cmd: list[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            if (
                ("get" in cmd and "metadata" in cmd or "all" in cmd)
                and "--output" in cmd
                and "json" in cmd
            ):
                result.returncode = 0
                result.stdout = mock_output
                result.stderr = ""
            else:
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
            return result

        monkeypatch.setattr("app.services.helm.client.subprocess.run", mock_run)

        result = helm_chart_metadata(release_name="my-app")

        assert result["source"] == "helm"
        assert result["available"] is True
        assert result["chart"]["name"] == "my-app"
        assert result["chart"]["version"] == "1.0.0"


class TestHelmCheckDiffTool:
    """Tests for helm_check_diff tool."""

    def test_check_diff_with_plugin_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.tools.HelmCheckDiffTool import helm_check_diff

        def mock_run(cmd: list[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            if "plugin" in cmd and "list" in cmd:
                result.returncode = 0
                result.stdout = "NAME\tVERSION\tDIFF\t\nhelm-diff\t3.8.0\t\t"
                result.stderr = ""
            elif "diff" in cmd and "upgrade" in cmd:
                result.returncode = 0
                result.stdout = "# No differences found"
                result.stderr = ""
            else:
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
            return result

        monkeypatch.setattr("app.services.helm.client.subprocess.run", mock_run)

        result = helm_check_diff(release_name="my-app")

        assert result["source"] == "helm"
        assert result["available"] is True
        assert result["has_diff"] is None

    def test_check_diff_without_plugin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.tools.HelmCheckDiffTool import helm_check_diff

        def mock_run(cmd: list[str], **kwargs: Any) -> MagicMock:
            result = MagicMock()
            if "plugin" in cmd and "list" in cmd:
                result.returncode = 0
                result.stdout = "NAME\tVERSION\t\n"  # No plugins
                result.stderr = ""
            elif "diff" in cmd and "upgrade" in cmd:
                result.returncode = 1
                result.stdout = ""
                result.stderr = "Error: plugin diff not found"
            else:
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
            return result

        monkeypatch.setattr("app.services.helm.client.subprocess.run", mock_run)

        result = helm_check_diff(release_name="my-app")

        assert result["source"] == "helm"
        assert result["available"] is True
        # has_diff should be None or error message about plugin
        assert result.get("has_diff") is None or "not available" in result.get("error", "").lower()
