"""Helm List Releases Tool."""

from typing import Any

from app.services.helm import (
    get_releases,
    helm_config_from_params,
    helm_is_available,
)
from app.tools.tool_decorator import tool


def _list_releases_extract_params(sources: dict[str, dict]) -> dict[str, Any]:
    helm = sources.get("helm", {})
    return {
        "namespace": helm.get("namespace", ""),
        "kubeconfig": helm.get("kubeconfig"),
        "kube_context": helm.get("kube_context"),
        "helm_path": helm.get("helm_path"),
    }


def _list_releases_available(sources: dict[str, dict]) -> bool:
    return helm_is_available(sources)


@tool(
    name="helm_list_releases",
    display_name="Helm List Releases",
    description="List all Helm releases in a namespace, showing status, chart, version, and revision.",
    source="helm",
    surfaces=("investigation", "chat"),
    use_cases=[
        "Identifying all deployed Helm releases during an incident",
        "Finding releases related to a specific application or service",
        "Checking which chart versions are currently deployed",
    ],
    is_available=_list_releases_available,
    extract_params=_list_releases_extract_params,
)
def helm_list_releases(
    namespace: str | None = None,
    kubeconfig: str | None = None,
    kube_context: str | None = None,
    helm_path: str | None = None,
) -> dict[str, Any]:
    """List all Helm releases in the specified namespace."""
    config = helm_config_from_params(namespace, kubeconfig, kube_context, helm_path)
    if config is None:
        return {"source": "helm", "available": False, "error": "Helm not available"}
    return get_releases(config)
