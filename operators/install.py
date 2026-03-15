"""OLM operator installation helpers.

Creates Namespace, OperatorGroup, Subscription, and waits for CSV to succeed.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from operators.constants import CATALOG_NAMESPACE

if TYPE_CHECKING:
    from operators.oc import OcRunner


def install_operator(
    oc: OcRunner,
    *,
    namespace: str,
    package_name: str,
    catalog_source: str,
    channel: str,
    operator_group_name: str,
    subscription_name: str,
    target_namespaces: list[str] | None = None,
    timeout: int = 600,
) -> None:
    """Install an operator via OLM.

    1. Create namespace (if it doesn't exist)
    2. Create OperatorGroup
    3. Create Subscription
    4. Wait for CSV to reach Succeeded phase
    """
    print(f"\n--- Installing {package_name} in {namespace} ---")

    _ensure_namespace(oc, namespace)
    _create_operator_group(oc, namespace, operator_group_name, target_namespaces)
    _create_subscription(
        oc, namespace, subscription_name, package_name, catalog_source, channel,
    )
    _wait_for_csv(oc, namespace, package_name, timeout)

    print(f"--- {package_name} installed successfully ---\n")


def _ensure_namespace(oc: OcRunner, namespace: str) -> None:
    r = oc.run("get", "namespace", namespace, timeout=10)
    if r.returncode == 0:
        print(f"  Namespace {namespace} already exists")
        return

    print(f"  Creating namespace {namespace}")
    oc.apply_stdin(f"""\
apiVersion: v1
kind: Namespace
metadata:
  name: {namespace}
""")


def _create_operator_group(
    oc: OcRunner,
    namespace: str,
    name: str,
    target_namespaces: list[str] | None,
) -> None:
    r = oc.run(
        "get", "operatorgroup", name, "-n", namespace, timeout=10,
    )
    if r.returncode == 0:
        print(f"  OperatorGroup {name} already exists")
        return

    if target_namespaces:
        ns_list = "\n".join(f"    - {ns}" for ns in target_namespaces)
        spec = f"""\
  targetNamespaces:
{ns_list}"""
    else:
        spec = "  {}"

    print(f"  Creating OperatorGroup {name}")
    oc.apply_stdin(f"""\
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: {name}
  namespace: {namespace}
spec:
{spec}
""")


def _create_subscription(
    oc: OcRunner,
    namespace: str,
    name: str,
    package_name: str,
    catalog_source: str,
    channel: str,
) -> None:
    r = oc.run("get", "subscription", name, "-n", namespace, timeout=10)
    if r.returncode == 0:
        print(f"  Subscription {name} already exists")
        return

    print(f"  Creating Subscription {name} (channel={channel}, source={catalog_source})")
    oc.apply_stdin(f"""\
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: {name}
  namespace: {namespace}
spec:
  channel: "{channel}"
  installPlanApproval: Automatic
  name: {package_name}
  source: {catalog_source}
  sourceNamespace: {CATALOG_NAMESPACE}
""")


def _wait_for_csv(
    oc: OcRunner,
    namespace: str,
    package_name: str,
    timeout: int,
) -> None:
    """Wait for the ClusterServiceVersion to reach Succeeded phase."""
    print(f"  Waiting for {package_name} CSV to succeed (timeout={timeout}s)...")
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        elapsed = int(time.monotonic() + timeout - deadline)

        r = oc.run(
            "get", "csv", "-n", namespace,
            "-o", "json",
            timeout=30,
        )
        if r.returncode != 0:
            print(f"    Cannot list CSVs yet ({elapsed}s)...")
            time.sleep(10)
            continue

        try:
            data = json.loads(r.stdout or "{}")
        except json.JSONDecodeError:
            time.sleep(10)
            continue

        for item in data.get("items", []):
            csv_name = item.get("metadata", {}).get("name", "")
            phase = item.get("status", {}).get("phase", "")

            if package_name in csv_name:
                if phase == "Succeeded":
                    print(f"    CSV {csv_name} is Succeeded")
                    return
                print(f"    CSV {csv_name} phase: {phase} ({elapsed}s)...")
                break

        time.sleep(10)

    raise RuntimeError(
        f"{package_name} CSV did not reach Succeeded within {timeout}s"
    )


def uninstall_operator(
    oc: OcRunner,
    *,
    namespace: str,
    subscription_name: str,
    operator_group_name: str,
) -> None:
    """Uninstall an operator by removing Subscription, CSV, OperatorGroup, and Namespace."""
    print(f"\n--- Uninstalling operator from {namespace} ---")

    # Get CSV name from subscription
    r = oc.run(
        "get", "subscription", subscription_name, "-n", namespace,
        "-o", "jsonpath={.status.currentCSV}",
        timeout=10,
    )
    csv_name = (r.stdout or "").strip() if r.returncode == 0 else ""

    # Delete subscription
    oc.run("delete", "subscription", subscription_name, "-n", namespace,
           "--ignore-not-found=true", timeout=30)

    # Delete CSV
    if csv_name:
        oc.run("delete", "csv", csv_name, "-n", namespace,
               "--ignore-not-found=true", timeout=30)

    # Delete operator group
    oc.run("delete", "operatorgroup", operator_group_name, "-n", namespace,
           "--ignore-not-found=true", timeout=30)

    # Delete namespace
    oc.run("delete", "namespace", namespace,
           "--ignore-not-found=true", "--wait=true", "--timeout=120s", timeout=150)

    print(f"--- Uninstalled operator from {namespace} ---\n")
