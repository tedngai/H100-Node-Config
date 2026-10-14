# H100 inference experiment rules

- This project records experiments; it does not deploy configurations automatically.
- Do not restart, stop, recreate, or modify the live container without explicit approval.
- Live inference tests require an approved idle window and explicit confirmation flags.
- Preserve `configs/baseline.json`. Record subsequent snapshots and every failed probe
  in timestamped, non-overwriting files under `evidence/`.
- Keep candidates relative to the original baseline. Change one experimental factor
  at a time; record automatic changes in SGLang's effective configuration too.
- Never save raw Docker inspect output, environment variables, credentials, model
  weights, caches, live logs, or shell history in this project.
- When a push is explicitly authorized, the GitHub PAT is supplied from the local
  home file `~/.env` as `GITHUB_PAT` (outside this repository). Never print, copy,
  stage, commit, or publish the file or token; pass it only ephemerally to the
  authenticated Git operation. Keep `.env` ignored.
- Never infer actual active concurrency from client concurrency or token-pool division.
  Missing metrics are unavailable, not zero. Do not sum duplicate TP metrics.
- No GPU benchmark, cache flush, driver change, deployment, commit, or publication
  is implied by setup or offline validation.
- Run `python3 -B -m unittest discover -s tests -v` after changing the harness.
