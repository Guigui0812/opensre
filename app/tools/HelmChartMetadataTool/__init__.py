"""Helm Chart Metadata Tool."""

from typing import Any

from app.integrations.helm import (
    get_chart_metadata,
    helm_extract_params,
    helm_is_available,
    resolve_helm_config,
)
from app.tools.tool_decorator import tool


@tool(
    name="helm_chart_metadata",
    description="Get metadata about the Helm chart used for a release including name, version, app version, and description.",
    source="helm",
    surfaces=("investigation", "chat"),
    use_cases=[
        "Identifying which chart version is deployed for a release",
        "Checking if the deployed chart version has known issues",
        "Understanding the chart metadata and maintainers",
        "Connecting chart information to configuration regressions",
    ],
    is_available=helm_is_available,
    extract_params=helm_extract_params,
)
def helm_chart_metadata(
    release_name: str,
    namespace: str | None = None,
    kubeconfig: str | None = None,
    kube_context: str | None = None,
) -> dict[str, Any]:
    """Get metadata about the chart used for a release."""
    config = resolve_helm_config(
        kubeconfig=kubeconfig,
        kube_context=kube_context,
        namespace=namespace,
    )
    return get_chart_metadata(config, release_name, namespace)
