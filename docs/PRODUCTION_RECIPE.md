# Frozen production recipe — 2026-10-16, 03:13 UTC

The operator requested freezing the current serving recipe and observing real
production traffic. **Do not resume experiments or tune it automatically.** Further
benchmarks, cache flushes, image changes, recreation or restarts require fresh
approval. The repository records the hold point; it does not deploy anything.

## Hold point

- Container: `sglang-qwen38-flash-next-088-mamba070-20261016t020846`.
- Profile: `memory-088-mamba-070`; model `Qwen/Qwen3.8-Flash-Next-FP8`, served as
  `pratt-medium` on host port **8011**.
- Pinned image: `sha256:4175343ed77bb05000ee5019b2dc3fa8999cd52edd6da7e5b75d23306c445c5f`.
  Preserve this image and the existing container; do not pull/recreate using a
  mutable nightly tag. PLE is enabled automatically in this pinned build; no new
  PLE launch flag was added to the serving container.
- The existing model argv uses the repository name without an explicit checkpoint
  revision. Preserve the model cache during this hold. Cached revision/config
  fingerprints were recorded in earlier inventories, but are not proof of the exact
  revision loaded by a process. This freeze is not a fully revision-pinned rebuild
  manifest; pinning a checkpoint or changing offline-loading behavior would be a
  separate, reviewed recipe change, not silently added to this production hold.
- Static memory **0.88**, Mamba/full-KV ratio **0.7**, PLE host offload **on**,
  MTP/NEXTN **3 steps / top-k 1 / 4 draft tokens** (effective algorithm `EAGLE`),
  **TP4/EP4/DP1**, FlashInfer attention, context **262,144**, HiCache **off**.
- Observed shared capacity **1,806,656**, Mamba slots **570**, direct per-DP request
  cap **48**. These are startup measurements, not proof of safe active concurrency.
- Frozen record: [`configs/production-frozen.json`](../configs/production-frozen.json).
  Full allowlisted argv/runtime/effective configuration:
  [freeze snapshot](../evidence/production-freeze-20261016T031327.846817Z.json).
  Private environment/credentials are intentionally omitted from the repository.

No additional inference tuning is recommended for the observation period. The
ratio-0.7 qualification remains bounded 32K/512 cold screening, not production-tail,
long-context or warm-retention qualification. Observe client errors/timeouts, OOM
or restarts, TTFT/decode responsiveness, queueing and available host/GPU memory;
do not automatically change the recipe in response to a single sample.

## Reboot persistence

The original restart policy was **`no`**, so the container would not have returned
automatically. With explicit operator approval it was changed to **`unless-stopped`**.
This was a metadata-only update: the container's ID, image, argv, process start time,
restart count and effective inference configuration remained unchanged. No restart,
reboot, cache flush or inference was performed for this update.

Read-only checks confirmed:

- `docker.service` is **enabled** at boot and currently **active**.
- The serving container alone has `unless-stopped`; all preserved original,
  rollback and test containers remain stopped with restart policy **`no`**.
- Model cache bind mount `/mnt/nvme1/huggingface` -> `/root/.cache/huggingface`
  is on a local ext4 filesystem; `/mnt/nvme1` has a UUID-based `/etc/fstab` entry.
  It is a regular boot mount (no `noauto`/`nofail`/automount flags), active and
  ordered before `local-fs.target`.
- Docker's data root `/var/lib/docker` is on local persistent storage (`overlay2`).

**Expected behavior:** following an ordinary reboot, Docker starts the same container,
reloads the model and pinned-host PLE table, and warms up before serving. Existing
container configuration, private environment and writable layer survive a reboot;
they are not a substitute for a private backup or a reproducible recreation plan.
GPU/CPU runtime caches and in-flight requests do not survive. Allow several minutes
for startup and keep clients retrying/gated on application readiness.

**Important exceptions:**

