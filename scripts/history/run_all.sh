#!/usr/bin/env bash
# Runs the full study for ONE model, condition by condition, resumably.
# Usage: ./run_all.sh <model> <reasoning_effort|none> <sleep_s>
# Results: results/main/<model>/<condition>.jsonl ; log: logs/<model>.log
# Re-running is safe: finished pairs are skipped.
set -u
MODEL="$1"; EFFORT="$2"; SLEEP="$3"
cd "$(dirname "$0")"
PY="${PY:-python3}"
export GEMINI_API_KEY="$($PY ../load_key.py)"
LIMIT=72; SUITE=banking
OUTDIR="results/main/$MODEL"; mkdir -p "$OUTDIR" logs
EARGS=(); [ "$EFFORT" != "none" ] && EARGS=(--reasoning-effort "$EFFORT")

# Priority order, so partial results are already usable.
CONDS=()
for L in en hi hi_latn bn te; do CONDS+=("attack $L en none"); done                 # P1 core: payload language
for L in en hi hi_latn bn te; do CONDS+=("benign - $L none"); done                  # P2 benign utility per task language
for D in spotlighting_with_delimiting repeat_user_prompt; do                        # P3 defenses
  for L in en hi hi_latn bn te; do CONDS+=("attack $L en $D"); done; done
for L in hi hi_latn bn te; do CONDS+=("attack $L $L none"); CONDS+=("attack en $L none"); done   # P4 mismatch

for C in "${CONDS[@]}"; do
  read -r KIND PL TL DEF <<<"$C"
  if [ "$KIND" = benign ]; then
    ARGS=(--attack none --task-lang "$TL"); NAME="benign_task-$TL"
  else
    ARGS=(--payload-lang "$PL" --task-lang "$TL" --defense "$DEF" --limit $LIMIT); NAME="attack_pay-${PL}_task-${TL}_def-${DEF}"
  fi
  for attempt in $(seq 1 60); do
    echo "$(date -u +%FT%TZ) START $NAME attempt $attempt" >>"logs/$MODEL.log"
    $PY run_experiments.py --provider gemini --model "$MODEL" --suite $SUITE "${ARGS[@]}" "${EARGS[@]}" \
        --sleep "$SLEEP" --out "$OUTDIR/$NAME.jsonl" >>"logs/$MODEL.log" 2>&1
    rc=$?
    echo "$(date -u +%FT%TZ) END $NAME rc=$rc" >>"logs/$MODEL.log"
    if [ $rc -eq 0 ]; then
      # rc 0 can still leave errored pairs; re-run once more picks them up, then move on
      $PY run_experiments.py --provider gemini --model "$MODEL" --suite $SUITE "${ARGS[@]}" "${EARGS[@]}" \
        --sleep "$SLEEP" --out "$OUTDIR/$NAME.jsonl" >>"logs/$MODEL.log" 2>&1
      break
    elif [ $rc -eq 3 ]; then sleep 3600     # daily quota: wait an hour, resume
    else sleep 600; fi                      # provider trouble: wait 10 min, resume
  done
done
echo "$(date -u +%FT%TZ) ALL DONE" >>"logs/$MODEL.log"
