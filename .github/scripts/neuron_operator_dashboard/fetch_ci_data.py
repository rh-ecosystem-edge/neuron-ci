#!/usr/bin/env python
"""
Fetches AWS Neuron operator CI test results from GCS and produces a JSON
data file consumed by the dashboard HTML generator.

Adapted from rh-ecosystem-edge/nvidia-ci gpu_operator_dashboard.
"""
import argparse
import json
import os
import re
import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Set

import requests
from pydantic import BaseModel
import semver

from common.utils import logger

OCP_FULL_VERSION = "ocp_full_version"
NEURON_OPERATOR_VERSION = "neuron_operator_version"
NEURON_DRIVER_VERSION = "neuron_driver_version"

STATUS_SUCCESS = "SUCCESS"
STATUS_FAILURE = "FAILURE"
STATUS_ABORTED = "ABORTED"

GCS_API_BASE_URL = "https://storage.googleapis.com/storage/v1/b/test-platform-results/o"

# Matches both presubmit and rehearsal job paths for neuron-ci.
TEST_RESULT_PATH_REGEX = re.compile(
    r"pr-logs/pull/(?P<repo>[^/]+)/(?P<pr_number>\d+)/"
    r"(?P<job_name>(?:rehearse-\d+-)?pull-ci-rh-ecosystem-edge-neuron-ci-main-"
    r"(?P<ocp_version>\d+\.\d+)-stable-aws-neuron-operator-e2e(?P<job_suffix>[^/]*))"
    r"/(?P<build_id>[^/]+)"
)

# Matches periodic job paths.
PERIODIC_RESULT_PATH_REGEX = re.compile(
    r"logs/(?P<job_name>periodic-ci-rh-ecosystem-edge-neuron-ci-main-"
    r"(?P<ocp_version>\d+\.\d+)-stable-aws-neuron-operator-e2e(?P<job_suffix>[^/]*))"
    r"/(?P<build_id>\d+)"
)

PERIODIC_JOB_GCS_PREFIX = "logs/periodic-ci-rh-ecosystem-edge-neuron-ci-main-"

GCS_MAX_RESULTS_PER_REQUEST = 1000


def http_get_json(url: str, params: Dict[str, Any] | None = None,
                  headers: Dict[str, str] | None = None) -> Dict[str, Any]:
    response = requests.get(url, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_gcs_file_content(file_path: str) -> str:
    logger.info(f"Fetching file content for {file_path}")
    response = requests.get(
        url=f"{GCS_API_BASE_URL}/{urllib.parse.quote_plus(file_path)}",
        params={"alt": "media"},
        timeout=30,
    )
    response.raise_for_status()
    return response.content.decode("UTF-8")


def build_prow_job_url(finished_json_path: str) -> str:
    directory_path = finished_json_path[: -len("/finished.json")]
    return (
        "https://gcsweb-ci.apps.ci.l2s4.p1.openshiftapps.com"
        f"/gcs/test-platform-results/{directory_path}"
    )


class TestResultKey(BaseModel):
    ocp_full_version: str
    neuron_operator_version: str
    neuron_driver_version: str
    test_status: str
    pr_number: str
    job_name: str
    build_id: str

    class Config:
        frozen = True


@dataclass(frozen=True)
class TestResult:
    ocp_full_version: str
    neuron_operator_version: str
    neuron_driver_version: str
    test_status: str
    prow_job_url: str
    job_timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            OCP_FULL_VERSION: self.ocp_full_version,
            NEURON_OPERATOR_VERSION: self.neuron_operator_version,
            NEURON_DRIVER_VERSION: self.neuron_driver_version,
            "test_status": self.test_status,
            "prow_job_url": self.prow_job_url,
            "job_timestamp": self.job_timestamp,
        }

    def build_key(self) -> Tuple[str, str, str]:
        _, pr_number, job_name, build_id = extract_build_components(self.prow_job_url)
        return (pr_number, job_name, build_id)

    def has_exact_versions(self) -> bool:
        try:
            semver.VersionInfo.parse(self.ocp_full_version)
            return True
        except (ValueError, TypeError):
            return False


