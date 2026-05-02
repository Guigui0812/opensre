"""Unit tests for the Helm integration module.

Tests cover:
- HelmConfig model validation and normalization
- build_helm_config and helm_config_from_env helpers
- helm_is_available and helm_extract_params
- Classification in the catalog
- Registry integration
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.integrations._catalog_impl import _classify_service_instance, load_env_integrations
from app.integrations.catalog import resolve_effective_integrations
from app.integrations.helm import (
    DEFAULT_HELM_MAX_RESULTS,
    DEFAULT_HELM_NAMESPACE,
    DEFAULT_HELM_TIMEOUT_SECONDS,
    HelmConfig,
    HelmValidationResult,
    build_helm_config,
    helm_config_from_env,
    helm_extract_params,
    helm_is_available,
    validate_helm_config,
)
from app.integrations.registry import INTEGRATION_SPECS, service_key


class TestHelmConfig:
    """Tests for HelmConfig model."""

    def test_defaults(self) -> None:
        config = HelmConfig()
        assert config.kubeconfig == ""
        assert config.kube_context == ""
        assert config.namespace == DEFAULT_HELM_NAMESPACE
        assert config.helm_path == "helm"
        assert config.timeout_seconds == DEFAULT_HELM_TIMEOUT_SECONDS
        assert config.max_results == DEFAULT_HELM_MAX_RESULTS
        assert config.integration_id == ""
        assert config.is_configured is True  # helm_path has default "helm"

    def test_is_configured_with_empty_helm_path(self) -> None:
        config = HelmConfig(helm_path="")
        assert config.is_configured is False

    def test_is_configured_with_custom_helm_path(self) -> None:
        config = HelmConfig(helm_path="/usr/local/bin/helm3")
        assert config.is_configured is True

    def test_normalize_kubeconfig_strips_whitespace(self) -> None:
        config = HelmConfig(kubeconfig="  /path/to/kubeconfig  ")
        assert config.kubeconfig == "/path/to/kubeconfig"

    def test_normalize_kubeconfig_none(self) -> None:
        config = HelmConfig(kubeconfig=None)  # type: ignore[arg-type]
        assert config.kubeconfig == ""

    def test_normalize_kube_context_strips_whitespace(self) -> None:
        config = HelmConfig(kube_context="  my-context  ")
        assert config.kube_context == "my-context"

    def test_normalize_namespace_strips_whitespace(self) -> None:
        config = HelmConfig(namespace="  my-namespace  ")
        assert config.namespace == "my-namespace"

    def test_normalize_namespace_default(self) -> None:
        config = HelmConfig(namespace=None)  # type: ignore[arg-type]
        assert config.namespace == DEFAULT_HELM_NAMESPACE

    def test_normalize_helm_path_strips_whitespace(self) -> None:
        config = HelmConfig(helm_path="  /usr/bin/helm  ")
        assert config.helm_path == "/usr/bin/helm"

    def test_normalize_helm_path_none(self) -> None:
        config = HelmConfig(helm_path=None)  # type: ignore[arg-type]
        assert config.helm_path == "helm"

    def test_timeout_seconds_default(self) -> None:
        config = HelmConfig()
        assert config.timeout_seconds == DEFAULT_HELM_TIMEOUT_SECONDS

    def test_timeout_seconds_zero_raises(self) -> None:
        with pytest.raises(ValidationError):
            HelmConfig(timeout_seconds=0)

    def test_timeout_seconds_negative_raises(self) -> None:
        with pytest.raises(ValidationError):
            HelmConfig(timeout_seconds=-1)

    def test_max_results_default(self) -> None:
        config = HelmConfig()
        assert config.max_results == DEFAULT_HELM_MAX_RESULTS

    def test_max_results_upper_boundary(self) -> None:
        config = HelmConfig(max_results=200)
        assert config.max_results == 200

    def test_max_results_over_limit_raises(self) -> None:
        with pytest.raises(ValidationError):
            HelmConfig(max_results=201)

    def test_max_results_zero_raises(self) -> None:
        with pytest.raises(ValidationError):
            HelmConfig(max_results=0)

    def test_custom_values(self) -> None:
        config = HelmConfig(
            kubeconfig="/home/user/.kube/config",
            kube_context="my-cluster",
            namespace="production",
            helm_path="/usr/local/bin/helm3",
            timeout_seconds=60,
            max_results=100,
            integration_id="helm-123",
        )
        assert config.kubeconfig == "/home/user/.kube/config"
        assert config.kube_context == "my-cluster"
        assert config.namespace == "production"
        assert config.helm_path == "/usr/local/bin/helm3"
        assert config.timeout_seconds == 60
        assert config.max_results == 100
        assert config.integration_id == "helm-123"


class TestBuildHelmConfig:
    """Tests for build_helm_config helper."""

    def test_from_dict(self) -> None:
        config = build_helm_config({
            "kubeconfig": "/path/to/config",
            "kube_context": "my-context",
            "namespace": "prod",
            "helm_path": "/usr/bin/helm",
        })
        assert config.kubeconfig == "/path/to/config"
        assert config.kube_context == "my-context"
        assert config.namespace == "prod"
        assert config.helm_path == "/usr/bin/helm"

    def test_from_none(self) -> None:
        config = build_helm_config(None)
        assert config.helm_path == "helm"
        assert config.namespace == DEFAULT_HELM_NAMESPACE

    def test_from_empty_dict(self) -> None:
        config = build_helm_config({})
        assert config.helm_path == "helm"
        assert config.is_configured is True

    def test_strips_whitespace(self) -> None:
        config = build_helm_config({
            "kubeconfig": "  /path  ",
            "kube_context": "  ctx  ",
            "namespace": "  ns  ",
            "helm_path": "  /usr/bin/helm  ",
        })
        assert config.kubeconfig == "/path"
        assert config.kube_context == "ctx"
        assert config.namespace == "ns"
        assert config.helm_path == "/usr/bin/helm"


class TestHelmConfigFromEnv:
    """Tests for helm_config_from_env helper."""

    def test_returns_none_when_helm_not_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def mock_subprocess_run(*args: any, **kwargs: any) -> MagicMock:
            result = MagicMock()
            result.returncode = 1
            return result

        monkeypatch.setattr(subprocess, "run", mock_subprocess_run)
        monkeypatch.setenv("HELM_PATH", "helm")
        assert helm_config_from_env() is None

    def test_returns_config_when_helm_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def mock_subprocess_run(*args: any, **kwargs: any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            return result

        monkeypatch.setattr(subprocess, "run", mock_subprocess_run)
        monkeypatch.setenv("HELM_KUBECONFIG", "/path/to/config")
        monkeypatch.setenv("HELM_KUBE_CONTEXT", "my-context")
        monkeypatch.setenv("HELM_NAMESPACE", "production")
        monkeypatch.setenv("HELM_PATH", "/usr/bin/helm")

        config = helm_config_from_env()

        assert config is not None
        assert config.kubeconfig == "/path/to/config"
        assert config.kube_context == "my-context"
        assert config.namespace == "production"
        assert config.helm_path == "/usr/bin/helm"

    def test_uses_defaults_for_missing_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def mock_subprocess_run(*args: any, **kwargs: any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            return result

        monkeypatch.setattr(subprocess, "run", mock_subprocess_run)
        monkeypatch.delenv("HELM_KUBECONFIG", raising=False)
        monkeypatch.delenv("HELM_KUBE_CONTEXT", raising=False)
        monkeypatch.delenv("HELM_NAMESPACE", raising=False)
        monkeypatch.setenv("HELM_PATH", "helm")

        config = helm_config_from_env()

        assert config is not None
        assert config.kubeconfig == ""
        assert config.kube_context == ""
        assert config.namespace == DEFAULT_HELM_NAMESPACE
        assert config.helm_path == "helm"


class TestHelmValidationResult:
    """Tests for HelmValidationResult dataclass."""

    def test_ok_result(self) -> None:
        result = HelmValidationResult(ok=True, detail="Helm v3.12.0 is available")
        assert result.ok is True
        assert "v3.12.0" in result.detail

    def test_error_result(self) -> None:
        result = HelmValidationResult(ok=False, detail="Helm binary not found")
        assert result.ok is False
        assert result.detail == "Helm binary not found"

    def test_fields_are_frozen(self) -> None:
        result = HelmValidationResult(ok=True, detail="ok")
        with pytest.raises((AttributeError, TypeError)):
            result.ok = False  # type: ignore[misc]


class TestValidateHelmConfig:
    """Tests for validate_helm_config function."""

    def test_valid_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def mock_run(*args: any, **kwargs: any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            result.stdout = "v3.12.0+g7d012a5"
            result.stderr = ""
            return result

        config = HelmConfig(helm_path="helm")
        monkeypatch.setattr(subprocess, "run", mock_run)

        result = validate_helm_config(config)

        assert result.ok is True
        assert "v3.12.0" in result.detail

    def test_missing_helm_path(self) -> None:
        config = HelmConfig(helm_path="")
        result = validate_helm_config(config)

        assert result.ok is False
        assert "Helm path is required" in result.detail

    def test_helm_binary_not_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def mock_run(*args: any, **kwargs: any) -> MagicMock:
            raise FileNotFoundError("helm not found")

        config = HelmConfig(helm_path="/nonexistent/helm")
        monkeypatch.setattr(subprocess, "run", mock_run)

        result = validate_helm_config(config)

        assert result.ok is False
        assert "not found" in result.detail.lower() or "not executable" in result.detail.lower()


class TestHelmAvailability:
    """Tests for helm_is_available and helm_extract_params functions."""

    def test_helm_is_available_with_helm_source(self) -> None:
        sources = {"helm": {"kubeconfig": "/path/to/config"}}
        assert helm_is_available(sources) is True

    def test_helm_is_available_without_helm_source(self) -> None:
        sources = {"datadog": {"api_key": "test"}}
        assert helm_is_available(sources) is False

    def test_helm_is_available_with_empty_helm_source(self) -> None:
        sources = {"helm": {}}
        assert helm_is_available(sources) is True

    def test_helm_extract_params_with_full_config(self) -> None:
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

    def test_helm_extract_params_with_missing_values(self) -> None:
        sources = {"helm": {}}
        params = helm_extract_params(sources)

        assert params["kubeconfig"] is None
        assert params["kube_context"] is None
        assert params["namespace"] == DEFAULT_HELM_NAMESPACE

    def test_helm_extract_params_with_empty_strings(self) -> None:
        sources = {
            "helm": {
                "kubeconfig": "",
                "kube_context": "",
                "namespace": "",
            }
        }
        params = helm_extract_params(sources)

        assert params["kubeconfig"] is None
        assert params["kube_context"] is None
        assert params["namespace"] == DEFAULT_HELM_NAMESPACE

    def test_helm_extract_params_without_helm_source(self) -> None:
        sources = {}
        params = helm_extract_params(sources)

        assert params["kubeconfig"] is None
        assert params["kube_context"] is None
        assert params["namespace"] == DEFAULT_HELM_NAMESPACE


class TestHelmClassification:
    """Tests for Helm integration classification in the catalog."""

    def test_classify_helm_instance_with_full_credentials(self) -> None:
        credentials = {
            "kubeconfig": "/path/to/config",
            "kube_context": "my-context",
            "namespace": "production",
            "helm_path": "/usr/bin/helm",
        }

        flat_view, flat_key = _classify_service_instance("helm", credentials, record_id="helm-1")

        assert flat_key == "helm"
        assert flat_view["kubeconfig"] == "/path/to/config"
        assert flat_view["kube_context"] == "my-context"
        assert flat_view["namespace"] == "production"
        assert flat_view["helm_path"] == "/usr/bin/helm"
        assert flat_view["integration_id"] == "helm-1"

    def test_classify_helm_instance_with_minimal_credentials(self) -> None:
        credentials = {"helm_path": "helm"}

        flat_view, flat_key = _classify_service_instance("helm", credentials, record_id="helm-2")

        assert flat_key == "helm"
        assert flat_view["helm_path"] == "helm"
        assert flat_view["integration_id"] == "helm-2"


class TestHelmEnvIntegrations:
    """Tests for Helm loading from environment variables."""

    def test_load_env_integrations_includes_helm(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.integrations.catalog.load_integrations", lambda: [])
        monkeypatch.setenv("HELM_KUBECONFIG", "/path/to/config")
        monkeypatch.setenv("HELM_KUBE_CONTEXT", "my-context")
        monkeypatch.setenv("HELM_NAMESPACE", "production")
        monkeypatch.setenv("HELM_PATH", "/usr/bin/helm")

        integrations = load_env_integrations()

        helm_integrations = [i for i in integrations if i.get("service") == "helm"]
        assert len(helm_integrations) == 1
        assert helm_integrations[0]["credentials"]["kubeconfig"] == "/path/to/config"
        assert helm_integrations[0]["credentials"]["kube_context"] == "my-context"
        assert helm_integrations[0]["credentials"]["namespace"] == "production"

    def test_load_env_integrations_skips_helm_without_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.integrations.catalog.load_integrations", lambda: [])
        # No HELM_* env vars set

        integrations = load_env_integrations()

        helm_integrations = [i for i in integrations if i.get("service") == "helm"]
        assert len(helm_integrations) == 0


class TestHelmEffectiveIntegrations:
    """Tests for Helm in effective integrations resolution."""

    def test_resolve_effective_integrations_includes_helm_from_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("app.integrations.catalog.load_integrations", lambda: [])
        monkeypatch.setenv("HELM_KUBECONFIG", "/path/to/config")
        monkeypatch.setenv("HELM_PATH", "helm")

        effective = resolve_effective_integrations()

        assert "helm" in effective
        assert effective["helm"]["source"] == "local env"
        assert effective["helm"]["config"]["kubeconfig"] == "/path/to/config"


class TestHelmRegistry:
    """Tests for Helm in the integration registry."""

    def test_helm_in_registry(self) -> None:
        services = [spec.service for spec in INTEGRATION_SPECS]
        assert "helm" in services

    def test_helm_service_key(self) -> None:
        assert service_key("helm") == "helm"
        assert service_key("HELM") == "helm"
        assert service_key("  helm  ") == "helm"
