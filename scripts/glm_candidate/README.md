# Offline candidate image tooling

These tools prepare an amd64 TensorFold image without changing the production
profile, existing deployment scripts, or serving container. No GPU is passed to
build or package-inspection containers. Nothing here automatically deploys.

```bash
# Dry-run: no Docker/Git commands or filesystem writes.
python3 -B scripts/glm_candidate/prepare.py \
  --recipe-repo /path/to/local/recipe-clone \
  --workspace /mnt/nvme1/glm53-candidates/unique-build-directory
```

Add `--execute` to authorize the build. The pinned recipe commit must be present
in the local clone and the digest-pinned amd64 base must already be installed.
An existing candidate tag or workspace is refused, not overwritten. Build context
and build output stay outside this public repository; sanitized non-overwriting
build evidence is written under `evidence/`. Resolved package versions are recorded.

The Dockerfile installs TensorFold from an immutable commit, applies the pinned
recipe patches, and bakes the H100 per-rank device selector into the image.
The candidate supervisor never rewrites engine source at startup. It terminates
all sibling ranks when one exits, treating an unexpected zero exit as failure.

The upstream patch/extras hash identifies upstream inputs, not the entire image:
the H100 adaptation and selected dependency constraints are additional inputs,
hashed separately in the build evidence. Constraints match selected production
packages; this is not a complete transitive dependency lock.

Two pinned upstream hunks have stale context after earlier patches: 0117 after
0115's rejection diagnostics, and 0119 after 0118's exit-on-broken initializer.
`apply_patches.py` refreshes only those context lines and hunk counts, preserving
every added/deleted line, then applies all 123 patches with zero fuzz. Unknown
context or an application failure stops the build.

## CPU-only checks

After a successful build:

```bash
python3 -B scripts/glm_candidate/validate.py \
  --build-evidence evidence/glm53-candidate-build-TIMESTAMP.json \
  --tokenizer-dir /path/to/pinned/checkpoint/snapshot \
  --output-dir /mnt/nvme1/glm53-candidates/unique-cpu-output-directory
```

Add `--execute` to run. The default suite covers 16 upstream regression tools.
Containers use runc, no GPU device requests, no external network, read-only root
filesystems, bounded CPU/RAM and disposable scratch. Only tokenizer/template
metadata files are mounted read-only; weights and the HF cache are not mounted.
HTTP tests serve stubs on container-local loopback, not the production endpoint.
`--case NAME` selects a subset, explicitly marked as partial in evidence. Raw test
output stays outside the repository; timestamped return codes/timings and image
identity are recorded under `evidence/`, including failures. CPU success does not
qualify the GPU engine, performance, restart recovery, or a production deployment.

Do not point the old serving container at these files. Its existing bind-mounted
entrypoint and uncommitted external deployment scripts remain untouched. An image
build is not a runtime qualification or permission for cutover/restart/inference.