def fetch_filtered_files(pr_number: str, glob_pattern: str) -> List[Dict[str, Any]]:
    logger.info(f"Fetching files matching pattern: {glob_pattern}")
    params = {
        "prefix": f"pr-logs/pull/rh-ecosystem-edge_neuron-ci/{pr_number}/",
        "alt": "json",
        "matchGlob": glob_pattern,
        "maxResults": str(GCS_MAX_RESULTS_PER_REQUEST),
        "projection": "noAcl",
    }
    headers = {"Accept": "application/json"}
    all_items: List[Dict[str, Any]] = []
    next_page_token = None

    while True:
        if next_page_token:
            params["pageToken"] = next_page_token
        response_data = http_get_json(GCS_API_BASE_URL, params=params, headers=headers)
        all_items.extend(response_data.get("items", []))
        next_page_token = response_data.get("nextPageToken")
        if not next_page_token:
            break

    logger.info(f"Found {len(all_items)} files matching {glob_pattern}")
    return all_items


def fetch_pr_files(pr_number: str) -> Tuple[
    List[Dict[str, Any]], List[Dict[str, Any]],
    List[Dict[str, Any]], List[Dict[str, Any]]
]:
    logger.info(f"Fetching files for PR #{pr_number}")
    finished = fetch_filtered_files(pr_number, "**/finished.json")
    ocp = fetch_filtered_files(pr_number, "**/aws-neuron-operator-test/artifacts/ocp.version")
    operator = fetch_filtered_files(pr_number, "**/aws-neuron-operator-test/artifacts/operator.version")
    driver = fetch_filtered_files(pr_number, "**/aws-neuron-operator-test/artifacts/driver.version")
    return finished, ocp, operator, driver


def extract_build_components(path: str) -> Tuple[str, str, str, str]:
    original_path = path
    if "/artifacts/" in path:
        path = path.split("/artifacts/")[0] + "/"
    match = TEST_RESULT_PATH_REGEX.search(path)
    if not match:
        raise ValueError(f"Path regex mismatch: {original_path}")
    return (
        match.group("repo"),
        match.group("pr_number"),
        match.group("job_name"),
        match.group("build_id"),
    )


