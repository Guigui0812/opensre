"""Helm Check Drift Tool."""

from typing import Any

from app.integrations.helm import (
    check_drift,
    helm_extract_params,
    helm_is_available,
    resolve_helm_config,
)
from app.tools.tool_decorator import tool


@tool(
    name="helm_check_drift",
    description="Check if a Helm release has drifted from its expected state by comparing live state with rendered templates.",
    source="helm",
    surfaces=("investigation", "chat"),
    use_cases=[
        "Detecting configuration drift between deployed and expected state",
        "Identifying manual changes to Helm-managed resources",
        "Finding discrepancies that could cause issues during upgrades",
        "Validating that deployed resources match chart templates",
    ],
    is_available=helm_is_available,
    extract_params=helm_extract_params,
)
def helm_check_drift(
    release_name: str,
    namespace: str | None = None,
    kubeconfig: str | None = None,
    kube_context: str | None = None,
) -> dict[str, Any]:
    """Check if a Helm release has drifted from its expected state.
    Note: Requires Helm diff plugin for full functionality.
    """
    config = resolve_helm_config(
        kubeconfig=kubeconfig,
        kube_context=kube_context,
        namespace=namespace,
    )
    return check_drift(config, release_name, namespace)
