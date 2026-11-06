# GLM-5.3-Flash production runbook

The serving container is `tensorfold-glm53-400k-p8-20261106t165335`, served as
`pratt-medium` on `http://127.0.0.1:8011/v1`. Context is 400,000 tokens per
request, prompt plus reply; at most 8 streams share the pool. This is not a
per-user quota. The primary rollback is previous production
`tensorfold-glm53-candidate-789e8f3bdfa2` (1M context / 4 streams, same image).
The intermediate 400k/4 container, older GLM and Qwen are additional preserved
fallbacks, all stopped with restart policy `no`. Never run two full models on
these GPUs at once. Current 400k/8 settings passed
[bounded workload validation](GLM53_400K_VALIDATION_20261106.md), not multi-day stability qualification.

## Read-only checks

```bash
curl -s http://127.0.0.1:8011/health | python3 -m json.tool
curl -s http://127.0.0.1:8011/v1/models
docker ps --filter name=tensorfold-glm53-400k-p8-20261106t165335
nvidia-smi --query-gpu=index,memory.used,memory.free,utilization.gpu --format=csv,noheader
tail -20 /mnt/nvme1/glm53-candidates/context-change-20261106T165335760866Z/parallel8/logs/rank0.log
```

Expected: `ok: true`, `context_length: 400000`, `pool_tokens: 3698688`,
`streams.max: 8`, the recorded production image, container `Up`. Memory depends
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
The same image's earlier 1M/4-stream restart passed in 162.881 s; current
400k/8 startup took 156.111 s. These are different settings. HTTP success alone
is insufficient. The guarded tool follows the production profile and verifies exact
image, idle health, same container/new start time, context/pool and unchanged
engine source. Only this selected service has `unless-stopped`.

**Do not use the older external `stop-tp4.sh` / `launch-tp4.sh` for a preserved-
container update or rollback:** they remove existing containers. Those scripts
remain outside this repository and were not rewritten during candidate validation.
Preparation tooling is under `scripts/glm_candidate/`; the original four-stream
candidate launcher is not a reconfiguration tool and must not recreate production. See
[the promotion record](GLM53_PROMOTION_20261031.md) for current evidence/status.

## Memory profile

```text
MEMORY_RESERVE_GIB=5
KV_POOL_GIB=22.5
pool_tokens=3698688
```

This host is dedicated to inference. The pool cap and reserve were retained,
but pool rows changed automatically with the 400k context. Fresh-start free HBM
was 12444/13598 MiB on GPU0/others. Subsequent bounded checks sampled actual
eight-way decoding, passed near-390k retrieval and both context refusals, and
completed a 120-request / 662.8 s soak. Driver-reported free HBM stayed above
10202/11470 MiB in the final run; later idle memory was flat. These are sampled,
short-window observations, not guaranteed headroom or multi-day stability.
Historical 1M/4-stream measurements are not current workload evidence.
Do not change reserve, pool, context or concurrency without approval and separate
workload validation. Cached histories and the CUDA allocator retain memory;
neither fresh-start headroom nor a smaller context proves bounded long-run growth.

## Primary rollback: restore the previous 1M/4-stream service

Requires explicit maintenance approval, idle/drained traffic and no competing GPU
work. Preserve containers; change restart policies so only the selected one restarts:

```bash
docker update --restart no tensorfold-glm53-400k-p8-20261106t165335
docker stop -t 60 tensorfold-glm53-400k-p8-20261106t165335
docker start tensorfold-glm53-candidate-789e8f3bdfa2
docker update --restart unless-stopped tensorfold-glm53-candidate-789e8f3bdfa2
# Wait for parsed health/model/context, then run approved interface smoke.
```

The rollback uses the same image (`sha256:09cb4a76…`), but restores
`context_length: 1048576`, `streams.max: 4` and `pool_tokens: 4345856`.
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
  --profile glm53-flash-exl3-400k --mode decode --cache cold --concurrency 1 \
  --prompt-tokens 1024 --output-tokens 256 --rounds 3 \
  --execute --confirm-idle
python3 -B tests/glm_benchmark.py --label glm53-32k-retrieval \
  --profile glm53-flash-exl3-400k --mode retrieval --cache cold --concurrency 1 \
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
