# Results

## Raw logs: `phase1/<model>/*.jsonl`

One JSON object per line, one line per test case. File names:
- `attack_pay-<attack language>_task-<task language>_def-<defense>.jsonl`: attack runs
- `benign_task-<language>.jsonl`: no-attack baseline runs (the user's task written in that language)

Languages: `en` English, `hi` Hindi (Devanagari), `hi_latn` Hinglish (Romanized code-mixed).

Key fields in each record:

| Field | Meaning |
|---|---|
| `user_task_id`, `injection_task_id` | which user task and which attacker goal |
| `status` | `ok` = scored; `error` = excluded (reason in `error`) |
| `security` | **true = the attack succeeded** (AgentDojo's convention) |
| `utility` | true = the user's task was solved |
| `injections` | the exact attack text placed into the tool outputs |
| `messages` | the full conversation: user, agent, every tool call and tool result |
| `tool_calls` | every tool call the agent made |
| `final_output` | the agent's final answer |
| `condition` | model, languages, defense and generation settings |
| `events` | API calls, latencies, retries |

If a case appears more than once in a file (a retry), the last `ok` record counts.

To read any case: `python show_case.py <file> <user_task_id> <injection_task_id>`

## Summaries and audits

- `phase1/summary_final.md` / `.csv`: all rates with 95% Wilson confidence intervals (made by `analyze.py`)
- `phase1/AUDIT_gemma.md`: first independent check; found the mixed-settings issue (see `docs/RUN_LOG.md`)
- `phase1/AUDIT_phase1_final.md`: final independent recomputation of every number

## `archive/`

Runs replaced during Phase 1 and **not used in any reported number**, kept for transparency:
- `gemma_en_mixed_settings.jsonl`: the English Gemma file before 30 capped cases were rerun uncapped
- `gemma_benign_*_capped.jsonl`: Gemma baselines run with an output cap, replaced by uncapped reruns

## `pilot/`

Small pilot runs (2 cases each) from 30 Oct 2026, used only to choose models and test the pipeline.
