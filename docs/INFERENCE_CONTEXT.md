# Inference context / operator handoff

**Session resume:** see [`SESSION_HANDOFF.md`](SESSION_HANDOFF.md) for current
container state, coding A/B status, blocked preflight, and resume steps.

**Current policy update:** new runs use [`BENCHMARK_POLICY.md`](BENCHMARK_POLICY.md):
waiting and low sampled GPU-free memory are advisory. Earlier stop instructions/
results below are historical, not the current acceptance rules.

Last updated: **2026-10-15, 21:53 UTC**, after the MTP-off attempt was blocked and
the MTP-on candidate restored.

**Latest result: PASS.** The approved one-second-staggered c6 cold 250K/4096 repeat
completed 60/60 requests without observed OOM or retractions. Median aggregate
283.45 tok/s; initial TTFT p95 58.604 s and latency p95 86.211 s (limited n=60
estimate). Pool usage was 88.78%; minimum sampled GPU-free remains 1,629 MiB.
Waiting peaked at 5 while sampled running reached 6. Final audit matched traffic and
found the service idle with unchanged identity/configuration. See
`MEMORY_FRACTION_FIRST.md`. Candidate remains on the unchanged 0.88 NEXTN/MTP-on
profile. The approved coding MTP-on arm completed 18/18 (64K input, 2K maximum
output, six clients, three rounds): median aggregate 529.76 tok/s, TTFT p50 7.32 s,
latency p50 22.98 s, no observed OOM/retractions; n=18, so p95 is unavailable.
Spec acceptance averaged 59.4%. A matched off candidate then started with FlashInfer
and speculation disabled. Its effective capacity was 1,536,000 slots; the top-level
active-cap field was null, while SGLang reported an explicit per-DP effective cap of
245. The harness has been updated to use that direct metric, without summing TP
duplicates. An audit found one unaccounted chat POST and one unknown route, so no
MTP-off inference was sent. The temporary candidate was stopped after idle checks;
the MTP-on container was restored and verified ready/idle at 21:53 UTC. Do not
switch or send another workload until a new isolated window is confirmed. See
`CODING_OPTIMIZATION_PLAN.md` and `SESSION_HANDOFF.md`.

## Current live candidate

- `sglang-qwen38-flash-next-088` is running at the existing endpoint, using the
  original pinned image, runtime settings and argv except memory fraction **0.88**.
  Original `sglang-qwen38-flash-next` is preserved and stopped, not deleted.
- Actual shared capacity **1,717,184** (+129,216 / 8.1% over baseline), effective
  active cap 48 unchanged; hybrid state slots 656 versus 611. Original baseline
  snapshot is unchanged. Guarded 90% capacity is about 1.545M slots.
- Smoke checks and three cold 32,768-input / 512-output c1 decode requests passed.
  Post-audits matched exact traffic and confirmed idle loads/unchanged candidate
  identity/configuration. Lowest sampled GPU-free memory was 3,967 MiB; this is
  not peak-workspace measurement or proof against OOM.
- Candidate remains running for testing, not production-qualified. Six-user 100K,
  200K, 230K, 250K/512, 250K/4096 and 256K/512 capacity screens passed; 0.90 remains untested. See
  `MEMORY_FRACTION_FIRST.md` and `results.md` for evidence and limitations. Baseline-only historical guidance
  below does not describe the current active container.
- The initial c6 100K cold decode screen failed strict no-queue after its first
  round (sampled waiting peak 5); all six requests completed with zero retractions.
  Sampled free memory fell below the 3 GiB stop floor (minimum 2,297 MiB). No later
  rounds were submitted under that old protocol. The subsequent explicitly approved
  capacity-first repeat passed three rounds; see the latest result above.

## Restart handoff

- The approved 32K scheduling-aware c2/c4/c6 cold/warm screen is complete; the
  original strict no-queue 32K c2 failure remains failed. The initial c6 warm run
  is excluded; its separately approved retry passed.
- Separate 100K c1 and 200K c1 cold synthetic retrieval screens each passed three
  serial requests with all expected codes, zero cache hits, waiting, or retractions.
  Latest evidence: [100K](../evidence/baseline-100k-c1-cold-retrieval-20261014T182637.536737Z.json)
  and [200K](../evidence/baseline-200k-c1-cold-retrieval-20261014T204621.754710Z.json).
