# H100 inference experiment rules

- Production hold (2026-10-16): the operator froze `memory-088-mamba-070` for real
  traffic observation. See `configs/production-frozen.json` and
  `docs/PRODUCTION_RECIPE.md`. Do not resume experiments or change the recipe
  without fresh approval. Only the serving container has `unless-stopped`;
  rollback/test containers remain stopped with restart policy `no`.

- This project records experiments; it does not deploy configurations automatically.
- Do not restart, stop, recreate, or modify the live container without explicit approval.
- Live inference tests require an approved idle window and explicit confirmation flags.
- Preserve `configs/baseline.json`. Record subsequent snapshots and every failed probe
  in timestamped, non-overwriting files under `evidence/`.
- Keep candidates relative to the original baseline. Change one experimental factor
  at a time; record automatic changes in SGLang's effective configuration too.
- Never save raw Docker inspect output, environment variables, credentials, model
  weights, caches, live logs, or shell history in this project.
- After validation, commit and push all intended repository updates to the current
  branch by default. Review the staged scope; exclude unrelated user changes and
  anything prohibited above. This standing instruction authorizes the push unless
  the user directs otherwise or a safety blocker applies.
- For GitHub pushes, the PAT is supplied from the local
  home file `~/.env` as `GITHUB_PAT` (outside this repository). Never print, copy,
  stage, commit, or publish the file or token; pass it only ephemerally to the
  authenticated Git operation. Keep `.env` ignored.
- Never infer actual active concurrency from client concurrency or token-pool division.
  Missing metrics are unavailable, not zero. Do not sum duplicate TP metrics.
- No GPU benchmark, cache flush, driver change, or deployment is implied by setup or
  offline validation. Commit/push intended repository updates after validation as
  described above.
- Run `python3 -B -m unittest discover -s tests -v` after changing the harness.

## Working records

- This repository is the authoritative configuration and experiment record. For
  GLM, start with `configs/glm53-production.json` and `docs/GLM53_PRODUCTION.md`;
  the older Qwen production hold above is historical, not the active GLM profile.
- Before continuing planned work, read `.local/UPDATE_PLAN.md` and
  `.local/CHANGELOG.md` when present. These are private, gitignored working records,
  not public documentation. Never force-add them or quote their contents into
  public commits/issues. The prohibition on secrets and raw operational dumps
  applies to ignored files too.
- Log every change and validation result in `.local/CHANGELOG.md`, including
  changes to external deployment scripts (record paths and summaries, not raw logs).
- Commit validated, public-safe changes in small logical checkpoints; push as
  authorized above. Private-plan-only edits stay local and need no public commit.
- Planning or documentation approval does not authorize builds, deployment,
  live inference tests, restarts, or changes to the recorded production profile.
