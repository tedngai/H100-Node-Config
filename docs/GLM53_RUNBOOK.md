# GLM-5.3-Flash production runbook

The promoted service is `tensorfold-glm53-candidate-789e8f3bdfa2`, served as
`pratt-medium` on `http://127.0.0.1:8011/v1`. Its versioned name is retained;
it is production, not a test container. The primary rollback is old GLM
`tensorfold-glm53-flash-exl3-1m`; Qwen is a secondary fallback. Both are stopped
with restart policy `no`. Never run two full models on these GPUs at once.

## Read-only checks

```bash
curl -s http://127.0.0.1:8011/health | python3 -m json.tool
curl -s http://127.0.0.1:8011/v1/models
docker ps --filter name=tensorfold-glm53-candidate-789e8f3bdfa2
nvidia-smi --query-gpu=index,memory.used,memory.free,utilization.gpu --format=csv,noheader
tail -20 /mnt/nvme1/glm53-candidates/window-20261031T130841Z/candidate-runtime/logs/rank0.log
```

Expected: `ok: true`, `context_length: 1048576`, `pool_tokens: 4345856`,
`streams.max: 4`, the recorded production image, container `Up`. Memory depends
on cached histories and allocator retention; historical idle HBM is not a
long-load guarantee. Current identities/paths are in `configs/glm53-production.json`.

## Restart the GLM service

Requires explicit maintenance approval and paused/drained external traffic.
Preserve the existing container and its mounted checkpoint/cache:

```bash
python3 -B scripts/glm_candidate/restart.py \
  --build-evidence evidence/glm53-candidate-build-20261031T122026669334Z.json \
  --execute --confirm-idle
# Wait for parsed /health ok=true, expected context/stream capacity and model ID.
curl -s http://127.0.0.1:8011/health | python3 -m json.tool
curl -s http://127.0.0.1:8011/v1/models | python3 -m json.tool
```

Run from this repository. Do not restart while another full model owns the GPUs.
The promoted image's real restart passed in 162.881 s; promotion readiness took
150.77 s. HTTP success alone is insufficient. The guarded tool verifies exact
image, idle health, same container/new start time, context/pool and unchanged
engine source. Only this selected service has `unless-stopped`.

**Do not use the older external `stop-tp4.sh` / `launch-tp4.sh` for a preserved-
container update or rollback:** they remove existing containers. Those scripts
remain outside this repository and were not rewritten during candidate validation.
Preparation tooling is under `scripts/glm_candidate/`; creation now refuses when
that same named container is already recorded as production. See
[the promotion record](GLM53_PROMOTION_20261031.md) for current evidence/status.

## Memory profile

```text
MEMORY_RESERVE_GIB=5
KV_POOL_GIB=22.5
pool_tokens=4345856
```

This host is dedicated to inference. The 22.5 GiB pool is the current tested
profile; cached histories and the CUDA allocator retain memory. Pre-promotion
long/mixed screens sampled 6813/8067 MiB free on GPU0/others; current promotion
results are recorded separately. Do not lower reserve below 5 GiB or raise pool
or concurrency without an approved experiment and re-running the
1M retrieval and 4-stream decode checks. Four simultaneous 1M requests are not
stress-tested.

## Primary rollback: restore the old GLM

Requires explicit maintenance approval, idle/drained traffic and no competing GPU
work. Preserve containers; change restart policies so only the selected one restarts:

```bash
docker update --restart no tensorfold-glm53-candidate-789e8f3bdfa2
docker stop -t 60 tensorfold-glm53-candidate-789e8f3bdfa2
docker update --restart unless-stopped tensorfold-glm53-flash-exl3-1m
docker start tensorfold-glm53-flash-exl3-1m
# Wait for parsed health/model/context, then run approved interface smoke.
```

The old image is `sha256:b8f133b9…`; its idempotent entrypoint/restart were proved.
After rollback, restore the correct production profile/container/log identity
before further benchmark audits. No `docker rm`, image pruning or legacy launch
script is needed. Qwen remains a separate preserved fallback on the same port;
select it only with explicit approval and its own SGLang configuration checks.
Do not remove either rollback image/container.

## Benchmarks

Each invocation is one bounded workload. The harness requires an idle service
and both confirmation flags.

```bash
cd /home/tngai/H100-Node-Config
python3 -B tests/glm_smoke.py --label glm53-smoke --execute --confirm-idle --vision
python3 -B tests/glm_benchmark.py --label glm53-short-c1-cold \
  --profile glm53-flash-exl3-1m --mode decode --cache cold --concurrency 1 \
  --prompt-tokens 1024 --output-tokens 256 --rounds 3 \
  --execute --confirm-idle
python3 -B tests/glm_benchmark.py --label glm53-32k-retrieval \
  --profile glm53-flash-exl3-1m --mode retrieval --cache cold --concurrency 1 \
  --prompt-tokens 32768 --output-tokens 256 --rounds 3 \
  --execute --confirm-idle
```

Reports are created exclusively under `evidence/`; failures are retained.
Default container and rank-log directory are read from `configs/glm53-production.json`.
`GLM_LOG_DIR` can explicitly override the log directory for an approved experiment.

## Failure handling

| Symptom | Action |
|---|---|
| `NCCL_NET_PLUGIN` / `gin_plugin` / `ibvwrap` warnings at start | make sure `NCCL_NET_PLUGIN=none` and `NCCL_GIN_ENABLE=0` are set |
| rank exits during startup | inspect the profile's rank-log paths; retain diagnostics outside the public repo |
| OOM at load | stop testing, preserve evidence and use approved rollback; do not silently tune the fixed profile |
| warm benchmark reports <90% cache hits | check `TF_GLM_CACHE_ENTRIES=32`; keep the failure report |
| service busy before a benchmark | wait for idle; do not send a bounded test into live traffic |
| need to abort | stop the promoted container and restore old GLM using the approved rollback sequence above |

## Current policy

Capacity-first: work completion, runtime health, token accounting and telemetry
are separate. Queueing and low free memory are reported, not automatic failures.
`production_qualified` remains false for these bounded screens. No sustained-load
or overload test is implied by this runbook.
