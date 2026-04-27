#!/usr/bin/env python
"""
Generates an HTML test-matrix dashboard from Neuron CI JSON data.

Adapted from rh-ecosystem-edge/nvidia-ci gpu_operator_dashboard.
"""
import json
import argparse

import semver
from typing import Dict, List, Any
from datetime import datetime, timezone

from common.utils import logger
from common.templates import load_template
from neuron_operator_dashboard.fetch_ci_data import (
    OCP_FULL_VERSION,
    NEURON_OPERATOR_VERSION,
    NEURON_DRIVER_VERSION,
    STATUS_ABORTED,
)


def ts_to_str(ts: str) -> str:
    try:
        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, TypeError, OSError):
        return "unknown"


def generate_test_matrix(ocp_data: Dict[str, Dict[str, Any]]) -> str:
    header = load_template("header.html")
    html_content = header
    main_table_template = load_template("main_table.html")
    sorted_keys = sorted(ocp_data.keys(), reverse=True)
    html_content += build_toc(sorted_keys)

    for ocp_key in sorted_keys:
        entry = ocp_data[ocp_key]
        notes = entry.get("notes", [])
        results = entry.get("tests", [])

        valid_results = [
            r for r in results
            if r.get("test_status") != STATUS_ABORTED
        ]

        notes_html = build_notes(notes)
        table_rows_html = build_table_rows(valid_results)
        job_history_html = build_job_history(valid_results)

        block = main_table_template
        block = block.replace("{ocp_key}", ocp_key)
        block = block.replace("{table_rows}", table_rows_html)
        block = block.replace("{notes}", notes_html)
        block = block.replace("{job_history}", job_history_html)
        html_content += block

    footer = load_template("footer.html")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    footer = footer.replace("{LAST_UPDATED}", now_str)
    html_content += footer
    return html_content


def build_table_rows(results: List[Dict[str, Any]]) -> str:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for r in results:
        ocp_full = r.get(OCP_FULL_VERSION, "unknown")
        grouped.setdefault(ocp_full, []).append(r)

    selected_rows: List[Dict[str, Any]] = []
    for ocp_full, rows in grouped.items():
        version_groups: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            ver_key = row.get(NEURON_OPERATOR_VERSION, "unknown")
            version_groups.setdefault(ver_key, []).append(row)

        for ver, ver_results in version_groups.items():
            has_success = any(r["test_status"] == "SUCCESS" for r in ver_results)
            if has_success:
                chosen = max(
                    [r for r in ver_results if r["test_status"] == "SUCCESS"],
                    key=lambda r: int(r.get("job_timestamp", "0")),
                )
            else:
                chosen = max(ver_results, key=lambda r: int(r.get("job_timestamp", "0")))
            selected_rows.append({"ocp_full": ocp_full, "ver": ver, "chosen": chosen})

    selected_rows.sort(key=lambda r: int(r["chosen"].get("job_timestamp", "0")), reverse=True)

    rows_html = ""
    for entry in selected_rows:
        ocp_full = entry["ocp_full"]
        chosen = entry["chosen"]
        label = entry["ver"]
        driver = chosen.get(NEURON_DRIVER_VERSION, "")
        if driver and driver != "unknown":
            label = f"{label} (driver {driver})"
        url = chosen.get("prow_job_url", "#")
        status = chosen.get("test_status", "FAILURE")
        timestamp = ts_to_str(chosen.get("job_timestamp", "0"))

        if status == "SUCCESS":
            link_class = "success"
            status_html = '<span class="status-success">&#10004; Passed</span>'
        else:
            link_class = "failed"
            status_html = '<span class="status-failure">&#10008; Failed</span>'

        rows_html += f"""<tr>
<td>{ocp_full}</td>
<td><a class="{link_class}" href="{url}">{label}</a></td>
<td>{status_html}</td>
<td><span class="timestamp">{timestamp}</span></td>
</tr>
"""

    return rows_html


def build_job_history(results: List[Dict[str, Any]]) -> str:
    if not results:
        return ""

    sorted_results = sorted(results, key=lambda r: int(r.get("job_timestamp", "0")))

    if sorted_results:
        latest_ts = ts_to_str(sorted_results[-1].get("job_timestamp", "0"))
    else:
        return ""

    squares = []
    for r in sorted_results:
        status = r.get("test_status", "FAILURE")
        css_class = "success" if status == "SUCCESS" else "failure"
        ts = ts_to_str(r.get("job_timestamp", "0"))
        url = r.get("prow_job_url", "#")
        driver = r.get(NEURON_DRIVER_VERSION, "unknown")
        tooltip = f"Status: {status} | Driver: {driver} | {ts}"
        squares.append(
            f'<a href="{url}" class="job-square {css_class}" title="{tooltip}"></a>'
        )

    squares_html = "\n".join(squares)
    return f"""<div style="margin-top: 12px;">
<strong>Job History</strong> <span class="timestamp">Latest: {latest_ts}</span>
<div class="job-history">
{squares_html}
</div>
</div>
"""


def build_notes(notes: List[str]) -> str:
    if not notes:
        return ""
    items = "\n".join(f"<li>{n}</li>" for n in notes)
    return f"""<details><summary>Notes</summary>
<ul>
{items}
</ul>
</details>
"""


def build_toc(ocp_keys: List[str]) -> str:
    toc_links = ", ".join(
        f'<a href="#ocp-{v}">{v}</a>' for v in ocp_keys
    )
    return f"""<div class="toc">
<strong>OpenShift Versions</strong>
{toc_links}
</div>
"""


def main():
    parser = argparse.ArgumentParser(description="Neuron CI Dashboard Generator")
    parser.add_argument("--dashboard_html_filepath", required=True)
    parser.add_argument("--dashboard_data_filepath", required=True)
    args = parser.parse_args()

    with open(args.dashboard_data_filepath, "r") as f:
        ocp_data = json.load(f)
    logger.info(f"Loaded JSON data with keys: {list(ocp_data.keys())}")

    html_content = generate_test_matrix(ocp_data)

    with open(args.dashboard_html_filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
    logger.info(f"Dashboard generated: {args.dashboard_html_filepath}")


if __name__ == "__main__":
    main()
