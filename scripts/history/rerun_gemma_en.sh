#!/usr/bin/env bash
cd "$(dirname "$0")"; source .venv/bin/activate; source ../secrets/env
for i in 1 2 3; do python run_experiments.py --provider gemini --model gemma-4-26b-a4b-it --suite banking --sleep 2 --skip-provider-errors --max-retries 6 --timeout 300 --no-retry-errors --payload-lang en --task-lang en --defense none --limit 72 --out results/phase1/gemma-4-26b-a4b-it/attack_pay-en_task-en_def-none.jsonl && break; sleep 60; done
echo DONE > logs/gemma_en_rerun.flag
