#!/usr/bin/env bash
# Candidate only: engine device selection is already patched in the immutable image.
# No modification of installed Python files at startup, including after a restart.
set -euo pipefail
: "${MODEL_PATH:?}" "${DRAFTER_ARG:?}" "${API_PORT:?}" "${MASTER_PORT:?}"
: "${SERVED_NAME:?}" "${CONTEXT:?}" "${PARALLEL:?}" "${MAX_TOKENS:?}"
[[ "${TP:-4}" == 4 ]] || { echo 'Candidate requires TP=4' >&2; exit 1; }
python -B - <<'PY'
import importlib.util
from pathlib import Path
root = Path(next(iter(importlib.util.find_spec('tensorfold').submodule_search_locations)))
text = (root / 'families/glm5_next/cuda/engine.py').read_text()
assert 'torch.cuda.set_device(int(os.environ.get("TF_GLM_DEVICE", "0")))' in text
assert 'torch.cuda.set_device(0)' not in text
PY
common=(tensorfold serve "$MODEL_PATH" --tp 4 --master 127.0.0.1
        --master-port "$MASTER_PORT" --context "$CONTEXT" --parallel "$PARALLEL"
        --max-tokens "$MAX_TOKENS" --drafter "$DRAFTER_ARG")
if [[ "${THINKING:-1}" == 1 ]]; then common+=(--thinking); else common+=(--no-thinking); fi
if [[ "${VISION:-1}" == 1 ]]; then common+=(--vision); fi
if [[ "$DRAFTER_ARG" == none ]]; then common+=(--no-drafts); fi
mkdir -p /logs
pids=()
cleanup() {
  trap - TERM INT
  if ((${#pids[@]})); then
    kill "${pids[@]}" 2>/dev/null || true
    wait "${pids[@]}" 2>/dev/null || true
  fi
}
trap 'cleanup; exit 143' TERM INT
for rank in 3 2 1; do
  TF_GLM_DEVICE=$rank "${common[@]}" --rank "$rank" >"/logs/rank${rank}.log" 2>&1 &
  pids+=($!)
done
TF_GLM_DEVICE=0 "${common[@]}" --rank 0 --name "$SERVED_NAME" --host 0.0.0.0 \
  --port "$API_PORT" >/logs/rank0.log 2>&1 &
pids+=($!)
set +e
wait -n "${pids[@]}"
code=$?
cleanup
# An unexpected rank termination, even status 0, is a supervisor failure.
((code != 0)) || code=1
exit "$code"
