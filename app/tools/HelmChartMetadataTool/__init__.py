"""Helm Chart Metadata Tool."""

from typing import Any

from app.services.helm import (
    get_chart_metadata,
    helm_config_from_params,
    helm_is_available,
)
from app.tools.tool_decorator import tool


def _chart_metadata_extract_params(sources: dict[str, dict]) -> dict[str, Any]:
    helm = sources.get("helm", {})
    return {
        "release_name": helm.get("release_name", ""),
        "namespace": helm.get("namespace", ""),
        "kubeconfig": helm.get("kubeconfig"),
        "kube_context": helm.get("kube_context"),
        "helm_path": helm.get("helm_path"),
    }


def _chart_metadata_available(sources: dict[str, dict]) -> bool:
    return helm_is_available(sources)


@tool(
    name="helm_chart_metadata",
    display_name="Helm Chart Metadata",
    description="Get metadata about the Helm chart used for a release including name, version, app version, and description.",
    source="helm",
    surfaces=("investigation", "chat"),
    use_cases=[
        "Identifying which chart version is deployed for a release",
        "Checking if the deployed chart version has known issues",
        "Understanding the chart metadata and maintainers",
        "Connecting chart information to configuration regressions",
    ],
    requires=["release_name"],
    input_schema={
        "type": "object",
        "properties": {
            "release_name": {"type": "string"},
            "namespace": {"type": "string"},
            "kubeconfig": {"type": "string"},
            "kube_context": {"type": "string"},
            "helm_path": {"type": "string"},
        },
        "required": ["release_name"],
    },
    is_available=_chart_metadata_available,
    extract_params=_chart_metadata_extract_params,
)
def helm_chart_metadata(
    release_name: str | None = None,
    namespace: str | None = None,
    kubeconfig: str | None = None,
    kube_context: str | None = None,
    helm_path: str | None = None,
) -> dict[str, Any]:
    """Get metadata about the chart used for a release."""
    config = helm_config_from_params(namespace, kubeconfig, kube_context, helm_path)
    if config is None:
        return {"source": "helm", "available": False, "error": "Helm not available"}

    return get_chart_metadata(config, release_name, namespace)
