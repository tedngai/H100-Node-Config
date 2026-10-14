#!/usr/bin/env python3
"""Read existing reports and print a comparison table; no server access."""

import argparse
import json
from pathlib import Path

from common import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="*", type=Path)
    args = parser.parse_args()
    paths = args.reports or sorted((ROOT / "evidence").glob("*.json"))
    excluded = set()
    for qualification in (ROOT / "evidence").glob("*.json"):
        item = json.loads(qualification.read_text())
        if item.get("kind") == "probe-qualification" and item.get("report"):
            excluded.add(Path(item["report"]).name)
    print("| Report | Profile | Mode | Cache | Input | Output | Concurrency | Status | Aggregate tok/s | p50 TTFT s |")
    print("|---|---|---|---|---:|---:|---:|---|---:|---:|")
    for path in paths:
        data = json.loads(path.read_text())
        if data.get("kind") != "benchmark":
            continue
        work, summary = data["workload"], data.get("summary", {})
        def number(key):
            value = summary.get(key)
            return f"{value:.2f}" if value is not None else "unavailable"
        status = "excluded" if path.name in excluded else "checks passed" if data["passed"] else "FAILED"
        print(f'| {path.name} | {work["profile"]} | {work["mode"]} | {work["cache"]} | {work["prompt_tokens"]} | '
              f'{work["output_tokens"]} | {work["concurrency"]} | {status} | '
              f'{number("median_aggregate_tokens_per_second")} | {number("ttft_p50_seconds")} |')
    print("\nCompare only matched workloads, cache states, and modes. Failed runs are not qualified results.")


if __name__ == "__main__":
    main()
