#!/usr/bin/env bash
cd "$(dirname "$0")"; source .venv/bin/activate; source ../secrets/env
M=gemma-4-26b-a4b-it; OUT=results/phase1/$M; mkdir -p $OUT
run(){ for i in 1 2 3 4 5 6; do python run_experiments.py --provider gemini --model $M --suite banking --sleep 2 "$@" && break; sleep 120; done; }
for L in en hi hi_latn; do run --payload-lang $L --task-lang en --defense none --limit 72 --out $OUT/attack_pay-${L}_task-en_def-none.jsonl > logs/gemma_attack_$L.log 2>&1 & done; wait
for L in en hi hi_latn; do run --attack none --task-lang $L --out $OUT/benign_task-$L.jsonl > logs/gemma_benign_$L.log 2>&1 & done; wait
# retry pass for any errored pairs
for L in en hi hi_latn; do run --payload-lang $L --task-lang en --defense none --limit 72 --out $OUT/attack_pay-${L}_task-en_def-none.jsonl >> logs/gemma_attack_$L.log 2>&1 & done; wait
for L in en hi hi_latn; do run --attack none --task-lang $L --out $OUT/benign_task-$L.jsonl >> logs/gemma_benign_$L.log 2>&1 & done; wait
echo GEMMA_DONE > logs/gemma_done.flag
