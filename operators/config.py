"""CR templates and creation helpers for NFD, NodeFeatureRule, and DeviceConfig.

Values extracted from eco-gotests neuronhelpers/config.go.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from operators.constants import (
    DEVICE_CONFIG_API_VERSION,
    DEVICE_CONFIG_NAME,
    DEVICE_IDS,
    DEVICE_PLUGIN_PREFIX,
    NAMESPACE_MONITORING,
    NAMESPACE_NFD,
    NAMESPACE_NEURON,
    NEURON_CAPACITY_ID,
    NFD_INSTANCE_NAME,
    NFD_LABEL_KEY,
    NFD_LABEL_VALUE,
    NFD_RULE_NAME,
    PCI_VENDOR_ID,
)

if TYPE_CHECKING:
    from operators.oc import OcRunner


def enable_user_workload_monitoring(oc: OcRunner) -> None:
    """Enable user workload monitoring so Prometheus scrapes ServiceMonitors in user namespaces.

    Without this, the platform Prometheus only scrapes targets in openshift-*
    namespaces and the Neuron metrics ServiceMonitor (in ai-operator-on-aws)
    is never scraped.
    """
    r = oc.run(
        "get", "configmap", "cluster-monitoring-config",
        "-n", NAMESPACE_MONITORING,
        "-o", "jsonpath={.data.config\\.yaml}",
        timeout=10,
    )

    if r.returncode == 0 and r.stdout and "enableUserWorkload" in r.stdout:
        print("  User workload monitoring already configured")
        return

    print("  Enabling user workload monitoring")
    oc.apply_stdin(f"""\
apiVersion: v1
kind: ConfigMap
metadata:
  name: cluster-monitoring-config
  namespace: {NAMESPACE_MONITORING}
data:
  config.yaml: |
    enableUserWorkload: true
""")


def create_nfd_instance(oc: OcRunner) -> None:
    """Create the NodeFeatureDiscovery instance to deploy NFD workers.

    Matches eco-gotests neuronhelpers/config.go getNFDInstanceYAML().
    """
    r = oc.run("get", "NodeFeatureDiscovery", NFD_INSTANCE_NAME,
               "-n", NAMESPACE_NFD, timeout=10)
    if r.returncode == 0:
        print("  NodeFeatureDiscovery instance already exists")
        return

    print("  Creating NodeFeatureDiscovery instance")
    oc.apply_stdin(f"""\
apiVersion: nfd.openshift.io/v1
kind: NodeFeatureDiscovery
metadata:
  name: {NFD_INSTANCE_NAME}
  namespace: {NAMESPACE_NFD}
spec:
  workerConfig:
    configData: |
      sources:
        pci:
          deviceClassWhitelist:
            - "0300"
            - "0302"
            - "0c80"
          deviceLabelFields:
            - vendor
            - device
""")


def create_neuron_nfd_rule(oc: OcRunner) -> None:
    """Create the NodeFeatureRule for Neuron PCI device detection.

    Matches eco-gotests neuronhelpers/config.go CreateNeuronNFDRule().
    Labels nodes with feature.node.kubernetes.io/aws-neuron=true when
    a PCI device with vendor 1d0f and one of the known Neuron device IDs
    is detected.
    """
    r = oc.run("get", "NodeFeatureRule", NFD_RULE_NAME,
               "-n", NAMESPACE_NEURON, timeout=10)
    if r.returncode == 0:
        print("  Neuron NodeFeatureRule already exists")
        return

    device_id_entries = "\n".join(
        f'              - "{did}"' for did in DEVICE_IDS
    )

    print("  Creating Neuron NodeFeatureRule")
    oc.apply_stdin(f"""\
apiVersion: nfd.openshift.io/v1alpha1
kind: NodeFeatureRule
metadata:
  name: {NFD_RULE_NAME}
  namespace: {NAMESPACE_NEURON}
spec:
  rules:
    - name: neuron-device
      labels:
        {NFD_LABEL_KEY}: "{NFD_LABEL_VALUE}"
      matchFeatures:
        - feature: pci.device
          matchExpressions:
            vendor:
              op: In
              value:
                - "{PCI_VENDOR_ID}"
            device:
              op: In
              value:
{device_id_entries}
""")


def create_device_config(
    oc: OcRunner,
    *,
    drivers_image: str,
    driver_version: str,
    device_plugin_image: str,
    node_metrics_image: str,
    scheduler_image: str = "",
    scheduler_extension_image: str = "",
) -> None:
    """Create the DeviceConfig CR.

    Matches eco-gotests neuronhelpers/config.go CreateDeviceConfigFromEnv().
    """
    r = oc.run("get", "DeviceConfig", DEVICE_CONFIG_NAME,
               "-n", NAMESPACE_NEURON, timeout=10)
    if r.returncode == 0:
        print("  DeviceConfig already exists")
        return

    scheduler_block = ""
    if scheduler_image and scheduler_extension_image:
        scheduler_block = f"""\
  customSchedulerImage: {scheduler_image}
  schedulerExtensionImage: {scheduler_extension_image}
"""

    print("  Creating DeviceConfig")
    oc.apply_stdin(f"""\
apiVersion: {DEVICE_CONFIG_API_VERSION}
kind: DeviceConfig
metadata:
  name: {DEVICE_CONFIG_NAME}
  namespace: {NAMESPACE_NEURON}
spec:
  driversImage: {drivers_image}
  driverVersion: "{driver_version}"
  devicePluginImage: {device_plugin_image}
  nodeMetricsImage: {node_metrics_image}
{scheduler_block}  selector:
    {NFD_LABEL_KEY}: "{NFD_LABEL_VALUE}"
""")


def delete_device_config(oc: OcRunner) -> None:
    """Delete the DeviceConfig CR."""
    oc.run("delete", "DeviceConfig", DEVICE_CONFIG_NAME,
           "-n", NAMESPACE_NEURON, "--ignore-not-found=true",
           "--wait=true", "--timeout=300s", timeout=330)


def delete_nfd_rule(oc: OcRunner) -> None:
    """Delete the Neuron NodeFeatureRule."""
    oc.run("delete", "NodeFeatureRule", NFD_RULE_NAME,
           "-n", NAMESPACE_NEURON, "--ignore-not-found=true", timeout=30)


def delete_nfd_instance(oc: OcRunner) -> None:
    """Delete the NodeFeatureDiscovery instance."""
    oc.run("delete", "NodeFeatureDiscovery", NFD_INSTANCE_NAME,
           "-n", NAMESPACE_NFD, "--ignore-not-found=true",
           "--wait=true", "--timeout=120s", timeout=150)
