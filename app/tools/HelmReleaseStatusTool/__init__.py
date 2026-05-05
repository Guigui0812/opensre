"""Helm Release Status Tool."""

from typing import Any

from app.services.helm import (
    get_release_status,
    helm_config_from_params,
    helm_is_available,
)
from app.tools.tool_decorator import tool


def _release_status_extract_params(sources: dict[str, dict]) -> dict[str, Any]:
    helm = sources.get("helm", {})
    return {
        "release_name": helm.get("release_name", ""),
        "namespace": helm.get("namespace", ""),
        "kubeconfig": helm.get("kubeconfig"),
        "kube_context": helm.get("kube_context"),
        "helm_path": helm.get("helm_path"),
    }


def _release_status_available(sources: dict[str, dict]) -> bool:
    return helm_is_available(sources)


@tool(
    name="helm_release_status",
    display_name="Helm Release Status",
    description="Get the status of a specific Helm release including state, resources, and chart info.",
    source="helm",
    surfaces=("investigation", "chat"),
    use_cases=[
        "Checking if a Helm release is deployed, failed, or pending",
        "Identifying which Kubernetes resources belong to a release",
        "Getting chart version and app version for a deployed release",
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
    is_available=_release_status_available,
    extract_params=_release_status_extract_params,
)
def helm_release_status(
    release_name: str | None = None,
    namespace: str | None = None,
    kubeconfig: str | None = None,
    kube_context: str | None = None,
    helm_path: str | None = None,
    max_results: int | None = None,
) -> dict[str, Any]:
    """Get the status of a specific Helm release."""
    config = helm_config_from_params(namespace, kubeconfig, kube_context, helm_path, max_results)
    if config is None:
        return {"source": "helm", "available": False, "error": "Helm not available"}
    return get_release_status(config, release_name, namespace)
