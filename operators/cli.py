#!/usr/bin/env python3
"""CLI entry point for operator installation/cleanup.

Usage:
    python -m operators install   # install all operators + DeviceConfig
    python -m operators cleanup   # reverse of install
"""

from __future__ import annotations

import argparse
import os
import sys

from operators.cleanup import cleanup_operators
from operators.main import NeuronInstallConfig, install_operators
from operators.oc import OcRunner


def _config_from_env() -> NeuronInstallConfig:
    return NeuronInstallConfig(
        drivers_image=os.environ.get("ECO_HWACCEL_NEURON_DRIVERS_IMAGE", ""),
        driver_version=os.environ.get("ECO_HWACCEL_NEURON_DRIVER_VERSION", ""),
        device_plugin_image=os.environ.get("ECO_HWACCEL_NEURON_DEVICE_PLUGIN_IMAGE", ""),
        node_metrics_image=os.environ.get("ECO_HWACCEL_NEURON_NODE_METRICS_IMAGE", ""),
        scheduler_image=os.environ.get("ECO_HWACCEL_NEURON_SCHEDULER_IMAGE", ""),
        scheduler_extension_image=os.environ.get("ECO_HWACCEL_NEURON_SCHEDULER_EXTENSION_IMAGE", ""),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AWS Neuron Operator installation orchestration",
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("install", help="Install operators and create DeviceConfig")
    sub.add_parser("cleanup", help="Remove operators and DeviceConfig")
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    oc = OcRunner()
    config = _config_from_env()

    if args.command == "install":
        install_operators(oc, config)
    elif args.command == "cleanup":
        cleanup_operators(oc)

    return 0


if __name__ == "__main__":
    sys.exit(main())
