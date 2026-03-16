"""Orchestrate AWS Neuron Operator and dependencies installation.

Steps (matching eco-gotests neuronhelpers/deploy.go DeployAllOperators):
1. Install NFD operator via OLM
2. Create NodeFeatureDiscovery instance (starts NFD worker pods)
3. Wait for NFD workers to be ready
4. Install KMM operator via OLM
5. Install Neuron operator via OLM (community-operators, Fast channel)
6. Create NodeFeatureRule for Neuron PCI devices
7. Wait for NFD to label nodes with aws-neuron label
8. Create DeviceConfig CR with driver/plugin images
9. Wait for device plugin DaemonSet to be ready
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from operators.config import (
    create_device_config,
    create_neuron_nfd_rule,
    create_nfd_instance,
)
from operators.constants import (
    KMM_CATALOG,
    KMM_CHANNEL,
    KMM_OPERATOR_GROUP,
    KMM_PACKAGE,
    KMM_SUBSCRIPTION,
    NAMESPACE_KMM,
    NAMESPACE_NFD,
    NAMESPACE_NEURON,
    NEURON_CATALOG,
    NEURON_CHANNEL,
    NEURON_OPERATOR_GROUP,
    NEURON_PACKAGE,
    NEURON_SUBSCRIPTION,
    NFD_CATALOG,
    NFD_CHANNEL,
    NFD_OPERATOR_GROUP,
    NFD_PACKAGE,
    NFD_SUBSCRIPTION,
)
from operators.install import install_operator
from operators.wait import (
    wait_for_device_plugin,
    wait_for_neuron_node_labels,
    wait_for_nfd_workers,
)

if TYPE_CHECKING:
    from operators.oc import OcRunner


@dataclass
class NeuronInstallConfig:
    """Configuration for the Neuron operator installation flow."""

    drivers_image: str = ""
    driver_version: str = ""
    device_plugin_image: str = ""
    node_metrics_image: str = ""
    scheduler_image: str = ""
    scheduler_extension_image: str = ""

    # Timeouts (seconds)
    operator_timeout: int = 600
    nfd_workers_timeout: int = 300
    node_label_timeout: int = 300
    device_plugin_timeout: int = 600


def install_operators(oc: OcRunner, config: NeuronInstallConfig) -> None:
    """Run full AWS Neuron Operator installation flow.

    Mirrors the flow from eco-gotests DeployAllOperators() but executed
    as a standalone pre-step so that eco-gotests detects the operators
    as pre-existing and skips its own install/uninstall cycles.
    """
    print("\n" + "=" * 60)
    print("AWS Neuron Operator & Dependencies Installation (OLM)")
    print("=" * 60)

    # Step 1: Install NFD operator
    install_operator(
        oc,
        namespace=NAMESPACE_NFD,
        package_name=NFD_PACKAGE,
        catalog_source=NFD_CATALOG,
        channel=NFD_CHANNEL,
        operator_group_name=NFD_OPERATOR_GROUP,
        subscription_name=NFD_SUBSCRIPTION,
        target_namespaces=[NAMESPACE_NFD],
        timeout=config.operator_timeout,
    )

    # Step 2-3: Create NFD instance and wait for workers
    create_nfd_instance(oc)
    wait_for_nfd_workers(oc, timeout=config.nfd_workers_timeout)

    # Step 4: Install KMM operator
    install_operator(
        oc,
        namespace=NAMESPACE_KMM,
        package_name=KMM_PACKAGE,
        catalog_source=KMM_CATALOG,
        channel=KMM_CHANNEL,
        operator_group_name=KMM_OPERATOR_GROUP,
        subscription_name=KMM_SUBSCRIPTION,
        timeout=config.operator_timeout,
    )

    # Step 5: Install Neuron operator (AllNamespaces mode)
    install_operator(
        oc,
        namespace=NAMESPACE_NEURON,
        package_name=NEURON_PACKAGE,
        catalog_source=NEURON_CATALOG,
        channel=NEURON_CHANNEL,
        operator_group_name=NEURON_OPERATOR_GROUP,
        subscription_name=NEURON_SUBSCRIPTION,
        timeout=config.operator_timeout,
    )

    # Step 6-7: Create NFD rule and wait for node labels
    create_neuron_nfd_rule(oc)
    wait_for_neuron_node_labels(oc, timeout=config.node_label_timeout)

    # Steps 8-9: Create DeviceConfig, wait for device plugin
    if config.drivers_image and config.driver_version and config.device_plugin_image:
        create_device_config(
            oc,
            drivers_image=config.drivers_image,
            driver_version=config.driver_version,
            device_plugin_image=config.device_plugin_image,
            node_metrics_image=config.node_metrics_image,
            scheduler_image=config.scheduler_image,
            scheduler_extension_image=config.scheduler_extension_image,
        )
        wait_for_device_plugin(oc, timeout=config.device_plugin_timeout)
    else:
        print("  Skipping DeviceConfig (driver images not configured)")

    print("\n" + "=" * 60)
    print("AWS Neuron Operator installation completed successfully.")
    print("=" * 60)
