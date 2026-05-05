"""Shared Helm integration helpers.

Provides configuration, connectivity validation, and read-only diagnostic
commands for Helm releases. All operations are production-safe: read-only,
timeouts enforced, result sizes capped.

Helm is the Kubernetes package manager. This integration enables investigation
of incidents caused by chart changes, bad values, failed upgrades, or changes
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
HELM_DEFAULT_NAMESPACE = "default"
HELM_DEFAULT_TIMEOUT_SECONDS = 30
HELM_DEFAULT_MAX_RESULTS = 50


class HelmConfig(StrictConfigModel):
    """Normalized Helm connection settings."""

    kubeconfig: str = ""
    kube_context: str = ""
    namespace: str = HELM_DEFAULT_NAMESPACE
    helm_path: str = "helm"
    timeout_seconds: float = Field(default=HELM_DEFAULT_TIMEOUT_SECONDS, gt=0)
    max_results: int = Field(default=HELM_DEFAULT_MAX_RESULTS, gt=0, le=200)
    integration_id: str = ""

    _normalize_kubeconfig = field_validator("kubeconfig", mode="before")(normalize_str(default=""))
    _normalize_kube_context = field_validator("kube_context", mode="before")(
        normalize_str(default="")
    )
    _normalize_namespace = field_validator("namespace", mode="before")(
        normalize_str(default=HELM_DEFAULT_NAMESPACE)
    )
    _normalize_helm_path = field_validator("helm_path", mode="before")(
        normalize_str(default="helm")
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
    namespace = os.getenv("HELM_NAMESPACE", HELM_DEFAULT_NAMESPACE)
    helm_path = os.getenv("HELM_PATH", "helm")

    if not _helm_binary_available(helm_path):
        return None

    return HelmConfig(
        kubeconfig=kubeconfig,
        kube_context=kube_context,
        namespace=namespace,
        helm_path=helm_path,
    )


def helm_config_from_params(
    namespace: str | None = None,
    kubeconfig: str | None = None,
    kube_context: str | None = None,
    helm_path: str | None = None,
) -> HelmConfig | None:
    """Build Helm config from explicit params, falling back to env vars."""
    config_dict: dict[str, Any] = {}
    if kubeconfig is not None:
        config_dict["kubeconfig"] = kubeconfig
    if kube_context is not None:
        config_dict["kube_context"] = kube_context
    if namespace is not None:
        config_dict["namespace"] = namespace
    if helm_path is not None:
        config_dict["helm_path"] = helm_path

    # Fall back to env vars
    config_dict.setdefault("kubeconfig", os.getenv("HELM_KUBECONFIG", ""))
    config_dict.setdefault("kube_context", os.getenv("HELM_KUBE_CONTEXT", ""))
    config_dict.setdefault("namespace", os.getenv("HELM_NAMESPACE", HELM_DEFAULT_NAMESPACE))
    config_dict.setdefault("helm_path", os.getenv("HELM_PATH", "helm"))

    config = build_helm_config(config_dict)

    if not _helm_binary_available(config.helm_path):
        return None

    return config


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
    namespace: str | None = None,
    skip_namespace: bool = False,
) -> tuple[bool, str, str]:
    """Run a helm command and return results (success, stdout, stderr).

    Args:
        config: Helm configuration
        args: Helm command arguments (e.g., ["version", "--client"])
        namespace: Override namespace (uses config.namespace if not provided)
        skip_namespace: If True, don't add --namespace flag (for global commands
                      like 'version' or 'plugin list')
    """
    cmd = [config.helm_path]

    if config.kubeconfig:
        cmd.extend(["--kubeconfig", config.kubeconfig])

    if config.kube_context:
        cmd.extend(["--kube-context", config.kube_context])

    if not skip_namespace:
        ns = namespace or config.namespace
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
    success, stdout, stderr = _run_helm_command(
        config, ["version", "--client"], skip_namespace=True
    )
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
        return False

    success, stdout, stderr = _run_helm_command(config, ["plugin", "list"], skip_namespace=True)

    if not success:
        return False

    try:
        plugins_lines = stdout.split("\n")
        if len(plugins_lines) > 1:
            plugins_lines = plugins_lines[1:]
        else:
            plugins_lines = []
        for plugin in plugins_lines:
            plugin_name = plugin.split("\t")
            if "diff" in plugin_name:
                return True

        return False
    except Exception as e:
        logger.error(f"[helm] There has been an error when parsing plugins: {e}")
        return False


def helm_is_available(sources: dict[str, dict]) -> bool:
    """Check if Helm integration identifying params are present."""
    return "helm" in sources


def helm_extract_params(sources: dict[str, dict]) -> dict[str, Any]:
    """Extract Helm identifying params from resolved integrations."""
    helm = sources.get("helm", {})
    return {
        "kubeconfig": str(helm.get("kubeconfig", "")).strip() or None,
        "kube_context": str(helm.get("kube_context", "")).strip() or None,
        "namespace": str(helm.get("namespace", HELM_DEFAULT_NAMESPACE)).strip()
        or HELM_DEFAULT_NAMESPACE,
        "release_name": str(helm.get("release_name", "")).strip() or None,
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
        result = {
            "source": "helm",
            "available": True,
            "namespace": config.namespace,
            "total_releases": len(releases),
            "releases": releases,
        }
        logger.info(
            f"[helm.get_releases] namespace={config.namespace} "
            f"releases={len(releases)} available=True"
        )
        return result
    except json.JSONDecodeError:
        result = {
            "source": "helm",
            "available": False,
            "error": f"Failed to parse Helm output: {stdout}",
        }
        logger.info(
            f"[helm.get_releases] namespace={config.namespace} available=False error='parse failed'"
        )
        return result


def get_release_status(
    config: HelmConfig,
    release_name: str | None,
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

    if not release_name:
        return {"source": "helm", "available": False, "error": "release_name is required."}

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
        result = {
            "source": "helm",
            "available": True,
            "release_name": release_name,
            "namespace": ns,
            "status": status_data,
        }
        logger.info(
            f"[helm.get_release_status] release={release_name} namespace={ns} available=True"
        )
        return result
    except json.JSONDecodeError:
        result = {
            "source": "helm",
            "available": True,
            "release_name": release_name,
            "namespace": ns,
            "status_text": stdout,
        }
        logger.info(
            f"[helm.get_release_status] release={release_name} "
            f"namespace={ns} available=True status_text=true"
        )
        return result


def get_release_history(
    config: HelmConfig,
    release_name: str | None,
    namespace: str | None = None,
    max_history: int | None = None,
) -> dict[str, Any]:
    """Get the revision history of a Helm release."""
    if not config.is_configured:
        return {"source": "helm", "available": False, "error": "Not configured."}

    if not release_name:
        return {"source": "helm", "available": False, "error": "release_name is required."}

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
        result = {
            "source": "helm",
            "available": True,
            "release_name": release_name,
            "namespace": ns,
            "history": history,
            "total_revisions": len(history),
        }
        logger.info(
            f"[helm.get_release_history] release={release_name} "
            f"namespace={ns} revisions={len(history)} available=True"
        )
        return result
    except json.JSONDecodeError:
        result = {
            "source": "helm",
            "available": False,
            "error": f"Failed to parse release history: {stdout}",
            "release_name": release_name,
            "namespace": ns,
        }
        logger.info(
            f"[helm.get_release_history] release={release_name} "
            f"namespace={ns} available=False error='parse failed'"
        )
        return result


def get_release_values(
    config: HelmConfig,
    release_name: str | None,
    namespace: str | None = None,
    all_values: bool = False,
) -> dict[str, Any]:
    """Get the values used in a Helm release."""
    if not config.is_configured:
        return {"source": "helm", "available": False, "error": "Not configured."}

    if not release_name:
        return {"source": "helm", "available": False, "error": "release_name is required."}

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
        result = {
            "source": "helm",
            "available": True,
            "release_name": release_name,
            "namespace": ns,
            "values": values,
            "all_values": all_values,
        }
        logger.info(
            f"[helm.get_release_values] release={release_name} "
            f"namespace={ns} all_values={all_values} available=True"
        )
        return result
    except json.JSONDecodeError:
        result = {
            "source": "helm",
            "available": False,
            "error": f"Failed to parse release values: {stdout}",
            "release_name": release_name,
            "namespace": ns,
        }
        logger.info(
            f"[helm.get_release_values] release={release_name} "
            f"namespace={ns} available=False error='parse failed'"
        )
        return result


def get_manifest(
    config: HelmConfig,
    release_name: str | None,
    namespace: str | None = None,
) -> dict[str, Any]:
    """Get the rendered manifest for a Helm release.

    Returns the full Kubernetes manifest that was generated from the chart.
    """
    if not config.is_configured:
        return {"source": "helm", "available": False, "error": "Not configured."}

    if not release_name:
        return {"source": "helm", "available": False, "error": "release_name is required."}

    ns = namespace or config.namespace

    success, stdout, stderr = _run_helm_command(
        config,
        ["get", "manifest", release_name],
        namespace=ns,
    )

    if not success:
        result = {
            "source": "helm",
            "available": False,
            "error": f"Failed to get manifest: {stderr}",
            "release_name": release_name,
            "namespace": ns,
        }
        logger.info(
            f"[helm.get_manifest] release={release_name} "
            f"namespace={ns} available=False error='{result.get('error', '')}'"
        )
        return result

    result = {
        "source": "helm",
        "available": True,
        "release_name": release_name,
        "namespace": ns,
        "manifest": stdout,
    }
    logger.info(
        f"[helm.get_manifest] release={release_name} "
        f"namespace={ns} available=True manifest_size={len(stdout)}"
    )
    return result


def get_chart_metadata(
    config: HelmConfig,
    release_name: str | None,
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

    if not release_name:
        return {"source": "helm", "available": False, "error": "release_name is required."}

    ns = namespace or config.namespace

    success, stdout, stderr = _run_helm_command(
        config,
        ["get", "metadata", release_name, "--output", "json"],
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

        if isinstance(release_info, str):
            result = {
                "source": "helm",
                "available": False,
                "error": f"Unexpected string output from helm get metadata: {release_info}",
                "release_name": release_name,
                "namespace": ns,
            }
            logger.info(
                f"[helm.get_chart_metadata] release={release_name} "
                f"namespace={ns} available=False error='string output'"
            )
            return result

        if isinstance(release_info, dict):
            chart_info = release_info.get("chart", release_info)
            metadata_info = release_info.get("info", {})

            if not isinstance(chart_info, dict):
                chart_info = release_info

            result = {
                "source": "helm",
                "available": True,
                "release_name": release_name,
                "namespace": ns,
                "chart": {
                    "name": chart_info.get("name", ""),
                    "version": chart_info.get("version", chart_info.get("Version", "")),
                    "app_version": chart_info.get("app_version", chart_info.get("appVersion", "")),
                },
                "metadata": metadata_info,
            }
            logger.info(
                f"[helm.get_chart_metadata] release={release_name} "
                f"namespace={ns} available=True chart={chart_info.get('name', '')}"
            )
            return result
        else:
            result = {
                "source": "helm",
                "available": False,
                "error": f"Unexpected output type from helm get metadata: {type(release_info)}",
                "release_name": release_name,
                "namespace": ns,
            }
            logger.info(
                f"[helm.get_chart_metadata] release={release_name} "
                f"namespace={ns} available=False error='unexpected type'"
            )
            return result
    except json.JSONDecodeError:
        result = {
            "source": "helm",
            "available": False,
            "error": f"Failed to parse release info: {stdout}",
            "release_name": release_name,
            "namespace": ns,
        }
        logger.info(
            f"[helm.get_chart_metadata] release={release_name} "
            f"namespace={ns} available=False error='json parse failed'"
        )
        return result


def get_notes(
    config: HelmConfig,
    release_name: str | None,
    namespace: str | None = None,
) -> dict[str, Any]:
    """Get the notes for a Helm release.

    Notes are typically displayed after a release is installed/upgraded
    and contain information about what was deployed and next steps.
    """
    if not config.is_configured:
        return {"source": "helm", "available": False, "error": "Not configured."}

    if not release_name:
        return {"source": "helm", "available": False, "error": "release_name is required."}

    ns = namespace or config.namespace

    success, stdout, stderr = _run_helm_command(
        config,
        ["get", "notes", release_name],
        namespace=ns,
    )

    if not success:
        result = {
            "source": "helm",
            "available": False,
            "error": f"Failed to get notes: {stderr}",
            "release_name": release_name,
            "namespace": ns,
        }
        logger.info(
            f"[helm.get_notes] release={release_name} "
            f"namespace={ns} available=False error='{result.get('error', '')}'"
        )
        return result

    result = {
        "source": "helm",
        "available": True,
        "release_name": release_name,
        "namespace": ns,
        "notes": stdout,
    }
    logger.info(
        f"[helm.get_notes] release={release_name} "
        f"namespace={ns} available=True notes_size={len(stdout)}"
    )
    return result


def check_diff(
    config: HelmConfig,
    release_name: str | None,
    namespace: str | None = None,
) -> dict[str, Any]:
    """Check if a Helm release has changed from its expected state.

    This compares the current live state with the state that would be
    generated by the current chart and values.

    Note: This requires Helm 3.11+ with the diff plugin or similar functionality.
    """
    if not config.is_configured:
        return {"source": "helm", "available": False, "error": "Not configured."}

    if not release_name:
        return {"source": "helm", "available": False, "error": "release_name is required."}

    ns = namespace or config.namespace

    if not helm_diff_plugin_is_available(config):
        logger.error("[helm] Helm Diff plugin is not available.")
        result = {
            "source": "helm",
            "available": True,
            "release_name": release_name,
            "namespace": ns,
            "has_diff": None,
            "error": "Helm Diff plugin is not available.",
        }
        logger.info(
            f"[helm.check_diff] release={release_name} "
            f"namespace={ns} available=True has_diff=None error='plugin not available'"
        )
        return result

    chart_success, chart_stdout, chart_stderr = _run_helm_command(
        config,
        ["get", "metadata", release_name, "--output", "json"],
        namespace=ns,
    )

    chart_ref = release_name
    if chart_success:
        try:
            chart_data = json.loads(chart_stdout)
            chart_ref = chart_data.get("chart", release_name)
            if isinstance(chart_ref, dict):
                chart_ref = chart_ref.get("name", release_name)
        except (json.JSONDecodeError, KeyError, AttributeError):
            chart_ref = release_name

    success, stdout, stderr = _run_helm_command(
        config,
        ["diff", "upgrade", release_name, chart_ref],
        namespace=ns,
    )

    if success:
        result = {
            "source": "helm",
            "available": True,
            "release_name": release_name,
            "namespace": ns,
            "has_diff": bool(stdout.strip()),
            "diff": stdout,
        }
        logger.info(
            f"[helm.check_diff] release={release_name} "
            f"namespace={ns} available=True has_diff={result['has_diff']} "
            f"diff_size={len(stdout)}"
        )
        return result

    # If diff plugin is not available, we can't check diff
    result = {
        "source": "helm",
        "available": True,
        "release_name": release_name,
        "namespace": ns,
        "has_diff": None,
        "error": f"Failed to check diff: {stderr}" if stderr else "Failed to check diff",
    }
    logger.info(
        f"[helm.check_diff] release={release_name} "
        f"namespace={ns} available=True has_diff=None error='{result['error']}'"
    )
    return result
