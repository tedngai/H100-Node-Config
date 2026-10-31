#!/usr/bin/env python3
"""Isolated pinned candidate build. No production mutation, GPU access or inference."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

RECIPE_COMMIT = "bf5f94523a8251029cedae86bf61f8ce37fac218"
TF_COMMIT = "c4646171139ee8a3c38103eaa1699dad226ec12b"
PATCHES_HASH = "789e8f3bdfa2"
EXTRAS = "av==18.1.0 xgrammar>=0.2.8,<0.3"
BASE_IMAGE = "nvcr.io/nvidia/pytorch@sha256:2140e699b3beaf7f96a0081fd9c9406bc3832b435cdb60dfa2d261f7d2f34a1c"
IMAGE = "tensorfold-glm53:v0.6.0-789e8f3bdfa2-h100"
ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def patch_hash(patches: Path) -> str:
    digest = hashlib.sha256()
    for patch in sorted(patches.glob("*.patch")):
        digest.update(patch.read_bytes())
    digest.update((EXTRAS + "\n").encode())
    return digest.hexdigest()[:12]


def run(args: list[str], **kwargs) -> str:
    return subprocess.check_output(args, text=True, **kwargs).strip()


def write_evidence(path: Path, value: dict) -> None:
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def outside_repo(path: Path) -> Path:
    path = path.expanduser().resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError("build context/logs must be outside the public repository")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe-repo", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True,
                        help="new directory outside this repo; never overwritten")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    workspace = outside_repo(args.workspace)
    recipe = args.recipe_repo.expanduser().resolve()
    manifest = {
        "schema_version": 1, "kind": "glm53-candidate-build", "production_changed": False,
        "recipe_commit": RECIPE_COMMIT, "tensorfold_commit": TF_COMMIT,
        "upstream_patch_hash": PATCHES_HASH, "base_image": BASE_IMAGE, "image": IMAGE,
        "gpu_access": False, "deployed": False,
    }
    print(json.dumps(manifest, indent=2))
    if not args.execute:
        print("Dry run only; pass --execute to build without GPU access.")
        return 0
    if workspace.exists():
        raise ValueError("workspace already exists; choose a fresh directory")
    if subprocess.run(["docker", "image", "inspect", IMAGE], stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL).returncode == 0:
        raise ValueError("candidate tag already exists; refusing to overwrite it")
    if run(["git", "-C", str(recipe), "rev-parse", RECIPE_COMMIT + "^{commit}"]) != RECIPE_COMMIT:
        raise ValueError("pinned recipe commit unavailable")
    base = json.loads(run(["docker", "image", "inspect", BASE_IMAGE]))[0]
    if base["Architecture"] != "amd64":
        raise ValueError("base must be linux/amd64")
    docker_root = Path(run(["docker", "info", "--format", "{{.DockerRootDir}}"])).parent
    if shutil.disk_usage(docker_root).free < 45 * 1024**3:
        raise ValueError("need at least 45 GiB free under Docker root")
    workspace.mkdir(parents=True)
    context = workspace / "context"
    context.mkdir()
    archive = workspace / "recipe.tar"
    subprocess.run(["git", "-C", str(recipe), "archive", "--format=tar", "-o", str(archive),
                    RECIPE_COMMIT, "patches", "tools"], check=True)
    with tarfile.open(archive) as source:
        source.extractall(context, filter="data")
    if patch_hash(context / "patches") != PATCHES_HASH:
        raise ValueError("patch/extras hash mismatch; refusing build")
    shutil.copytree(HERE, context / "h100", ignore=shutil.ignore_patterns("__pycache__"))
    manifest["base_image_id"] = base["Id"]
    manifest["patch_count"] = len(list((context / "patches").glob("*.patch")))
    manifest["tooling_sha256"] = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(HERE.iterdir()) if p.is_file()
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    evidence = ROOT / "evidence" / f"glm53-candidate-build-{stamp}.json"
    manifest["started_at"] = datetime.now(timezone.utc).isoformat()
    command = ["docker", "build", "--platform", "linux/amd64", "--network", "default",
               "--build-arg", "BASE_IMAGE=" + BASE_IMAGE, "--build-arg", "TF_COMMIT=" + TF_COMMIT,
               "--build-arg", "RECIPE_COMMIT=" + RECIPE_COMMIT,
               "--build-arg", "PATCHES_HASH=" + PATCHES_HASH, "-t", IMAGE,
               "-f", str(context / "h100/Dockerfile"), str(context)]
    print("Build output outside repo:", workspace / "build.log", flush=True)
    try:
        with (workspace / "build.log").open("x") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        image = json.loads(run(["docker", "image", "inspect", IMAGE]))[0]
        manifest.update(image_id=image["Id"], architecture=image["Architecture"],
                        image_size_bytes=image["Size"], success=True)
        packages = run(["docker", "run", "--rm", "--network", "none", "--runtime", "runc",
                        "-e", "NVIDIA_VISIBLE_DEVICES=void", "--entrypoint", "python", image["Id"],
                        "-B", "-c", "import importlib.metadata,json; print(json.dumps({d.metadata['Name']:d.version for d in importlib.metadata.distributions()},sort_keys=True))"])
        manifest["resolved_packages"] = json.loads(packages)
    except (subprocess.CalledProcessError, ValueError) as exc:
        manifest.update(success=False, failure_type=type(exc).__name__)
        raise
    finally:
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_evidence(evidence, manifest)
        print("Sanitized evidence:", evidence, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
