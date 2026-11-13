#!/usr/bin/env bash
# Reproduces Phase 1 with the exact settings used for the reported numbers.
# Needs: GEMINI_API_KEY in the environment (free key from https://aistudio.google.com).
# Resumable: re-running skips cases already in the output files.
#
# Free-tier limits seen on 13 Nov 2026: Gemini 3.5 Flash-Lite = 500 requests/day,
# Gemma 4 26B = 16,000 input tokens/minute. A full Phase 1 needs ~900 Flash-Lite requests
# (so two days of quota) and ~3-5 hours for Gemma.
set -u
cd "$(dirname "$0")/.."
: "${GEMINI_API_KEY:?set GEMINI_API_KEY first}"

COMMON="--provider gemini --suite banking --defense none --skip-provider-errors"

run() {  # retry a condition a few times (rate limits / server errors), then move on
  for i in 1 2 3 4 5 6; do python run_experiments.py $COMMON "$@" && return; sleep 120; done
}

# Model 1: Gemini 3.5 Flash-Lite, minimal reasoning
M=gemini-3.5-flash-lite; OUT=results/phase1/$M
for L in en hi hi_latn; do
  run --model $M --reasoning-effort minimal --sleep 4 --payload-lang $L --task-lang en --limit 72 \
      --out $OUT/attack_pay-${L}_task-en_def-none.jsonl
done
for L in en hi hi_latn; do
  run --model $M --reasoning-effort minimal --sleep 4 --attack none --task-lang $L --out $OUT/benign_task-$L.jsonl
done

# Model 2: Gemma 4 26B (open-weight), default settings, no output cap
M=gemma-4-26b-a4b-it; OUT=results/phase1/$M
for L in en hi hi_latn; do
  run --model $M --sleep 2 --timeout 300 --max-retries 6 --payload-lang $L --task-lang en --limit 72 \
      --out $OUT/attack_pay-${L}_task-en_def-none.jsonl
done
for L in en hi hi_latn; do
  run --model $M --sleep 2 --timeout 300 --max-retries 6 --attack none --task-lang $L --out $OUT/benign_task-$L.jsonl
done

python analyze.py results/phase1 --out-prefix results/phase1/summary_final
python extra_analysis.py results/phase1
