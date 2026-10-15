#!/usr/bin/env python3
"""Resolve candidate launch arguments offline. Prints commands; never executes them."""

import argparse
import json
import shlex

from common import ROOT


def modify_argv(argv, replacements, removals):
    argv = list(argv)
    for flag in list(removals) + list(replacements):
        positions = [i for i, value in enumerate(argv) if value == flag or value.startswith(flag + "=")]
        if len(positions) > 1:
            raise ValueError("Repeated launch flag: " + flag)
        if positions:
            index = positions[0]
            end = index + 1
            if argv[index] == flag and end < len(argv) and not argv[end].startswith("--"):
                end += 1
            del argv[index:end]
    for flag, value in replacements.items():
        argv.append(flag)
        if value is not None:
            argv.append(str(value))
    return argv


def resolve_profile(name):
    baseline = json.loads((ROOT / "configs/baseline.json").read_text())
    candidates = json.loads((ROOT / "configs/candidates.json").read_text())
    if name not in candidates:
        raise ValueError("Unknown profile: " + name)
    candidate = candidates[name]
    # Capacities depend on allocation, not just launch flags; always recapture them.
    allocation = {"max_total_num_tokens", "max_mamba_cache_size", "status"}
    if name in ("mtp-off", "mtp-shallow", "memory-088-mtp-off"):
        # SGLang reserves input-token slots based on speculative depth.
        allocation.add("max_req_input_len")
    expected = {k: v for k, v in baseline["server"]["config"].items()
                if k not in allocation | set(candidate["ignore_expected"])}
    expected.update(candidate["expected_overrides"])
    return {
        "name": name, "description": candidate["description"],
        "deployment_status": "captured baseline" if name == "baseline" else "not deployed",
        "validation": "captured configuration only; no performance or correctness qualification",
        "image_id": baseline["container"]["image_id"],
        "argv": modify_argv(baseline["container"]["argv"], candidate["set"], candidate["remove"]),
        "expected_config": expected,
        "baseline_evidence": baseline["evidence"],
        "requires_approved_restart": name != "baseline",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", nargs="?", default="baseline")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--shell", action="store_true", help="Print SGLang argv only; does not run it")
    args = parser.parse_args()
    if args.list:
        print((ROOT / "configs/candidates.json").read_text())
        return
    profile = resolve_profile(args.name)
    print(shlex.join(profile["argv"]) if args.shell else json.dumps(profile, indent=2))


if __name__ == "__main__":
    main()
