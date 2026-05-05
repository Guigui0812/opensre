"""Helm Release Values Tool."""

from typing import Any

from app.services.helm import (
    get_release_values,
    helm_is_available,
    resolve_helm_config,
)
from app.tools.tool_decorator import tool


def _release_values_extract_params(sources: dict[str, dict]) -> dict[str, Any]:
    helm = sources.get("helm", {})
    return {
        "release_name": helm.get("release_name", ""),
        "namespace": helm.get("namespace", ""),
        "all_values": False,
        "kubeconfig": helm.get("kubeconfig"),
        "kube_context": helm.get("kube_context"),
    }


def _release_values_available(sources: dict[str, dict]) -> bool:
    return helm_is_available(sources)


@tool(
    name="helm_release_values",
    display_name="Helm Release Values",
    description="Get the computed values (default + overrides) for a Helm release.",
    source="helm",
    surfaces=("investigation", "chat"),
    use_cases=[
        "Reviewing the actual configuration values deployed for a release",
        "Comparing expected vs actual values to find configuration issues",
        "Identifying bad values that caused deployment failures",
        "Understanding the full configuration including defaults",
    ],
    requires=["release_name"],
    input_schema={
        "type": "object",
        "properties": {
            "release_name": {"type": "string"},
            "namespace": {"type": "string"},
            "all_values": {"type": "boolean", "default": False},
            "kubeconfig": {"type": "string"},
            "kube_context": {"type": "string"},
        },
        "required": ["release_name"],
    },
    is_available=_release_values_available,
    extract_params=_release_values_extract_params,
)
def helm_release_values(
    release_name: str | None = None,
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
