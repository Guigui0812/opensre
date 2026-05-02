"""Helm Release History Tool."""

from typing import Any

from app.integrations.helm import (
    get_release_history,
    helm_extract_params,
    helm_is_available,
    resolve_helm_config,
)
from app.tools.tool_decorator import tool


@tool(
    name="helm_release_history",
    description="Get the revision history of a Helm release with timestamps, status, chart versions, and descriptions.",
    source="helm",
    surfaces=("investigation", "chat"),
    use_cases=[
        "Investigating when a release was last upgraded",
        "Finding which revision caused a deployment issue",
        "Checking the chart version history for a release",
        "Understanding the timeline of configuration changes",
    ],
    is_available=helm_is_available,
    extract_params=helm_extract_params,
)
def helm_release_history(
    release_name: str,
    namespace: str | None = None,
    max_history: int | None = None,
    kubeconfig: str | None = None,
    kube_context: str | None = None,
) -> dict[str, Any]:
    """Get the revision history of a Helm release."""
    config = resolve_helm_config(
        kubeconfig=kubeconfig,
        kube_context=kube_context,
        namespace=namespace,
    )
    return get_release_history(config, release_name, namespace, max_history)
