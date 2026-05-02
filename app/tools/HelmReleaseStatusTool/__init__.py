"""Helm Release Status Tool."""

from typing import Any

from app.integrations.helm import (
    get_release_status,
    helm_extract_params,
    helm_is_available,
    resolve_helm_config,
)
from app.tools.tool_decorator import tool


@tool(
    name="helm_release_status",
    description="Get the status of a specific Helm release including state, resources, and chart info.",
    source="helm",
    surfaces=("investigation", "chat"),
    use_cases=[
        "Checking if a Helm release is deployed, failed, or pending",
        "Identifying which Kubernetes resources belong to a release",
        "Getting chart version and app version for a deployed release",
    ],
    is_available=helm_is_available,
    extract_params=helm_extract_params,
)
def helm_release_status(
    release_name: str,
    namespace: str | None = None,
    kubeconfig: str | None = None,
    kube_context: str | None = None,
) -> dict[str, Any]:
    """Get the status of a specific Helm release."""
    config = resolve_helm_config(
        kubeconfig=kubeconfig,
        kube_context=kube_context,
        namespace=namespace,
    )
    return get_release_status(config, release_name, namespace)
