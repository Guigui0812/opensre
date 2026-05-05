"""Helm Release Manifest Tool."""

from typing import Any

from app.integrations.helm import (
    get_manifest,
    helm_is_available,
    resolve_helm_config,
)
from app.tools.tool_decorator import tool


def _release_manifest_extract_params(sources: dict[str, dict]) -> dict[str, Any]:
    helm = sources.get("helm", {})
    return {
        "release_name": helm.get("release_name", ""),
        "namespace": helm.get("namespace", ""),
        "kubeconfig": helm.get("kubeconfig"),
        "kube_context": helm.get("kube_context"),
    }


def _release_manifest_available(sources: dict[str, dict]) -> bool:
    return helm_is_available(sources)


@tool(
    name="helm_release_manifest",
    display_name="Helm Release Manifest",
    description="Get the full Kubernetes manifest generated from a Helm chart for a release.",
    source="helm",
    surfaces=("investigation", "chat"),
    use_cases=[
        "Reviewing the exact Kubernetes resources deployed by a Helm release",
        "Connecting Helm release evidence to Kubernetes investigations",
        "Finding specific resource definitions in a deployed chart",
        "Understanding how chart templates rendered into actual manifests",
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
    is_available=_release_manifest_available,
    extract_params=_release_manifest_extract_params,
)
def helm_release_manifest(
    release_name: str | None = None,
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
