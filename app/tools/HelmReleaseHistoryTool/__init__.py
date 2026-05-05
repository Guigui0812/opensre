"""Helm Release History Tool."""

from typing import Any

from app.services.helm import (
    get_release_history,
    helm_config_from_params,
    helm_is_available,
)
from app.tools.tool_decorator import tool


def _release_history_extract_params(sources: dict[str, dict]) -> dict[str, Any]:
    helm = sources.get("helm", {})
    return {
        "release_name": helm.get("release_name", ""),
        "namespace": helm.get("namespace", ""),
        "max_history": helm.get("max_results", 50),
        "kubeconfig": helm.get("kubeconfig"),
        "kube_context": helm.get("kube_context"),
        "helm_path": helm.get("helm_path"),
    }


def _release_history_available(sources: dict[str, dict]) -> bool:
    return helm_is_available(sources)


@tool(
    name="helm_release_history",
    display_name="Helm Release History",
    description="Get the revision history of a Helm release with timestamps, status, chart versions, and descriptions.",
    source="helm",
    surfaces=("investigation", "chat"),
    use_cases=[
        "Investigating when a release was last upgraded",
        "Finding which revision caused a deployment issue",
        "Checking the chart version history for a release",
        "Understanding the timeline of configuration changes",
    ],
    requires=["release_name"],
    input_schema={
        "type": "object",
        "properties": {
            "release_name": {"type": "string"},
            "namespace": {"type": "string"},
            "max_history": {"type": "integer", "default": 50},
            "kubeconfig": {"type": "string"},
            "kube_context": {"type": "string"},
            "helm_path": {"type": "string"},
        },
        "required": ["release_name"],
    },
    is_available=_release_history_available,
    extract_params=_release_history_extract_params,
)
def helm_release_history(
    release_name: str | None = None,
    namespace: str | None = None,
    max_history: int | None = None,
    kubeconfig: str | None = None,
    kube_context: str | None = None,
    helm_path: str | None = None,
    max_results: int | None = None,
) -> dict[str, Any]:
    """Get the revision history of a Helm release."""
    config = helm_config_from_params(namespace, kubeconfig, kube_context, helm_path, max_results)
    if config is None:
        return {"source": "helm", "available": False, "error": "Helm not available"}
    return get_release_history(config, release_name, namespace, max_history)
