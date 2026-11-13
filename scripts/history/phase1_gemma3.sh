#!/usr/bin/env bash
cd "$(dirname "$0")"; source .venv/bin/activate; source ../secrets/env
M=gemma-4-26b-a4b-it; OUT=results/phase1/$M
run(){ for i in 1 2 3; do python run_experiments.py --provider gemini --model $M --suite banking --sleep 2 --skip-provider-errors --max-retries 4 --timeout 120 --max-tokens 2048 "$@" && break; sleep 60; done; }
run --payload-lang en --task-lang en --defense none --limit 72 --out $OUT/attack_pay-en_task-en_def-none.jsonl >> logs/gemma_attack_en.log 2>&1 &
for L in en hi hi_latn; do run --attack none --task-lang $L --out $OUT/benign_task-$L.jsonl > logs/gemma_benign_$L.log 2>&1 & done; wait
# one retry pass over any excluded pairs
run --payload-lang en --task-lang en --defense none --limit 72 --out $OUT/attack_pay-en_task-en_def-none.jsonl >> logs/gemma_attack_en.log 2>&1
for L in hi hi_latn; do run --payload-lang $L --task-lang en --defense none --limit 72 --out $OUT/attack_pay-${L}_task-en_def-none.jsonl >> logs/gemma_attack_$L.log 2>&1; done
for L in en hi hi_latn; do run --attack none --task-lang $L --out $OUT/benign_task-$L.jsonl >> logs/gemma_benign_$L.log 2>&1; done
echo GEMMA_DONE > logs/gemma_done.flag