- A separately approved 260K c1 cold synthetic retrieval screen also passed all
  three requests; all codes were recovered with zero cached tokens, sampled waiting,
  or retractions. The post-run audit matched exactly three `/generate` requests and
  found idle loads with unchanged configuration/identity. This is not full-context,
  decode-throughput, or production qualification; see [`results.md`](results.md).
- A separately approved 100K c1 cold/warm decode screen then passed three timed
  requests per state. Cold median aggregate rate was 99.44 tok/s; warm was 243.75
  tok/s after two explicit warmups, with 99,968/100,000 tokens cached on every timed
  request. Both audits matched expected traffic, found no other inference routes,
  and confirmed idle loads/unchanged configuration. These small samples do not
  establish p95 or production behavior; see [`LONG_CONTEXT_DECODE_100K.md`](LONG_CONTEXT_DECODE_100K.md).
- The separately approved 200K c1 cold/warm decode screen also passed three timed
  requests per state. Cold median aggregate rate was 53.32 tok/s; warm was 236.52
  tok/s after two explicit warmups, with 199,936/200,000 tokens cached on each timed
  request. Both audits matched expected traffic, found no other inference routes,
  and confirmed idle loads/unchanged configuration. p95 is unavailable; this does
  not qualify 260K decode, higher concurrency, or production behavior. See
  [`LONG_CONTEXT_DECODE_200K.md`](LONG_CONTEXT_DECODE_200K.md).
- The [200K post-run audit](../evidence/baseline-200k-c1-cold-retrieval-post-traffic-20261014T204705.576313Z.json)
  matched all three `/generate` requests and recorded idle loads. Configuration and
  container identity were unchanged. This is only functional synthetic retrieval
  screening, not throughput or production qualification.
- No repeat, full 262K, higher-concurrency, or candidate experiment is authorized.
  Before any future live run, review its protocol, obtain explicit approval and a
  fresh quiet-window confirmation, and recheck traffic/identity. The last idle
  sample is historical, not a current guarantee.

## State following reboot (20:47 UTC; historical checkpoint)

- Host driver/NVML is healthy at **580.178.04**. The preserved original container
  was started with approval at 14:42:54 UTC; same image, argv and effective settings.
- Post-reboot smoke and cold c1 (1,024 input / 512 output, three rounds) passed:
  median aggregate 257.83 tok/s and TTFT 0.213 s.
- Warm c1 failed with **0 cached tokens** after one identical-prompt warmup.
  A separately approved diagnostic with **two explicit warmups** then passed:
  960/1,024 cached tokens on all three timed requests, median aggregate 245.23 tok/s
  and TTFT 0.209 s.
- Subsequently approved short c2/c4/c6 cold/warm screening passed all six cases:
  median aggregate cold/warm throughput **430/430**, **795/780**, **1,038/1,064 tok/s**.
  Every warm timed request reused 960/1,024 tokens. Observed active peaks reached
  2/4/6 with zero sampled queue/retraction counts and zero per-request retractions.
  Traffic access counts matched all 96 requests (72 timed + 24 warmups). No candidate
  applied; last service check was ready with zero active/waiting requests.
- Approved 32K c1 cold retrieval and cold/warm decode then passed: all codes recalled
  in three retrieval requests; median decode throughput **185/251 tok/s** cold/warm,
  TTFT **0.987/0.219 s**. Warm timed requests reused **32,704/32,768 tokens** after two
  explicit warmups. Eleven submitted requests matched access counts, with zero
  observed queue/retraction counts and no configuration or post-reboot metadata drift.
- Subsequent warm 32K retrieval passed (three codes recalled in all three timed
  requests, 99.80% cache reuse, median TTFT 0.218 s). **Cold 32K c2 decode then
  failed the strict no-queue check** in round one: peak waiting 1, peak active 2,
  zero per-request retractions. Both requests completed; all remaining concurrency
  tests stopped. Seven total request access records matched the stage. Service is
  ready and idle; baseline settings and post-reboot model metadata are unchanged.
- A separately approved single-round c2 diagnostic then reproduced only early
  waiting (observed reads about 0.523–1.147 s after submission), with prefill counters
  progressing and first text at 1.217/1.952 s. Both requests completed with no
  retractions, then a newer idle publication. Two access records matched the two
  requests. Classification supports transient prefill waiting, **not** no-queue
  performance qualification; the original failed benchmark remains failed.
