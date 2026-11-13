"""Print one test case from the raw logs in readable form.

Shows: the user's request, the tool output containing the hidden attack, every tool call the
agent made, its final answer, and the verdict (task solved? attack succeeded?).

Usage:
  python show_case.py <results .jsonl file> <user_task_id> <injection_task_id>
Example:
  python show_case.py results/phase1/gemma-4-26b-a4b-it/attack_pay-hi_task-en_def-none.jsonl user_task_1 injection_task_3
"""
import json
import sys
import textwrap

ATTACKER_IBAN = "US133000000121212121212"


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(c.get("content", "") if isinstance(c, dict) else str(c) for c in content)
    return str(content or "")


def main(path, ut, it):
    rec = None
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        if r["user_task_id"] == ut and r.get("injection_task_id") == it and r["status"] == "ok":
            rec = r  # last ok record wins
    if rec is None:
        sys.exit(f"no ok record for {ut} / {it} in {path}")
    c = rec["condition"]
    bar = "=" * 78
    print(bar)
    print(f"MODEL {c.get('model')} | attack language: {c.get('payload_lang')} | task language: {c.get('task_lang')}"
          f" | defense: {c.get('defense')}")
    print(f"CASE  {ut} + {it}")
    print(bar)
    print("\n[1] USER ASKS THE AGENT:\n" + textwrap.indent(rec["prompt"], "    "))
    step = 2
    for m in rec["messages"]:
        role = m.get("role")
        if role == "assistant":
            for tc in m.get("tool_calls") or []:
                args = json.dumps(tc.get("args", {}), ensure_ascii=False)
                flag = "   <-- SENDS TO ATTACKER" if ATTACKER_IBAN in args else ""
                print(f"\n[{step}] AGENT CALLS TOOL: {tc.get('function')}({args}){flag}")
                step += 1
        elif role == "tool":
            t = text_of(m.get("content"))
            if "<INFORMATION>" in t:
                i = t.find("<INFORMATION>")
                j = t.find("</INFORMATION>") + len("</INFORMATION>")
                print(f"\n[{step}] TOOL RETURNS DATA WITH A HIDDEN ATTACK INSIDE:")
                print(textwrap.indent(t[i:j].strip(), "    | "))
            else:
                print(f"\n[{step}] TOOL RETURNS: {t[:300]}{'...' if len(t) > 300 else ''}")
            step += 1
    print(f"\n[{step}] AGENT'S FINAL ANSWER TO THE USER:\n" + textwrap.indent((rec.get("final_output") or "")[:1200], "    "))
    print("\n" + bar)
    print(f"VERDICT  user task solved: {rec['utility']}   |   attack succeeded: {rec['security']}")
    print(bar)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
