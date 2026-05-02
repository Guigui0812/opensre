"""Helm Release Manifest Tool."""

from typing import Any

from app.integrations.helm import (
    get_manifest,
    helm_extract_params,
    helm_is_available,
    resolve_helm_config,
)
from app.tools.tool_decorator import tool


@tool(
    name="helm_release_manifest",
    description="Get the full Kubernetes manifest generated from a Helm chart for a release.",
    source="helm",
    surfaces=("investigation", "chat"),
    use_cases=[
        "Reviewing the exact Kubernetes resources deployed by a Helm release",
        "Connecting Helm release evidence to Kubernetes investigations",
        "Finding specific resource definitions in a deployed chart",
        "Understanding how chart templates rendered into actual manifests",
    ],
    is_available=helm_is_available,
    extract_params=helm_extract_params,
)
def helm_release_manifest(
    release_name: str,
    namespace: str | None = None,
    kubeconfig: str | None = None,
    kube_context: str | None = None,
) -> dict[str, Any]:
    """Get the rendered manifest for a Helm release."""
    config = resolve_helm_config(
        kubeconfig=kubeconfig,
        kube_context=kube_context,
        namespace=namespace,
    )
    return get_manifest(config, release_name, namespace)
