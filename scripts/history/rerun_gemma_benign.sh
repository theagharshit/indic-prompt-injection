#!/usr/bin/env bash
cd "$(dirname "$0")"; source .venv/bin/activate; source ../secrets/env
for L in en hi hi_latn; do
  for i in 1 2 3; do python run_experiments.py --provider gemini --model gemma-4-26b-a4b-it --suite banking --sleep 2 --skip-provider-errors --max-retries 6 --timeout 300 --attack none --task-lang $L --out results/phase1/gemma-4-26b-a4b-it/benign_task-$L.jsonl && break; sleep 60; done
done
echo DONE > logs/gemma_benign_rerun.flag
