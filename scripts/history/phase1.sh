#!/usr/bin/env bash
cd "$(dirname "$0")"; source .venv/bin/activate; source ../secrets/env
M=gemini-3.5-flash-lite; OUT=results/phase1/$M; mkdir -p $OUT logs
run(){ for i in 1 2 3 4 5 6; do python run_experiments.py --provider gemini --model $M --suite banking --reasoning-effort minimal --sleep 4 --skip-provider-errors "$@" && break; sleep 120; done; }
for L in en hi hi_latn; do run --payload-lang $L --task-lang en --defense none --limit 72 --out $OUT/attack_pay-${L}_task-en_def-none.jsonl; done
for L in en hi hi_latn; do run --attack none --task-lang $L --out $OUT/benign_task-$L.jsonl; done
# second pass picks up any errored pairs
for L in en hi hi_latn; do run --payload-lang $L --task-lang en --defense none --limit 72 --out $OUT/attack_pay-${L}_task-en_def-none.jsonl; done
for L in en hi hi_latn; do run --attack none --task-lang $L --out $OUT/benign_task-$L.jsonl; done
echo PHASE1_DONE
