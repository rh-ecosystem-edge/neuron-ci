"""Wait utilities for NFD workers, node labels, device plugin, and Neuron resources.

Extracted from eco-gotests neuronhelpers/wait.go and await/await.go.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from operators.constants import (
    DEVICE_PLUGIN_PREFIX,
    NAMESPACE_KMM,
    NAMESPACE_NFD,
    NAMESPACE_NEURON,
    NAMESPACE_USER_WORKLOAD_MONITORING,
    NEURON_CAPACITY_ID,
    NFD_LABEL_KEY,
    NFD_LABEL_VALUE,
)

if TYPE_CHECKING:
    from operators.oc import OcRunner


def wait_for_nfd_workers(oc: OcRunner, timeout: int = 300) -> None:
    """Wait for NFD worker DaemonSet to be fully ready.

    Matches eco-gotests neuronhelpers/config.go waitForNFDWorkersReady().
    """
    print(f"  Waiting for NFD workers (timeout={timeout}s)...")
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        elapsed = int(time.monotonic() + timeout - deadline)

        r = oc.run(
            "get", "daemonsets", "-n", NAMESPACE_NFD,
            "-o", "json", timeout=15,
        )
        if r.returncode != 0:
            time.sleep(10)
            continue

        try:
            data = json.loads(r.stdout or "{}")
        except json.JSONDecodeError:
            time.sleep(10)
            continue

        for ds in data.get("items", []):
            name = ds.get("metadata", {}).get("name", "")
            if "worker" not in name:
                continue
            status = ds.get("status", {})
            ready = status.get("numberReady", 0)
            desired = status.get("desiredNumberScheduled", 0)

            if ready > 0 and ready == desired:
                print(f"    NFD workers ready: {ready}/{desired}")
                return

            print(f"    NFD worker DaemonSet {name}: {ready}/{desired} ({elapsed}s)...")
            break

        time.sleep(10)

    raise RuntimeError(f"NFD workers did not become ready within {timeout}s")


def wait_for_neuron_node_labels(oc: OcRunner, timeout: int = 300) -> None:
    """Wait for at least one node to have the Neuron NFD label.

    Matches eco-gotests await/await.go NeuronNodesLabeled().
    """
    print(f"  Waiting for Neuron node labels (timeout={timeout}s)...")
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        elapsed = int(time.monotonic() + timeout - deadline)

        r = oc.run(
            "get", "nodes",
            "-l", f"{NFD_LABEL_KEY}={NFD_LABEL_VALUE}",
            "--no-headers",
            timeout=15,
        )
        if r.returncode == 0 and r.stdout and r.stdout.strip():
            count = len(r.stdout.strip().splitlines())
            print(f"    Found {count} Neuron-labeled node(s)")
            return

        print(f"    No Neuron-labeled nodes yet ({elapsed}s)...")
        time.sleep(10)

    raise RuntimeError(
        f"No nodes labeled with {NFD_LABEL_KEY}={NFD_LABEL_VALUE} "
        f"within {timeout}s"
    )


def _dump_diagnostics(oc: OcRunner) -> None:
    """Collect diagnostic info when device plugin wait fails."""
    print("\n--- Device plugin wait DIAGNOSTICS ---")

    print("\n[Module CRs in namespace]")
    r = oc.run("get", "Module", "-n", NAMESPACE_NEURON, "-o", "yaml", timeout=15)
    if r.returncode == 0:
        print(r.stdout or "  (empty)")
    else:
        print(f"  (not found or error: {r.stderr})")

    print("\n[DaemonSets in namespace]")
    r = oc.run("get", "daemonsets", "-n", NAMESPACE_NEURON, "-o", "wide", timeout=15)
    print(r.stdout or "  (none)")

    print("\n[Pods in namespace]")
    r = oc.run("get", "pods", "-n", NAMESPACE_NEURON, "-o", "wide", timeout=15)
    print(r.stdout or "  (none)")

    print("\n[Build pods in KMM namespace]")
    r = oc.run("get", "pods", "-n", NAMESPACE_KMM, "-o", "wide", timeout=15)
    print(r.stdout or "  (none)")

    print("\n[Neuron-labeled nodes]")
    r = oc.run("get", "nodes", "-l", f"{NFD_LABEL_KEY}={NFD_LABEL_VALUE}",
               "--show-labels", timeout=15)
    print(r.stdout or "  (none)")

    print("\n[DeviceConfig status]")
    r = oc.run("get", "DeviceConfig", "-n", NAMESPACE_NEURON, "-o", "yaml", timeout=15)
    if r.returncode == 0:
        print(r.stdout or "  (empty)")
    else:
        print(f"  (not found or error: {r.stderr})")

    print("\n[Events in neuron namespace (last 20)]")
    r = oc.run("get", "events", "-n", NAMESPACE_NEURON,
               "--sort-by=.lastTimestamp", timeout=15)
    if r.returncode == 0 and r.stdout:
        lines = r.stdout.strip().splitlines()
        for line in lines[-20:]:
            print(f"  {line}")
    else:
        print("  (none)")

    print("\n--- End diagnostics ---\n")


def wait_for_device_plugin(oc: OcRunner, timeout: int = 600) -> None:
    """Wait for Neuron device plugin DaemonSet to be ready.

    Matches eco-gotests await/await.go DevicePluginDeployment().
    """
    print(f"  Waiting for device plugin DaemonSet (timeout={timeout}s)...")
    deadline = time.monotonic() + timeout
    diag_printed_at = 0

    while time.monotonic() < deadline:
        elapsed = int(time.monotonic() + timeout - deadline)

        r = oc.run(
            "get", "daemonsets", "-n", NAMESPACE_NEURON,
            "-o", "json", timeout=15,
        )
        if r.returncode != 0:
            time.sleep(10)
            continue

        try:
            data = json.loads(r.stdout or "{}")
        except json.JSONDecodeError:
            time.sleep(10)
            continue

        for ds in data.get("items", []):
            name = ds.get("metadata", {}).get("name", "")
            if not name.startswith(DEVICE_PLUGIN_PREFIX):
                continue
            status = ds.get("status", {})
            ready = status.get("numberReady", 0)
            desired = status.get("desiredNumberScheduled", 0)

            if desired > 0 and ready == desired:
                print(f"    Device plugin DaemonSet ready: {ready}/{desired}")
                return

            print(f"    Device plugin {name}: {ready}/{desired} ({elapsed}s)...")

            if desired == 0 and elapsed >= 120 and elapsed - diag_printed_at >= 180:
                _dump_diagnostics(oc)
                diag_printed_at = elapsed
            break

        time.sleep(10)

    _dump_diagnostics(oc)
    raise RuntimeError(
        f"Neuron device plugin DaemonSet did not become ready within {timeout}s"
    )


def wait_for_neuron_resources(oc: OcRunner, timeout: int = 600) -> None:
    """Wait for aws.amazon.com/neurondevice resources on labeled nodes.

    Matches eco-gotests await/await.go AllNeuronNodesResourceAvailable().
    """
    print(f"  Waiting for Neuron device resources on nodes (timeout={timeout}s)...")
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        elapsed = int(time.monotonic() + timeout - deadline)

        r = oc.run(
            "get", "nodes",
            "-l", f"{NFD_LABEL_KEY}={NFD_LABEL_VALUE}",
            "-o", "json",
            timeout=15,
        )
        if r.returncode != 0:
            time.sleep(10)
            continue

        try:
            data = json.loads(r.stdout or "{}")
        except json.JSONDecodeError:
            time.sleep(10)
            continue

        nodes = data.get("items", [])
        if not nodes:
            print(f"    No Neuron-labeled nodes found ({elapsed}s)...")
            time.sleep(10)
            continue

        all_ready = True
        for node in nodes:
            node_name = node.get("metadata", {}).get("name", "?")
            capacity = node.get("status", {}).get("capacity", {})
            neuron_count = int(capacity.get(NEURON_CAPACITY_ID, "0"))

            if neuron_count <= 0:
                print(f"    Node {node_name}: no {NEURON_CAPACITY_ID} yet ({elapsed}s)...")
                all_ready = False
                break

        if all_ready:
            total = sum(
                int(n.get("status", {}).get("capacity", {}).get(NEURON_CAPACITY_ID, "0"))
                for n in nodes
            )
            print(f"    All {len(nodes)} node(s) report Neuron resources (total={total})")
            return

        time.sleep(10)

    raise RuntimeError(
        f"Neuron device resources did not appear on nodes within {timeout}s"
    )


def wait_for_user_workload_monitoring(oc: OcRunner, timeout: int = 300) -> None:
    """Wait for the user workload monitoring Prometheus pods to be ready.

    After enabling user workload monitoring via the cluster-monitoring-config
    ConfigMap, the cluster-monitoring-operator deploys a Prometheus instance
    in openshift-user-workload-monitoring. This function waits for at least
    one prometheus-user-workload pod to reach Running state.
    """
    print(f"  Waiting for user workload monitoring pods (timeout={timeout}s)...")
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        elapsed = int(time.monotonic() + timeout - deadline)

        r = oc.run(
            "get", "pods", "-n", NAMESPACE_USER_WORKLOAD_MONITORING,
            "-l", "app.kubernetes.io/name=prometheus",
            "--no-headers",
            timeout=15,
        )

        if r.returncode == 0 and r.stdout and r.stdout.strip():
            for line in r.stdout.strip().splitlines():
                parts = line.split()
                if len(parts) >= 3 and parts[2] == "Running":
                    print(f"    User workload monitoring is ready")
                    return

        print(f"    User workload monitoring pods not ready yet ({elapsed}s)...")
        time.sleep(10)

    raise RuntimeError(
        f"User workload monitoring pods did not become ready within {timeout}s"
    )
