# Hy4-Flash FP8 on the four-H100 node

Status: **ready for operator testing; not workload-qualified**
(2026-11-18). GLM is **stopped and preserved**, not serving.
The operator explicitly cancelled automatic GLM restoration during the second
startup. The original trial controller was cancelled without running its
rollback or inference prompt. A readiness-only observer leaves both containers
untouched, including on failure. No workload qualification is claimed.

Readiness completed at **13:58:43 UTC**: health, model alias and effective
configuration checks passed. No inference prompts were submitted.
[Handoff evidence](../evidence/hy4-flash-operator-handoff-20261118T135843874237Z.json)
records the exact container/image and effective settings: TP4/DP1, DSA attention,
BF16 KV, no speculative decoding, static fraction 0.93, 32,768 context, maximum
four running requests and chunked prefill 4,096. Both Hy4 and the preserved GLM
have `restart=no`; only Hy4 is running.

The official amd64 image was downloaded and pinned to
`sha256:237b1a7e37c81be25d0e5ab77a06f5640a73a10bcbe239a00e4eb77046efc56b`
(registry digest `sha256:1ceda4a19a78db64c3f667c6a9b7644a7681819f13b45906a6bfc08edb3639ca`).
CPU-only, network-isolated checks found Hy4 model support and confirmed CLI flags
and Hunyuan parser choices. Installed versions: SGLang `0.0.0.dev1+g25c1c4394`,
PyTorch `2.14.1+cu130`, Transformers `5.19.0`. These checks are not GPU validation.

The first trial completed weight loading on all four H100s, but SGLang rejected
the 0.88 static-memory budget before allocating KV cache. It reported that a value
above 0.894 was required. No inference request ran. The exact 400k/8-stream GLM
service was restored healthy; the failed Hy4 container remains stopped/preserved.
See [trial evidence](../evidence/hy4-flash-trial-20261118T133516489333Z.json).

The operator approved a retry changing **only static memory to 0.93**, with a
new container name to preserve the first probe:
[`configs/hy4-flash-h100-mem093.json`](../configs/hy4-flash-h100-mem093.json).
This is not proof of fit or workload headroom. The external **start/stop wrappers
now select the 0.93 profile**, matching the operator-selected container.
Direct Python commands must select it explicitly with
`--config configs/hy4-flash-h100-mem093.json`; the original candidate JSON remains
unchanged as the failed probe record.

## Operator test endpoint

Use **`http://<this-node>:8011/v1`**, model
**`pratt-medium`**. Initial context is **32,768 tokens total**, not GLM's 400k.
Maximum running requests is four, sharing the available token pool; that is not
a throughput/concurrency qualification. The Hy4 container remains `restart=no`:
it is left running for testing but is not configured to return after a reboot.
No automated prompts or GLM restoration will follow the manual handoff.

## Recipe

- Official image: `lmsysorg/sglang:hy4-flash`, resolved to an immutable local
  image ID by `pin-image`. Support is on a dedicated upstream branch, not the
  older Qwen image or an arbitrary released wheel.
- Model: `tencent/Hy4-flash-FP8`, revision
  `003107fa248f5892064ab1c43af0a7003dd68c9b`.
- Download: 287,073,390,118 bytes of safetensors (~267.4 GiB). FP8 does **not**
  mean every parameter in the checkpoint is FP8.
- Weights: `/mnt/nvme2/huggingface`; runtime/kernel cache:
  `/mnt/nvme1/hy4-flash`. Neither belongs in Git.
- Alias/API retained: `pratt-medium`, `http://127.0.0.1:8011/v1`.
- Balanced strategy: TP4, prefill CUDA graphs disabled, **no speculative decoding**,
  no HiCache, no PD disaggregation. Native vision is retained.
- Initial H100 adaptations: 32,768 context, at most four running requests,
  chunked prefill 4,096, static memory fraction 0.88, Hunyuan reasoning/tool parsers.
  These are candidate settings, not measured capacity or performance.
- The supplied link is verified for **4×H200 141GB**, not **4×H100 80GB**.
  Preserve [the exact cookbook record](../configs/hy4-flash-cookbook.json);
  adaptations live in [a separate candidate](../configs/hy4-flash-h100.json).
  Do not claim the native 1M context or GLM's 400k context fits before testing.
- Model license: [Tencent Hy License](https://huggingface.co/tencent/Hy4-flash-FP8/blob/main/LICENSE),
  not Apache/MIT. Review its terms for your intended use.

## Matching start/stop scripts

Located beside the previous SGLang scripts:

```bash
cd /home/tngai/data/vllm-deepseek
./download_sglang_hy4_flash.sh --execute  # approved download only; no GPU use
./start_sglang_hy4_flash.sh              # safe dry run
./start_sglang_hy4_flash.sh --execute --confirm-idle
./stop_sglang_hy4_flash.sh --execute --confirm-idle
```

Startup refuses occupied GPUs or port 8011. Stop preserves the container and
sets `restart=no`. Start reuses an owned, identical stopped container; changed
recipes require a **new container name**, not automatic removal/recreation.
There is no automatic image pull, checkpoint download, old-service stop,
production promotion or auto-start policy on startup.

All live operations require fresh approval and paused/drained client traffic.
The `--confirm-idle` flag is an operator assertion, not a traffic firewall.
Keep port 8011 on the same trusted network; no authentication/firewall change
is part of this setup. No credentials are copied from the old deployment.
The public, ungated checkpoint needs no token in the serving container.

## Bounded idle-window trial and rollback

```bash
cd /home/tngai/H100-Node-Config
python3 -B scripts/hy4_flash/manage.py trial --execute --confirm-idle
```

This verifies complete checkpoint shards and the pinned image **before downtime**,
checks exact GLM identity and stable idle health, stops/preserves GLM with
`restart=no`, archives its stopped rank logs privately outside this repository
(the existing entrypoint truncates them on restart), launches Hy4, validates
health/model/context, and runs one bounded
chat request. A `finally` block stops/preserves Hy4 and restores the exact GLM
container and prior restart policy on either success or failure.
Only sanitized, timestamped evidence is written to `evidence/`; raw Docker
inspection, credentials, request text and live logs are not saved in Git.
The original GLM profile is not overwritten by a trial.

```bash
python3 -B scripts/hy4_flash/manage.py status --config configs/hy4-flash-h100-mem093.json
docker logs --tail 80 sglang-hy4-flash-h100-20261118-m093  # inspect locally, do not publish raw
```

If orchestration itself is interrupted, first stop the owned Hy4 container using
the wrapper. Verify all GPUs/port are free, then restore the **current 400k/8 GLM**
container from `configs/glm53-production.json`, not a historical GLM/Qwen fallback:

```bash
docker start tensorfold-glm53-400k-p8-20261106t165335
# Wait for /health ok=true, context_length=400000, streams.max=8 and model pratt-medium.
docker update --restart unless-stopped tensorfold-glm53-400k-p8-20261106t165335
```

Do not run both models at once. Preserve all containers, images and caches.
Promotion requires an explicit decision and more than a basic chat smoke:
tool calls, reasoning, vision, streaming, representative context/load and a real
container restart still need qualification.

Model-card recommendation: temperature 0.9, top_p 1.0; use
`chat_template_kwargs.reasoning_effort="no_think"` for direct answers or `"high"`
for thinking. The bounded marker smoke uses temperature zero deliberately.
