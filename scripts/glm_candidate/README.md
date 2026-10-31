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

Do not point the old serving container at these files. Its existing bind-mounted
entrypoint and uncommitted external deployment scripts remain untouched. An image
build is not a runtime qualification or permission for cutover/restart/inference.
