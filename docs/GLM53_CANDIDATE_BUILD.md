# GLM candidate build — 2026-10-31

**Not deployed.** `configs/glm53-production.json` still records the active service.
No live inference, GPU startup, restart or performance qualification was performed
as part of this candidate preparation.

## Built artifact

| Input/artifact | Identity |
|---|---|
| Recipe commit | `bf5f94523a8251029cedae86bf61f8ce37fac218` |
| Recipe patch/extras hash | `789e8f3bdfa2` (123 patches) |
| TensorFold v0.6.0 commit | `c4646171139ee8a3c38103eaa1699dad226ec12b` |
| Base | `nvcr.io/nvidia/pytorch@sha256:2140e699b3beaf7f96a0081fd9c9406bc3832b435cdb60dfa2d261f7d2f34a1c` |
| Candidate tag | `tensorfold-glm53:v0.6.0-789e8f3bdfa2-h100` |
| Candidate image ID | `sha256:09cb4a76ca5ee2080c3f50bca7985c904c5b48f741f61940ffa734d35ffe179c` |
| Platform / size | linux/amd64 / 24,479,387,346 bytes (shared layers included) |

The tag exists locally; this is not a published registry artifact. The image
includes the H100 per-rank device adaptation at build time and an immutable
supervisor entrypoint. Startup does not rewrite engine source. It does not replace
or modify the current production image/container or its bind-mounted entrypoint.

Selected dependencies match production: av 18.1.0, xgrammar 0.2.8, transformers
5.20.1, tokenizers 0.23.1 and the same NGC torch/triton versions. Full resolved
package versions and tooling hashes are in the build evidence. A selected-package
constraint file is not a complete transitive dependency lock.

## Validation and failure history

- Initial strict build stopped at upstream 0117: its context predates 0115's
  rejection diagnostics. An offline replay also found stale 0119 context after
  0118's exit-on-broken initializer.
- The checked-in patch applicator refreshes those two contexts and hunk counts
  only, preserving every added/deleted upstream line. All 123 patches subsequently
  applied with zero fuzz; build/import/shell-syntax checks passed.
- All 16 upstream CPU regression tools passed: tool/result images, MPO input,
  SSE, Anthropic usage, HTTP bodies, tool-tag parsing, unoffered-call diagnostics,
  broken health, queued cancellation, kept reasoning, conversation continuation,
  fork points, spill blocks, KV shards, literal request tokens and reply markers.
- The local supervisor integration check passed with fake ranks: device mapping,
  failure propagation, unexpected-zero-exit handling, SIGTERM cleanup, no orphan
  ranks, and unchanged engine source across repeated starts.
- A complete combined rerun passed all **17/17 checks**; the guarded launcher
  accepted that exact image/evidence in dry-run mode, without creating a container.
  [Combined CPU evidence](../evidence/glm53-candidate-cpu-20261031T122404103999Z.json)
  and [successful build evidence](../evidence/glm53-candidate-build-20261031T122026669334Z.json).
- Early supervisor TEST-harness failures are retained too. They were corrected
  by isolating shell initialization and making disposable test scratch executable;
  these failures were not GPU engine failures.

CPU containers use runc, no GPU requests, no external network, a read-only root,
bounded resources, and isolated scratch. Tokenizer checks mount metadata only,
not model weights or the Hugging Face cache. Stub HTTP servers bind only inside
the isolated test container. Sanitized reports are retained under `evidence/`;
build output and raw CPU diagnostics are kept outside this public repository.

## Tooling and qualification boundary

See [`scripts/glm_candidate/README.md`](../scripts/glm_candidate/README.md) for
the build, CPU validator and guarded launch interfaces. All default to dry-run.
The launcher requires explicit execution/idle confirmation, full passing CPU
evidence for the exact image, a previously stopped production container, free
ports and idle GPUs. It never automatically stops/removes production, and the
candidate restart policy is `no`.

CPU checks do **not** validate H100 kernels, runtime memory, native-context GPU
behavior, output quality, throughput, automatic restart recovery, or production
tail latency. No deployment or performance improvement is claimed. The older
external deployment scripts still need a maintenance-window rollback review;
retaining an old image alone does not fix their startup mutation/removal hazards.