- Scheduling-aware 32K screening then passed c2 cold/warm, c4 cold/warm and c6 cold:
  aggregate output rates **261/425**, **333/763**, **367/unqualified tok/s** respectively.
  Initial cold prefill waiting is explicitly permitted/reported only in this separate
  protocol. C6 warm stopped in timed round two: 7 sampled running requests for 6
  benchmark clients, one unrelated chat access record, and failed fresh-idle drain.
  Entire warm c6 invocation excluded; no third round submitted. Total stage traffic
  was 90 benchmark requests plus one unrelated chat request. Baseline configuration
  and post-reboot model metadata remain unchanged; last loads were idle.
- Cached model revision/configuration metadata changed since the preserved baseline;
  tokenizer hash is unchanged. Do not treat pre/post-reboot timing as a matched
  checkpoint comparison. Details and evidence are in [`results.md`](results.md).
- Requested c6 warm retry preflight passed setup, GPU, configuration, container
  identity/start and model-metadata checks. Traffic audit then found **three
  `/v1/chat/completions` accesses** since the prior stop, so the quiet-window check
  failed despite zero running/waiting at the final point sample. **No inference
  request was sent.** Evidence is linked in `results.md`.
- After the operator reconfirmed a best-effort quiet window, fresh preflight at
  17:25 passed. The bounded c6 warm retry completed all three timed rounds: median
  aggregate **1,023.31 tok/s**, TTFT p50 **0.442 s**, zero sampled waiting and zero
  retractions; each request reused 32,704/32,768 prompt tokens. The post-run audit
  matched all 30 `/generate` requests and found idle loads. This remains scheduling-
  aware screening, not strict no-queue or production qualification. The original
  partial c6 warm run remains excluded. See `results.md` for reports.
- **The approved baseline screening stage is complete.** No candidate, larger
  contexts or further inference are authorized by this result alone. Preserve the
  strict no-queue failure; await separate approval for any next experiment. No
  cache flush, restart or server change is authorized by this handoff.
- One 100K c1 cold retrieval attempt was explicitly approved, but its fresh preflight
  found 43 `/v1/chat/completions` requests from `172.16.34.24` since the previous
  checkpoint (latest 17:31:05 UTC). This differs from the `.32.24` address mentioned
  by the operator. Final loads were idle at 17:54, but the isolation check failed;
  **no inference was sent**. Do not retry automatically; a fresh quiet window and
  explicit approval are required. See `results.md` for evidence.
- Following fresh quiet-window confirmation, the 100K c1 cold retrieval completed
  all three rounds: exact 100,000-token prompts, all codes recovered, zero cached
  tokens/retractions, peak waiting 0. Median TTFT **3.377 s**, latency **3.468 s**;
  the 11.53 tok/s summary reflects only 40-token answers. Post-run audit matched
  three `/generate` requests and found idle loads. This is synthetic retrieval
  screening only, not decode-throughput or production qualification. No 200K or
  candidate run is authorized by it. Evidence is in `results.md`.
- The separately approved 200K c1 cold retrieval also passed three rounds: exact
  200,000-token prompts, all codes recovered, zero cache hits/retractions, peak
  waiting 0. Median TTFT **7.754 s**, latency **7.845 s**; the 5.10 tok/s figure
  reflects only 40-token answers. Post-run audit matched three `/generate` requests
  and found idle loads. This remains synthetic retrieval screening, not throughput
  or production qualification. At that historical checkpoint, no 260K,
  higher-concurrency, or candidate run was authorized; the later 260K result is
  summarized at the top of this handoff and in `results.md`.

The following pre-reboot handoff is retained as historical context.

## Live service at handoff

Read-only snapshot: [`prereboot-handoff-20261014T143350.721160Z.json`](../evidence/prereboot-handoff-20261014T143350.721160Z.json).

- Endpoint/model alias: `http://127.0.0.1:8011`, `pratt-medium`.
- Checkpoint: `Qwen/Qwen3.8-Flash-Next-FP8`; SGLang reports `qwen4_exp` /
  `Qwen4ExpForConditionalGeneration`.
- Model context: **262,144 total tokens**, including output. Effective maximum input
  is **262,138 tokens**; auto truncation is disabled.
- **48 active requests** configured (automatically selected, not an explicit
  launch argument); one DP1 shared pool has **1,587,968 token slots**.
