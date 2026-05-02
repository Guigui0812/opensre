"""Helm List Releases Tool."""

from typing import Any

from app.integrations.helm import (
    get_releases,
    helm_extract_params,
    helm_is_available,
    resolve_helm_config,
)
from app.tools.tool_decorator import tool


@tool(
    name="helm_list_releases",
    description="List all Helm releases in a namespace, showing status, chart, version, and revision.",
    source="helm",
    surfaces=("investigation", "chat"),
    use_cases=[
        "Identifying all deployed Helm releases during an incident",
        "Finding releases related to a specific application or service",
        "Checking which chart versions are currently deployed",
    ],
    is_available=helm_is_available,
    extract_params=helm_extract_params,
)
def helm_list_releases(
    namespace: str | None = None,
    kubeconfig: str | None = None,
    kube_context: str | None = None,
) -> dict[str, Any]:
    """List all Helm releases in the specified namespace."""
    config = resolve_helm_config(
        kubeconfig=kubeconfig,
        kube_context=kube_context,
        namespace=namespace,
    )
    return get_releases(config)