- If you deliberately `docker stop` this container, `unless-stopped` keeps it stopped
  across a reboot. Returning it to service then requires an explicitly approved
  `docker start`, after confirming no other container owns the GPUs/port.
- Restart policy restarts an exited process; it does not detect or recover a hung
  inference server merely because its API is unhealthy.
- Boot success still depends on the GPU driver/runtime, cache disk and Docker
  coming up correctly. No actual reboot was performed or qualified here. The PLE
  test did successfully stop/start and restore this same container beforehand.

Do not enable boot startup for the old containers: they share the GPUs and port.
Do not add duplicate systemd/cron launchers alongside Docker's restart policy.
Keep port 8011 restricted to trusted clients; changing authentication/firewall rules
is outside this freeze and has not been performed.

## Read-only checks after the next planned reboot

```bash
systemctl is-active docker.service
docker ps --format '{{.Names}} {{.Status}}'
docker inspect --format '{{.State.Running}} {{.State.OOMKilled}} {{.HostConfig.RestartPolicy.Name}}' \
  sglang-qwen38-flash-next-088-mamba070-20261016t020846
python3 -B tests/capture_baseline.py \
  --container sglang-qwen38-flash-next-088-mamba070-20261016t020846 \
  --label production-post-reboot
```

The inventory command sends only metadata requests and writes a new sanitized
snapshot; it does not run inference. Wait for readiness before using it, and compare
the new snapshot against the freeze's image/argv/configuration. Start time should
change on reboot; require the same container ID and effective recipe. Capture and
investigate any failed probe rather than treating missing readiness as success.
No post-reboot inference smoke is implicitly authorized by this checklist.

Evidence: [pre-update snapshot](../evidence/production-freeze-preflight-20261016T031327.566793Z.json),
[restart-policy change and persistence checks](../evidence/production-freeze-20261016T031327.846817Z.json).
[Frozen metadata, link and mount-order validation](../evidence/production-freeze-offline-and-mount-validation-20261016T031458.670937Z.json)
and [110-test offline setup validation](../evidence/setup-validation-20261016T031441.216828Z.json)
also passed.

## 2026-10-18 service stop (approved)

The operator explicitly approved stopping the frozen service to free the GPUs for a
DeepSeek-V4.1-Flash feasibility check. `docker stop -t 120` returned 0; the
container exited cleanly (`exit 0`, `OOMKilled false`). The container, its writable
layer and the pinned image were preserved; nothing was removed. Because the restart
policy is `unless-stopped`, the service will stay stopped across a reboot until it is
explicitly started. The four GPUs returned to idle (14 MiB used each). No inference
request was sent by the stop record.

Before the stop, this workspace was moved from `/home/tngai/H100-Node-Config` to
`/home/tngai/Qwen38-Flash-Next-Config`. The git remote still points at the existing
GitHub repository; the local directory rename does not change the remote.

Evidence: [`qwen-service-stop-20261018T102635.612026Z.json`](../evidence/qwen-service-stop-20261018T102635.612026Z.json).

## 2026-10-18 service restore (approved)

After the DeepSeek-V4.1-Flash experiment was closed, the operator directed a revert
to qwen38. The preserved container was started with `docker start`; no container
was recreated or removed. It became healthy again at approximately **13:57 UTC**.

Read-only verification:

- Container status `running`, `OOMKilled false`, restart policy `unless-stopped`.
- Served model `pratt-medium`; `max_total_num_tokens=1,806,656`,
  `max_running_requests=48`, TP4/EP4/DP1, static memory 0.88, effective `EAGLE`
  speculation.
- GPU memory at readiness: approximately 74.7–75.3 GiB per card.
- No inference request was sent by the restore check.

The frozen recipe and pinned image are unchanged. Evidence:
[`qwen-restore-verified-20261018T140109.321873Z.json`](../evidence/qwen-restore-verified-20261018T140109.321873Z.json),
[`qwen-restore-20261018T140048.221344Z.json`](../evidence/qwen-restore-20261018T140048.221344Z.json).