def filter_neuron_finished_files(
    all_finished_files: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Keep only top-level finished.json files for neuron e2e jobs."""
    preferred: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for file_item in all_finished_files:
        path = file_item.get("name", "")
        if "aws-neuron-operator-e2e" not in path or not path.endswith("/finished.json"):
            continue
        if "/artifacts/" in path:
            continue
        try:
            _, pr_number, job_name, build_id = extract_build_components(path)
            key = (pr_number, job_name, build_id)
        except ValueError:
            continue
        preferred[key] = file_item
    return list(preferred.values())


def build_files_lookup(
    finished_files: List[Dict[str, Any]],
    ocp_files: List[Dict[str, Any]],
    operator_files: List[Dict[str, Any]],
    driver_files: List[Dict[str, Any]],
) -> Tuple[Dict[Tuple[str, str, str], Dict[str, Dict[str, Any]]], Set[Tuple[str, str, str]]]:
    build_files: Dict[Tuple[str, str, str], Dict[str, Dict[str, Any]]] = {}
    all_builds: Set[Tuple[str, str, str]] = set()

    tagged: List[Tuple[Dict[str, Any], str]] = []
    for f in finished_files:
        tagged.append((f, "finished"))
    for f in ocp_files:
        tagged.append((f, "ocp"))
    for f in operator_files:
        tagged.append((f, "operator"))
    for f in driver_files:
        tagged.append((f, "driver"))

    for file_item, file_type in tagged:
        path = file_item.get("name", "")
        try:
            _, pr_number, job_name, build_id = extract_build_components(path)
        except ValueError:
            continue
        if build_id in ("latest-build.txt", "latest-build"):
            continue
        key = (pr_number, job_name, build_id)
        build_files.setdefault(key, {})[file_type] = file_item
        all_builds.add(key)

    return build_files, all_builds


def process_single_build(
    pr_number_arg: str,
    job_name: str,
    build_id: str,
    ocp_version: str,
    build_files: Dict[Tuple[str, str, str], Dict[str, Dict[str, Any]]],
) -> TestResult:
    key = (pr_number_arg, job_name, build_id)
    bfs = build_files[key]

    finished_content = fetch_gcs_file_content(bfs["finished"]["name"])
    finished_data = json.loads(finished_content)
    status = finished_data["result"]
    timestamp = finished_data["timestamp"]
    job_url = build_prow_job_url(bfs["finished"]["name"])

    ocp_exact = ocp_version
    operator_ver = "unknown"
    driver_ver = "unknown"

    if "ocp" in bfs:
        ocp_exact = fetch_gcs_file_content(bfs["ocp"]["name"]).strip()
    if "operator" in bfs:
        operator_ver = fetch_gcs_file_content(bfs["operator"]["name"]).strip()
    if "driver" in bfs:
        driver_ver = fetch_gcs_file_content(bfs["driver"]["name"]).strip()

    return TestResult(
        ocp_full_version=ocp_exact,
        neuron_operator_version=operator_ver,
        neuron_driver_version=driver_ver,
        test_status=status,
        prow_job_url=job_url,
        job_timestamp=str(timestamp),
    )


def process_tests_for_pr(
    pr_number: str,
    results_by_ocp: Dict[str, Dict[str, Any]],
) -> None:
    logger.info(f"Fetching test data for PR #{pr_number}")
    all_finished, ocp_files, operator_files, driver_files = fetch_pr_files(pr_number)
    finished_files = filter_neuron_finished_files(all_finished)
    build_files, all_builds = build_files_lookup(
        finished_files, ocp_files, operator_files, driver_files
    )
    logger.info(f"Found {len(all_builds)} builds to process")

    for pr_num, job_name, build_id in sorted(all_builds):
        full_path = f"pr-logs/pull/rh-ecosystem-edge_neuron-ci/{pr_num}/{job_name}/{build_id}"
        match = TEST_RESULT_PATH_REGEX.search(full_path)
        if not match:
            logger.warning(f"Could not parse: {pr_num}, {job_name}, {build_id}")
            continue

        key = (pr_num, job_name, build_id)
        if "finished" not in build_files.get(key, {}):
            logger.info(f"Skipping build {build_id} (no finished.json, job may still be running)")
            continue

        ocp_version = match.group("ocp_version")

        logger.info(f"Processing build {build_id} for OCP {ocp_version}")
        result = process_single_build(pr_num, job_name, build_id, ocp_version, build_files)

        results_by_ocp.setdefault(ocp_version, {"tests": [], "job_history_links": set()})

        job_history_url = (
            "https://prow.ci.openshift.org/job-history/gs/test-platform-results"
            f"/pr-logs/directory/{job_name}"
        )
        results_by_ocp[ocp_version]["job_history_links"].add(job_history_url)

        if result.has_exact_versions() and result.test_status != STATUS_ABORTED:
            results_by_ocp[ocp_version]["tests"].append(result.to_dict())


def list_periodic_job_prefixes() -> List[str]:
    """Discover all periodic job prefixes in GCS (one per OCP version)."""
    logger.info("Discovering periodic job prefixes...")
    params = {
        "prefix": PERIODIC_JOB_GCS_PREFIX,
        "delimiter": "/",
        "maxResults": "100",
        "alt": "json",
    }
    headers = {"Accept": "application/json"}
    response_data = http_get_json(GCS_API_BASE_URL, params=params, headers=headers)
    prefixes = response_data.get("prefixes", [])
    logger.info(f"Found {len(prefixes)} periodic job prefix(es)")
    return prefixes


def list_periodic_builds(job_prefix: str, max_builds: int = 10) -> List[str]:
    """List recent build IDs for a periodic job prefix."""
    params = {
        "prefix": job_prefix,
        "delimiter": "/",
        "maxResults": str(max_builds),
        "alt": "json",
    }
    headers = {"Accept": "application/json"}
    response_data = http_get_json(GCS_API_BASE_URL, params=params, headers=headers)
    build_prefixes = response_data.get("prefixes", [])
    build_ids = []
    for bp in build_prefixes:
        build_id = bp.rstrip("/").rsplit("/", 1)[-1]
        if build_id.isdigit():
            build_ids.append(build_id)
    build_ids.sort(reverse=True)
    return build_ids[:max_builds]


def process_periodic_build(
    job_name: str,
    build_id: str,
    ocp_version: str,
) -> Optional[TestResult]:
    """Process a single periodic build and return a TestResult, or None on failure."""
    base_path = f"logs/{job_name}/{build_id}"
    finished_path = f"{base_path}/finished.json"

    try:
        finished_content = fetch_gcs_file_content(finished_path)
    except requests.HTTPError:
        logger.info(f"No finished.json for periodic build {build_id}, skipping")
        return None

    finished_data = json.loads(finished_content)
    status = finished_data.get("result", STATUS_ABORTED)
    timestamp = finished_data.get("timestamp", 0)
    job_url = (
        f"https://prow.ci.openshift.org/view/gs/test-platform-results"
        f"/logs/{job_name}/{build_id}"
    )

    # The test step name mirrors the ci-operator test name
    test_step = job_name.rsplit("-", 1)[-1]  # e.g. "weekly"
    test_name = f"aws-neuron-operator-e2e-{test_step}"
    artifact_base = f"{base_path}/artifacts/{test_name}/aws-neuron-operator-test/artifacts"

    ocp_exact = ocp_version
    operator_ver = "unknown"
    driver_ver = "unknown"

    for file_name, setter in [
        ("ocp.version", "ocp"),
        ("operator.version", "operator"),
        ("driver.version", "driver"),
    ]:
        try:
            content = fetch_gcs_file_content(f"{artifact_base}/{file_name}").strip()
            if setter == "ocp":
                ocp_exact = content
            elif setter == "operator":
                operator_ver = content
            elif setter == "driver":
                driver_ver = content
        except requests.HTTPError:
            pass

    return TestResult(
        ocp_full_version=ocp_exact,
        neuron_operator_version=operator_ver,
        neuron_driver_version=driver_ver,
        test_status=status,
        prow_job_url=job_url,
        job_timestamp=str(timestamp),
    )


def process_periodic_tests(
    results_by_ocp: Dict[str, Dict[str, Any]],
    max_builds: int = 10,
) -> None:
    """Fetch and process results from periodic (cron-scheduled) jobs."""
    logger.info("Processing periodic job results...")
    prefixes = list_periodic_job_prefixes()

    for prefix in prefixes:
        job_name = prefix.strip("/").split("/", 1)[-1]
        match = PERIODIC_RESULT_PATH_REGEX.search(f"logs/{job_name}/0")
        if not match:
            logger.warning(f"Could not parse periodic prefix: {prefix}")
            continue

        ocp_version = match.group("ocp_version")
        logger.info(f"Processing periodic jobs for OCP {ocp_version}: {job_name}")

        build_ids = list_periodic_builds(prefix, max_builds=max_builds)
        logger.info(f"Found {len(build_ids)} recent builds")

        results_by_ocp.setdefault(ocp_version, {"tests": [], "job_history_links": set()})

        job_history_url = (
            "https://prow.ci.openshift.org/job-history/gs/test-platform-results"
            f"/logs/{job_name}"
        )
        results_by_ocp[ocp_version]["job_history_links"].add(job_history_url)

        for build_id in build_ids:
            logger.info(f"Processing periodic build {build_id}")
            result = process_periodic_build(job_name, build_id, ocp_version)
            if result and result.test_status != STATUS_ABORTED:
                results_by_ocp[ocp_version]["tests"].append(result.to_dict())


def process_closed_prs(results_by_ocp: Dict[str, Dict[str, Any]]) -> None:
    logger.info("Retrieving PR history...")
    url = "https://api.github.com/repos/rh-ecosystem-edge/neuron-ci/pulls"
    params = {"state": "closed", "base": "main", "per_page": "100", "page": "1"}
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    gh_token = os.environ.get("GITHUB_TOKEN")
    if gh_token:
        headers["Authorization"] = f"Bearer {gh_token}"
    else:
        logger.warning("GITHUB_TOKEN not set; GitHub API requests may be rate-limited")
    response_data = http_get_json(url, params=params, headers=headers)
    for pr in response_data:
        pr_number = str(pr["number"])
        logger.info(f"Processing PR #{pr_number}")
        process_tests_for_pr(pr_number, results_by_ocp)


def merge_tests(
    new_tests: List[Dict[str, Any]],
    existing_tests: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge tests keeping one result per (OCP, operator, driver) combination."""
    by_version: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}

    for item in existing_tests + new_tests:
        key = (
            item.get(OCP_FULL_VERSION, ""),
            item.get(NEURON_OPERATOR_VERSION, ""),
            item.get(NEURON_DRIVER_VERSION, ""),
        )
        by_version.setdefault(key, []).append(item)

    final: List[Dict[str, Any]] = []
    for version_results in by_version.values():
        successes = [r for r in version_results if r.get("test_status") == STATUS_SUCCESS]
        if successes:
            chosen = max(successes, key=lambda r: int(r.get("job_timestamp", "0")))
        else:
            chosen = max(version_results, key=lambda r: int(r.get("job_timestamp", "0")))
        final.append(chosen)

    final.sort(key=lambda x: int(x.get("job_timestamp", "0")), reverse=True)
    return final


