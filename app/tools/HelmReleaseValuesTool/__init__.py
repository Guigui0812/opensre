"""Helm Release Values Tool."""

from typing import Any

from app.integrations.helm import (
    get_release_values,
    helm_extract_params,
    helm_is_available,
    resolve_helm_config,
)
from app.tools.tool_decorator import tool


@tool(
    name="helm_release_values",
    description="Get the computed values (default + overrides) for a Helm release.",
    source="helm",
    surfaces=("investigation", "chat"),
    use_cases=[
        "Reviewing the actual configuration values deployed for a release",
        "Comparing expected vs actual values to find configuration issues",
        "Identifying bad values that caused deployment failures",
        "Understanding the full configuration including defaults",
    ],
    is_available=helm_is_available,
    extract_params=helm_extract_params,
)
def helm_release_values(
    release_name: str,
    namespace: str | None = None,
    all_values: bool = False,
    kubeconfig: str | None = None,
    kube_context: str | None = None,
) -> dict[str, Any]:
    """Get the values used in a Helm release."""
    config = resolve_helm_config(
        kubeconfig=kubeconfig,
        kube_context=kube_context,
        namespace=namespace,
    )
    return get_release_values(config, release_name, namespace, all_values)
