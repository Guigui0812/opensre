"""Helm Check Diff Tool."""

from typing import Any

from app.services.helm import (
    check_diff,
    helm_is_available,
    resolve_helm_config,
)
from app.tools.tool_decorator import tool


def _check_diff_extract_params(sources: dict[str, dict]) -> dict[str, Any]:
    helm = sources.get("helm", {})
    return {
        "release_name": helm.get("release_name", ""),
        "namespace": helm.get("namespace", ""),
        "kubeconfig": helm.get("kubeconfig"),
        "kube_context": helm.get("kube_context"),
    }


def _check_diff_available(sources: dict[str, dict]) -> bool:
    return helm_is_available(sources)


@tool(
    name="helm_check_diff",
    display_name="Helm Check Diff",
    description="Check if a Helm release has changed from its expected state by comparing live state with rendered templates.",
    source="helm",
    surfaces=("investigation", "chat"),
    use_cases=[
        "Detecting configuration diff between deployed and expected state",
        "Identifying manual changes to Helm-managed resources",
        "Finding discrepancies that could cause issues during upgrades",
        "Validating that deployed resources match chart templates",
    ],
    requires=["release_name"],
    input_schema={
        "type": "object",
        "properties": {
            "release_name": {"type": "string"},
            "namespace": {"type": "string"},
            "kubeconfig": {"type": "string"},
            "kube_context": {"type": "string"},
        },
        "required": ["release_name"],
    },
    is_available=_check_diff_available,
    extract_params=_check_diff_extract_params,
)
def helm_check_diff(
    release_name: str | None = None,
    namespace: str | None = None,
    kubeconfig: str | None = None,
    kube_context: str | None = None,
) -> dict[str, Any]:
    """Check if a Helm release has changed from its expected state.
    Note: Requires Helm diff plugin for full functionality.
    """
    config = resolve_helm_config(
        kubeconfig=kubeconfig,
        kube_context=kube_context,
        namespace=namespace,
    )
    return check_diff(config, release_name, namespace)
