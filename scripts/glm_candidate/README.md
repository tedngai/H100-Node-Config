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

Add `--execute` to run. The default suite covers 16 upstream regression tools
plus a local supervisor integration test using fake rank processes (17 checks).
Containers use runc, no GPU device requests, no external network, read-only root
filesystems, bounded CPU/RAM and disposable scratch. Only tokenizer/template
metadata files are mounted read-only; weights and the HF cache are not mounted.
HTTP tests serve stubs on container-local loopback, not the production endpoint.
`--case NAME` selects a subset, explicitly marked as partial in evidence. Raw test
output stays outside the repository; timestamped return codes/timings and image
identity are recorded under `evidence/`, including failures. CPU success does not
qualify the GPU engine, performance, restart recovery, or a production deployment.

## Candidate launcher (maintenance window only)

`launch.py` defaults to a dry run. It reads the current production profile, a
successful build record and a full passing CPU-suite record for the same image.
It creates a separately named container using the immutable image ID, with
`restart=no`, isolated external logs/cache, and the current memory/context policy.
It does not stop, remove or modify the production container or its configuration.

Execution requires both `--execute --confirm-idle`. The existing production
container must already be stopped, all four GPUs must have at most 4096 MiB each
allocated, and both serving/rendezvous ports must be free. An existing candidate
or runtime directory is refused. Readiness requires JSON `ok: true`, the expected
engine/model/context/stream capacity and a usable pool. A failed start stops only
the candidate created by that invocation, preserving it and its diagnostics.

Before using this launcher, agree on traffic draining and prepare/test a safe
rollback. The older external entrypoint's startup mutation is not fixed by the
candidate image; leaving that shared production mount untouched is intentional.
Do not use the old stop script for cutover: it removes the rollback container.
No automatic rollback, restart-policy promotion, tuning, or benchmark is implied.

After the 2026-10-31 operator-approved promotion, that versioned container's role
is production with `unless-stopped`. Its name/identity were retained. Creation
now refuses if the same name is already selected in the production profile;
do not recreate it or use preparation commands as a production redeploy shortcut.
Actual service/default audit paths are in `configs/glm53-production.json`.

`restart.py --build-evidence PATH --execute --confirm-idle` performs an explicitly
approved real restart of the named candidate only. Without both flags it refuses
before any external action. It verifies the build/image, idle health, unchanged
container/image identity, a new start time, native-context readiness and unchanged
installed engine source. It writes timestamped evidence, never promotes or removes
containers, and does not restart the old production container.

Do not repoint the old serving container at these preparation files. Its device
adaptation was repaired separately in the approved maintenance window and its
restart proved before promotion; unrelated external deployment edits were
preserved. An image build alone is not runtime qualification or permission for
cutover/restart/inference.
