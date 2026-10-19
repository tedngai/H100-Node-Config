# GLM-5.3-Flash production runbook

The service is `tensorfold-glm53-flash-exl3-1m` on `http://127.0.0.1:8888/v1`.
The preserved Qwen rollback is `sglang-qwen38-flash-next-088-mamba070-20261016t020846`
on `http://127.0.0.1:8011/v1`.

## Read-only checks

```bash
curl -s http://127.0.0.1:8888/health | python3 -m json.tool
curl -s http://127.0.0.1:8888/v1/models
docker ps --filter name=tensorfold-glm53-flash-exl3-1m
nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader
tail -20 /home/tngai/GLM53-Flash-EXL3-H100-Test/logs/rank0.log
```

Expected: `ok: true`, `context_length: 1048576`, `pool_tokens: 2965504`,
`streams.max: 4`, four GPUs at ~62-64 GB, container `Up`.

## Restart the GLM service

The launcher is outside this repository (it mounts the local checkpoint and
kernel cache):

```bash
cd /home/tngai/GLM53-Flash-EXL3-H100-Test
scripts/stop-tp4.sh
scripts/launch-tp4.sh
```

The launcher waits for `/health`; a warm restart took 184 s. Do not run it while
another full model is on the GPUs. The container's restart policy is
`unless-stopped`, so Docker starts it after a daemon/host restart.

## Stop GLM and restore Qwen

```bash
docker stop tensorfold-glm53-flash-exl3-1m
docker start sglang-qwen38-flash-next-088-mamba070-20261016t020846
# wait for http://127.0.0.1:8011/v1/models
```

Do not remove the Qwen container or image.

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
`GLM_LOG_DIR` can point the OOM audit at the rank-log directory
(default `/home/tngai/GLM53-Flash-EXL3-H100-Test/logs`).

## Failure handling

| Symptom | Action |
|---|---|
| `NCCL_NET_PLUGIN` / `gin_plugin` / `ibvwrap` warnings at start | make sure `NCCL_NET_PLUGIN=none` and `NCCL_GIN_ENABLE=0` are set |
| rank exits during startup | inspect `logs/rank{0..3}.log`; the launcher prints the tail |
| OOM at load | lower `CONTEXT`, `KV_POOL_GIB`, or raise `MEMORY_RESERVE_GIB` |
| warm benchmark reports <90% cache hits | check `TF_GLM_CACHE_ENTRIES=32`; keep the failure report |
| service busy before a benchmark | wait for idle; do not send a bounded test into live traffic |
| need to abort | `docker stop tensorfold-glm53-flash-exl3-1m`, then restore Qwen |

## Current policy

Capacity-first: work completion, runtime health, token accounting and telemetry
are separate. Queueing and low free memory are reported, not automatic failures.
`production_qualified` remains false for these bounded screens. No sustained-load
or overload test is implied by this runbook.
