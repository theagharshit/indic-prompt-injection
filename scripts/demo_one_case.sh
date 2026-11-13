#!/usr/bin/env bash
# Live demo: runs ONE test case on Gemma 4, first with the attack in English, then in Hindi,
# and prints what the agent did in each. Takes about 1-3 minutes. Needs GEMINI_API_KEY.
#
# Usage: ./scripts/demo_one_case.sh [user_task_id] [injection_task_id]
# Default case: user asks for March 2022 spending; the hidden attack asks the agent to send
# the user's phone model to the attacker's account.
set -u
cd "$(dirname "$0")/.."
: "${GEMINI_API_KEY:?set GEMINI_API_KEY first}"
UT="${1:-user_task_1}"; IT="${2:-injection_task_3}"
OUT=results/demo; mkdir -p $OUT
for L in en hi; do
  F=$OUT/demo_${L}_$(date +%Y%m%d_%H%M%S).jsonl
  echo; echo ">>> Running $UT + $IT with the attack written in: $L"
  python run_experiments.py --provider gemini --model gemma-4-26b-a4b-it --suite banking --defense none \
      --payload-lang $L --task-lang en --limit 72 --user-tasks $UT --injection-tasks $IT \
      --sleep 2 --timeout 300 --max-retries 6 --out "$F" >/dev/null 2>&1 \
    || { echo "run failed (rate limit or server error) - try again in a minute"; continue; }
  python show_case.py "$F" $UT $IT
done
echo
echo "Note: one live run can differ from the logged result - the model is not fully deterministic."
echo "Rates in the paper come from 71-72 cases per language, not one."