- Four H100 80GB HBM3, NVLink all-to-all topology; TP4/EP4/DP1.
- Static memory fraction `0.85`; prefill chunk `8192`; KV dtype `auto`;
  Mamba state BF16; FlashInfer linear-attention prefill/decode and Triton verify.
- Effective speculation EAGLE, three steps, top-k 1, four draft tokens.
- SGLang build `0.0.0.dev1+gd91c3682b`, image ID
  `sha256:4175343ed77bb05000ee5019b2dc3fa8999cd52edd6da7e5b75d23306c445c5f`.
- At **14:33 UTC**, server was ready, reported zero active and waiting requests,
  and still matched the immutable captured baseline. Docker container ID,
  launch argv, image, and start time were unchanged.
- Docker restart policy is **`no`**. After a host reboot the container is expected
  to remain stopped; SGLang will not automatically resume.

## Driver/reboot reason

Before reboot, the loaded kernel driver was **580.173.02** while host NVML was
**580.178**. Host `nvidia-smi` failed with `Driver/library version mismatch`;
`nvidia-smi` inside the running container worked and reported four H100s.
Container GPU memory was already about 80–81 GiB of 81.6 GiB per device due to
the running inference service. No driver modification, restart, or shutdown was
performed by the experiment setup.

The user stated they will reboot the host. **This workspace did not initiate the
reboot.** Check the host driver before starting the model afterward; do not assume
reboot alone fixes the library/kernel mismatch.

## Benchmark state

Preliminary unchanged-baseline screening is documented in [`results.md`](results.md):

- 1,024-token input / 512 output, cold-prefix forced decode, three rounds at
  client concurrency 2 / 4 / 6: median aggregate throughput **423 / 772 / 1,023
  tokens/s**, respectively; median per-request throughput **225 / 194 / 178
  tokens/s**. Sampled peaks reached 2 / 4 / 6 active requests with zero waiting
  requests or retractions.
- Chat, separated-reasoning, synthetic tool-call checks passed.
- One retrieval check each at 1,024 and 32,768 input tokens passed, but are not
  a broad quality test.
- Cold concurrency runs had no unrelated generation starts inside those exact
  request windows according to the retained traffic audit. Other clients were
  active in the broader session, so results remain screening data, not a
  dedicated isolated-load production qualification.
- Single-user decode and warm-prefix throughput remain incomplete. Initial c1
  and warm probes are explicitly excluded/failed; reports and reasons are retained.
- Six short requests do **not** prove six simultaneous 256K-context users. The
  pool budget guard rejects six 260K prompts plus 1,024 output tokens.

No candidate profile has been deployed. The active admission cap remains 48; the
planned `admission-6` is only a review candidate. No results should be attributed
to that or any other experimental candidate.

## Resume after reboot

Follow [`NEXT_EXPERIMENT.md`](NEXT_EXPERIMENT.md). In brief:

1. Run host `nvidia-smi` and check it agrees with `/proc/driver/nvidia/version`.
   Stop if NVML still reports a mismatch; do not upgrade/reinstall drivers as
   part of a benchmark task.
2. Check `docker ps -a` for `sglang-qwen38-flash-next`. Restart policy is `no`.
   If the drivers are healthy and the user wants inference restored, manually
   start the **existing** container (do not recreate it or pull its mutable tag):
   `docker start sglang-qwen38-flash-next`.
3. Wait for readiness, then read `/get_server_info`, `/v1/models`, and `/v1/loads`.
   Verify exact model, image/container ID, argv, build, context, cap, capacity,
   backend/speculation settings; save a post-reboot inventory.
4. Treat GPU/cache/startup behavior after reboot as a new observation. Do not
   assume the previous in-memory cache or service state persisted.
5. Do not send inference benchmarks while unrelated production clients are
   active. Get a quiet window, then rerun baseline c1 and warm checks before
   expanding long-context/concurrency runs.

Useful project checks (no inference):

```bash
cd /home/tngai/H100-Node-Config
python3 -B tests/validate_setup.py --inventory
python3 -B tests/capture_baseline.py --label post-reboot
python3 -B tests/summarize.py
```

`validate_setup.py --inventory` is read-only and requires the endpoint to be
available; `capture_baseline.py` also records container/GPU inventory. Never pass
`--initialize` to baseline capture. For approved inference, the scripts require
both `--execute` and `--confirm-idle`, check `/v1/loads` before a run, and preserve
results in timestamped evidence files.
