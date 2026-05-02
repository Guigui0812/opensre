"""Shared Helm integration helpers.

Provides configuration, connectivity validation, and read-only diagnostic
commands for Helm releases. All operations are production-safe: read-only,
timeouts enforced, result sizes capped.

Helm is the Kubernetes package manager. This integration enables investigation
of incidents caused by chart changes, bad values, failed upgrades, or drift
between expected and deployed release state.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Any

from pydantic import Field, field_validator

from app.integrations._validators import normalize_str
from app.strict_config import StrictConfigModel

logger = logging.getLogger(__name__)

# Defaults
DEFAULT_HELM_NAMESPACE = "default"
DEFAULT_HELM_TIMEOUT_SECONDS = 30
DEFAULT_HELM_MAX_RESULTS = 50

class HelmConfig(StrictConfigModel):
    """Normalized Helm connection settings."""

    kubeconfig: str = ""
    kube_context: str = ""
    namespace: str = DEFAULT_HELM_NAMESPACE
    helm_path: str = "helm"
    timeout_seconds: float = Field(default=DEFAULT_HELM_TIMEOUT_SECONDS, gt=0)
    max_results: int = Field(default=DEFAULT_HELM_MAX_RESULTS, gt=0, le=200)
    integration_id: str = ""

    _normalize_kubeconfig = field_validator("kubeconfig", mode="before")(
        normalize_str()
    )
    _normalize_kube_context = field_validator("kube_context", mode="before")(
        normalize_str()
    )
    _normalize_namespace = field_validator("namespace", mode="before")(
        normalize_str()
    )
    _normalize_helm_path = field_validator("helm_path", mode="before")(
        normalize_str()
    )

    @property
    def is_configured(self) -> bool:
        return bool(self.helm_path)

@dataclass(frozen=True)
class HelmValidationResult:
    """Result of validating a Helm integration."""

    ok: bool
    detail: str

def build_helm_config(raw: dict[str, Any] | None) -> HelmConfig:
    """Build a normalized Helm config object from env/store data."""
    return HelmConfig.model_validate(raw or {})

def helm_config_from_env() -> HelmConfig | None:
    """Load a Helm config from env vars."""
    kubeconfig = os.getenv("HELM_KUBECONFIG", "")
    kube_context = os.getenv("HELM_KUBE_CONTEXT", "")
    namespace = os.getenv("HELM_NAMESPACE", DEFAULT_HELM_NAMESPACE)
    helm_path = os.getenv("HELM_PATH", "helm")

    # Only create config if helm is available
    if not _helm_binary_available(helm_path):
        return None

    return HelmConfig(
        kubeconfig=kubeconfig,
        kube_context=kube_context,
        namespace=namespace,
        helm_path=helm_path,
    )

def _helm_binary_available(helm_path: str = "helm") -> bool:
    """Check if helm binary is available and executable."""
    try:
        result = subprocess.run(
            [helm_path, "version", "--client"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False

def _run_helm_command(
    config: HelmConfig,
    args: list[str],
    namespace: str | None = None
) -> tuple[bool, str, str]:
    """Run a helm command and return results (success, stdout, stderr).
    """
    cmd = [config.helm_path]

    if config.kubeconfig:
        cmd.extend(["--kubeconfig", config.kubeconfig])

    if config.kube_context:
        cmd.extend(["--kube-context", config.kube_context])

    ns = namespace or config.namespace
    if ns and ns != DEFAULT_HELM_NAMESPACE:
        cmd.extend(["--namespace", ns])

    cmd.extend(args)

    timeout = int(config.timeout_seconds)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return (
            result.returncode == 0,
            result.stdout.strip(),
            result.stderr.strip(),
        )
    except subprocess.TimeoutExpired:
        logger.error(f"[helm] Command timed out after {timeout} seconds")
        return False, "", f"Command timed out after {timeout} seconds"
    except FileNotFoundError:
        logger.error(f"[helm] binary not found at: {config.helm_path}")
        return False, "", f"Helm binary not found at: {config.helm_path}"
    except OSError as e:
        logger.error(f"[helm] Failed to run helm command: {e}")
        return False, "", f"Failed to run helm command: {e}"


def resolve_helm_config(
    kubeconfig: str | None = None,
    kube_context: str | None = None,
    namespace: str | None = None,
) -> HelmConfig:
    """Build a Helm config from provided params, resolving from store or env.

    The LLM supplies only identifying params (kubeconfig, kube_context, namespace).
    Other settings (helm_path, timeout, max_results) come from stored config or defaults.
    """
    return HelmConfig(
        kubeconfig=kubeconfig or "",
        kube_context=kube_context or "",
        namespace=namespace or DEFAULT_HELM_NAMESPACE,
        helm_path=os.getenv("HELM_PATH", "helm"),
    )


def validate_helm_config(config: HelmConfig) -> HelmValidationResult:
    """Validate Helm configuration by running a simple version check."""
    if not config.helm_path:
        return HelmValidationResult(
            ok=False,
            detail="Helm path is required.",
        )

    # Check if helm binary exists and is executable
    if not _helm_binary_available(config.helm_path):
        return HelmValidationResult(
            ok=False,
            detail=f"Helm binary not found or not executable at: {config.helm_path}",
        )

    # Try to get helm version
    success, stdout, stderr = _run_helm_command(config, ["version", "--client"])
    if not success:
        return HelmValidationResult(
            ok=False,
            detail=f"Failed to get Helm version: {stderr or 'Unknown error'}",
        )

    # Extract version from output
    version = ""
    for line in stdout.split("\n"):
        if "v3." in line or "Version:" in line:
            version = line.strip()
            break

    return HelmValidationResult(
        ok=True,
        detail=f"Helm {version} is available and configured.",
    )

def helm_diff_plugin_is_available(config: HelmConfig) -> bool:
    """Check if Helm diff plugin is installed."""

    if not config.is_configured:
        return {"source": "helm", "available": False, "error": "Not configured."}

    success, stdout, stderr = _run_helm_command(
        config,
        ["plugin", "list"]
    )

    if not success:
        return {
            "source": "helm",
            "available": False,
            "error": f"Failed to list plugins: {stderr}",
        }

    try:
        plugins_lines = stdout.split("\n")
        plugins_lines.pop()
        plugins_lines.pop(0)
        for plugin in plugins_lines:
           plugin_name = plugin.split("\t")
           if "diff" in plugin_name:
               return True

        return False
    except Exception as e:
        logger.error(f"[helm] There has been an error when parsing plugins: {e}")

def helm_is_available(sources: dict[str, dict]) -> bool:
    """Check if Helm integration identifying params are present."""
    helm = sources.get("helm", {})
    # Helm is available if we have any configuration
    return bool(helm)


def helm_extract_params(sources: dict[str, dict]) -> dict[str, Any]:
    """Extract Helm identifying params from resolved integrations."""
    helm = sources.get("helm", {})
    return {
        "kubeconfig": str(helm.get("kubeconfig", "")).strip() or None,
        "kube_context": str(helm.get("kube_context", "")).strip() or None,
        "namespace": str(helm.get("namespace", DEFAULT_HELM_NAMESPACE)).strip(),
    }


def get_releases(config: HelmConfig) -> dict[str, Any]:
    """List all Helm releases in the configured namespace.

    Returns a list of releases with their status, chart, version, and revision.
    """
    if not config.is_configured:
        return {"source": "helm", "available": False, "error": "Not configured."}

    success, stdout, stderr = _run_helm_command(
        config,
        ["list", "--all", "--output", "json"],
    )

    if not success:
        return {
            "source": "helm",
            "available": False,
            "error": f"Failed to list releases: {stderr}",
        }

    try:
        releases = json.loads(stdout)
        return {
            "source": "helm",
            "available": True,
            "namespace": config.namespace,
            "total_releases": len(releases),
            "releases": releases,
        }
    except json.JSONDecodeError:
        return {
            "source": "helm",
            "available": False,
            "error": f"Failed to parse Helm output: {stdout}",
        }


def get_release_status(
    config: HelmConfig,
    release_name: str,
    namespace: str | None = None,
) -> dict[str, Any]:
    """Get the status of a specific Helm release.

    Returns detailed information about the release including:
    - Status (deployed, failed, pending, etc.)
    - Chart metadata
    - Deployed resources
    - Notes (if any)
    """
    if not config.is_configured:
        return {"source": "helm", "available": False, "error": "Not configured."}

    ns = namespace or config.namespace
    success, stdout, stderr = _run_helm_command(
        config,
        ["status", release_name, "--output", "json"],
        namespace=ns,
    )

    if not success:
        return {
            "source": "helm",
            "available": False,
            "error": f"Failed to get release status: {stderr}",
            "release_name": release_name,
            "namespace": ns,
        }

    try:
        status_data = json.loads(stdout)
        return {
            "source": "helm",
            "available": True,
            "release_name": release_name,
            "namespace": ns,
            "status": status_data,
        }
    except json.JSONDecodeError:
        # Fall back to text parsing
        return {
            "source": "helm",
            "available": True,
            "release_name": release_name,
            "namespace": ns,
            "status_text": stdout,
        }


def get_release_history(
    config: HelmConfig,
    release_name: str,
    namespace: str | None = None,
    max_history: int | None = None,
) -> dict[str, Any]:
    """Get the revision history of a Helm release.

    Returns the list of revisions with:
    - Revision number
    - Update timestamp
    - Status
    - Chart version
    - Description
    """
    if not config.is_configured:
        return {"source": "helm", "available": False, "error": "Not configured."}

    ns = namespace or config.namespace
    effective_max = max_history or config.max_results

    success, stdout, stderr = _run_helm_command(
        config,
        ["history", release_name, "--output", "json", "--max", str(effective_max)],
        namespace=ns,
    )

    if not success:
        return {
            "source": "helm",
            "available": False,
            "error": f"Failed to get release history: {stderr}",
            "release_name": release_name,
            "namespace": ns,
        }

    try:
        history = json.loads(stdout)
        return {
            "source": "helm",
            "available": True,
            "release_name": release_name,
            "namespace": ns,
            "history": history,
            "total_revisions": len(history),
        }
    except json.JSONDecodeError:
        return {
            "source": "helm",
            "available": False,
            "error": f"Failed to parse release history: {stdout}",
            "release_name": release_name,
            "namespace": ns,
        }


def get_release_values(
    config: HelmConfig,
    release_name: str,
    namespace: str | None = None,
    all_values: bool = False,
) -> dict[str, Any]:
    """Get the values used in a Helm release."""
    if not config.is_configured:
        return {"source": "helm", "available": False, "error": "Not configured."}

    ns = namespace or config.namespace
    cmd = ["get", "values", release_name, "--output", "json"]
    if all_values:
        cmd.append("--all")

    success, stdout, stderr = _run_helm_command(
        config,
        cmd,
        namespace=ns,
    )

    if not success:
        return {
            "source": "helm",
            "available": False,
            "error": f"Failed to get release values: {stderr}",
            "release_name": release_name,
            "namespace": ns,
        }

    try:
        values = json.loads(stdout)
        return {
            "source": "helm",
            "available": True,
            "release_name": release_name,
            "namespace": ns,
            "values": values,
            "all_values": all_values,
        }
    except json.JSONDecodeError:
        return {
            "source": "helm",
            "available": False,
            "error": f"Failed to parse release values: {stdout}",
            "release_name": release_name,
            "namespace": ns,
        }


def get_manifest(
    config: HelmConfig,
    release_name: str,
    namespace: str | None = None,
) -> dict[str, Any]:
    """Get the rendered manifest for a Helm release.

    Returns the full Kubernetes manifest that was generated from the chart.
    """
    if not config.is_configured:
        return {"source": "helm", "available": False, "error": "Not configured."}

    ns = namespace or config.namespace

    success, stdout, stderr = _run_helm_command(
        config,
        ["get", "manifest", release_name],
        namespace=ns,
    )

    if not success:
        return {
            "source": "helm",
            "available": False,
            "error": f"Failed to get manifest: {stderr}",
            "release_name": release_name,
            "namespace": ns,
        }

    return {
        "source": "helm",
        "available": True,
        "release_name": release_name,
        "namespace": ns,
        "manifest": stdout,
    }


def get_chart_metadata(
    config: HelmConfig,
    release_name: str,
    namespace: str | None = None,
) -> dict[str, Any]:
    """Get metadata about the chart used for a release.

    Returns:
    - Chart name and version
    - App version
    - Description
    - Home URL
    - Sources
    - Maintainers
    - Dependencies
    """
    if not config.is_configured:
        return {"source": "helm", "available": False, "error": "Not configured."}

    ns = namespace or config.namespace

    # Get the release info to extract chart metadata
    success, stdout, stderr = _run_helm_command(
        config,
        ["get", "all", release_name, "--output", "json"],
        namespace=ns,
    )

    if not success:
        return {
            "source": "helm",
            "available": False,
            "error": f"Failed to get release info: {stderr}",
            "release_name": release_name,
            "namespace": ns,
        }

    try:
        release_info = json.loads(stdout)

        chart_info = release_info.get("chart", {})
        return {
            "source": "helm",
            "available": True,
            "release_name": release_name,
            "namespace": ns,
            "chart": {
                "name": chart_info.get("name", ""),
                "version": chart_info.get("version", ""),
                "app_version": chart_info.get("app_version", ""),
            },
            "metadata": release_info.get("info", {}),
        }
    except json.JSONDecodeError:
        return {
            "source": "helm",
            "available": False,
            "error": f"Failed to parse release info: {stdout}",
            "release_name": release_name,
            "namespace": ns,
        }


def get_notes(
    config: HelmConfig,
    release_name: str,
    namespace: str | None = None,
) -> dict[str, Any]:
    """Get the notes for a Helm release.

    Notes are typically displayed after a release is installed/upgraded
    and contain information about what was deployed and next steps.
    """
    if not config.is_configured:
        return {"source": "helm", "available": False, "error": "Not configured."}

    ns = namespace or config.namespace

    success, stdout, stderr = _run_helm_command(
        config,
        ["get", "notes", release_name],
        namespace=ns,
    )

    if not success:
        return {
            "source": "helm",
            "available": False,
            "error": f"Failed to get notes: {stderr}",
            "release_name": release_name,
            "namespace": ns,
        }

    return {
        "source": "helm",
        "available": True,
        "release_name": release_name,
        "namespace": ns,
        "notes": stdout,
    }


def check_drift(
    config: HelmConfig,
    release_name: str,
    namespace: str | None = None,
) -> dict[str, Any]:
    """Check if a Helm release has drifted from its expected state.

    This compares the current live state with the state that would be
    generated by the current chart and values.

    Note: This requires Helm 3.11+ with the diff plugin or similar functionality.
    """
    if not config.is_configured:
        return {"source": "helm", "available": False, "error": "Not configured."}

    if not helm_diff_plugin_is_available():
        logger.error("[helm] Helm Diff plugin is not available.")
        return  {"source": "helm", "available": False, "error": "Helm Diff plugin is not available."}

    ns = namespace or config.namespace

    # Try using helm diff plugin if available
    success, stdout, stderr = _run_helm_command(
        config,
        ["diff", "upgrade", release_name],
        namespace=ns,
    )

    if success:
        return {
            "source": "helm",
            "available": True,
            "release_name": release_name,
            "namespace": ns,
            "has_drift": bool(stdout.strip()),
            "diff": stdout,
        }

    # If diff plugin is not available, we can't check drift
    return {
        "source": "helm",
        "available": True,
        "release_name": release_name,
        "namespace": ns,
        "has_drift": None,
        "error": "Helm diff plugin not available, cannot check drift",
    }
