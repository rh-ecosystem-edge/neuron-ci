"""Reverse of install: remove DeviceConfig, NFD rule, operators, and namespaces.

Matches eco-gotests neuronhelpers/deploy.go UninstallAllOperators() order.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from operators.config import delete_device_config, delete_nfd_instance, delete_nfd_rule
from operators.constants import (
    KMM_OPERATOR_GROUP,
    KMM_SUBSCRIPTION,
    NAMESPACE_KMM,
    NAMESPACE_NFD,
    NAMESPACE_NEURON,
    NEURON_OPERATOR_GROUP,
    NEURON_SUBSCRIPTION,
    NFD_OPERATOR_GROUP,
    NFD_SUBSCRIPTION,
)
from operators.install import uninstall_operator

if TYPE_CHECKING:
    from operators.oc import OcRunner


def cleanup_operators(oc: OcRunner) -> None:
    """Remove the full Neuron operator stack in reverse order."""
    print("\n" + "=" * 60)
    print("AWS Neuron Operator Cleanup")
    print("=" * 60)

    errors: list[str] = []

    # Delete DeviceConfig first
    try:
        delete_device_config(oc)
    except Exception as exc:
        errors.append(f"DeviceConfig: {exc}")

    # Delete NFD rule
    try:
        delete_nfd_rule(oc)
    except Exception as exc:
        errors.append(f"NFD rule: {exc}")

    # Uninstall Neuron operator
    try:
        uninstall_operator(
            oc,
            namespace=NAMESPACE_NEURON,
            subscription_name=NEURON_SUBSCRIPTION,
            operator_group_name=NEURON_OPERATOR_GROUP,
        )
    except Exception as exc:
        errors.append(f"Neuron operator: {exc}")

    # Uninstall KMM operator
    try:
        uninstall_operator(
            oc,
            namespace=NAMESPACE_KMM,
            subscription_name=KMM_SUBSCRIPTION,
            operator_group_name=KMM_OPERATOR_GROUP,
        )
    except Exception as exc:
        errors.append(f"KMM operator: {exc}")

    # Delete NFD instance before NFD operator
    try:
        delete_nfd_instance(oc)
    except Exception as exc:
        errors.append(f"NFD instance: {exc}")

    # Uninstall NFD operator
    try:
        uninstall_operator(
            oc,
            namespace=NAMESPACE_NFD,
            subscription_name=NFD_SUBSCRIPTION,
            operator_group_name=NFD_OPERATOR_GROUP,
        )
    except Exception as exc:
        errors.append(f"NFD operator: {exc}")

    if errors:
        print(f"\nCleanup completed with {len(errors)} error(s):")
        for err in errors:
            print(f"  - {err}")
    else:
        print("\n" + "=" * 60)
        print("Cleanup completed successfully.")
        print("=" * 60)
