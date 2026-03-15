"""Thin wrapper around the ``oc`` CLI."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


@dataclass
class RunResult:
    returncode: int
    stdout: str | None
    stderr: str | None


class OcRunner:
    """Execute ``oc`` commands against a cluster."""

    def __init__(self, kubeconfig: str | None = None) -> None:
        self.kubeconfig = kubeconfig or os.environ.get("KUBECONFIG", "")
        if not self.kubeconfig:
            raise ValueError("KUBECONFIG must be set or passed to OcRunner")

    def run(self, *args: str, timeout: int = 60) -> RunResult:
        cmd = ["oc", *args]
        env = {**os.environ, "KUBECONFIG": self.kubeconfig}
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            return RunResult(proc.returncode, proc.stdout, proc.stderr)
        except subprocess.TimeoutExpired:
            return RunResult(1, None, f"Command timed out after {timeout}s")
        except FileNotFoundError:
            return RunResult(1, None, "oc binary not found")

    def apply_stdin(self, yaml_str: str, timeout: int = 30) -> RunResult:
        cmd = ["oc", "apply", "-f", "-"]
        env = {**os.environ, "KUBECONFIG": self.kubeconfig}
        proc = subprocess.run(
            cmd,
            input=yaml_str,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"oc apply failed (rc={proc.returncode}): {proc.stderr}"
            )
        return RunResult(proc.returncode, proc.stdout, proc.stderr)