def merge_and_save_results(
    new_results: Dict[str, Dict[str, Any]],
    output_file: str,
    existing_results: Dict[str, Dict[str, Any]] | None = None,
) -> None:
    merged = dict(existing_results) if existing_results else {}

    for ocp_version, version_data in new_results.items():
        existing = merged.get(ocp_version, {})
        merged_data = {"notes": [], "tests": [], "job_history_links": []}
        merged_data.update(existing)

        new_tests = version_data.get("tests", [])
        existing_tests = merged_data.get("tests", [])
        merged_data["tests"] = merge_tests(new_tests, existing_tests)

        new_links = version_data.get("job_history_links", set())
        existing_links = set(merged_data.get("job_history_links", []))
        existing_links.update(new_links)
        merged_data["job_history_links"] = sorted(existing_links)

        merged[ocp_version] = merged_data

    with open(output_file, "w") as f:
        json.dump(merged, f, indent=4)
    logger.info(f"Results saved to {output_file}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Neuron CI Test Matrix Data Fetcher")
    parser.add_argument(
        "--pr_number", default="all",
        help='PR number to process; use "all" for full history',
    )
    parser.add_argument(
        "--include_periodic", action="store_true", default=False,
        help="Also fetch results from periodic (cron-scheduled) jobs",
    )
    parser.add_argument("--baseline_data_filepath", required=True)
    parser.add_argument("--merged_data_filepath", required=True)
    args = parser.parse_args()

    existing_results: Dict[str, Dict[str, Any]] = {}
    try:
        with open(args.baseline_data_filepath, "r") as f:
            existing_results = json.load(f)
        logger.info(f"Loaded baseline data with {len(existing_results)} OCP versions")
    except FileNotFoundError:
        logger.info("No baseline data found, starting fresh")

    local_results: Dict[str, Dict[str, Any]] = {}
    if args.pr_number.lower() == "all":
        process_closed_prs(local_results)
    else:
        process_tests_for_pr(args.pr_number, local_results)

    if args.include_periodic:
        process_periodic_tests(local_results)

    merge_and_save_results(local_results, args.merged_data_filepath, existing_results)


if __name__ == "__main__":
    main()
