"""Consolidated dataset: 150-task run (headline) + 30-task pilot as an independent repeat on 30 of the same tasks."""
import csv, json
from pathlib import Path
ROOT = Path("/home/ubuntu/lscb-bench")
OUT = ROOT / "consolidated"; OUT.mkdir(exist_ok=True)
ARMS = ["deepseek-cc", "mistral-vibe"]
F = ("functional", "secure", "reward")


def official(p):
    rows = [r for r in csv.DictReader(open(p)) if r["official"] == "1"]
    return {(r["arm"], r["task"]): r for r in rows}


def val(r, c):
    v = r.get(c, "")
    return None if v in ("", None) else int(float(v))


main = official(ROOT / "run150/report/data/trials.csv")
pilot = official(ROOT / "report/data/trials.csv")
pilot_tasks = sorted({t for _, t in pilot})
rep_rows, summ = [], {}
for arm in ARMS:
    s = {"n": 0, "same_reward": 0, "pass_both": 0, "pass_pilot_only": 0, "pass_main_only": 0, "fail_both": 0,
         "pilot_reward": 0, "main_reward_on_pilot_tasks": 0, "same_functional": 0, "unscored_either": 0}
    for t in pilot_tasks:
        a, b = pilot.get((arm, t)), main.get((arm, t))
        if not a or not b:
            continue
        ra, rb = val(a, "reward"), val(b, "reward")
        rep_rows.append({"arm": arm, "task": t, "lang": b["lang"], "cwe": b["cwe"],
                         **{f"pilot_{c}": val(a, c) for c in F}, **{f"main_{c}": val(b, c) for c in F},
                         "pilot_job": a["job"], "main_job": b["job"]})
        s["n"] += 1
        if ra is None or rb is None:
            s["unscored_either"] += 1
            continue
        s["pilot_reward"] += ra; s["main_reward_on_pilot_tasks"] += rb
        s["same_reward"] += ra == rb
        s["same_functional"] += val(a, "functional") == val(b, "functional")
        key = {(1, 1): "pass_both", (1, 0): "pass_pilot_only", (0, 1): "pass_main_only", (0, 0): "fail_both"}[(ra, rb)]
        s[key] += 1
    summ[arm] = s

with open(OUT / "repeat_pilot_vs_run150.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rep_rows[0])); w.writeheader(); w.writerows(rep_rows)
json.dump({"note": "Pilot (30 tasks, seed 20261120) is a separate earlier run on a subset of the 150 function tasks, "
                   "different host (Devin VM, 3 concurrent) and same agent/model settings. It is NOT pooled with the "
                   "150-task run; it is used only as a repeat to measure run-to-run outcome stability.",
           "repeat_summary": summ, "pilot_tasks": pilot_tasks},
          open(OUT / "repeat_summary.json", "w"), indent=1)
print(json.dumps(summ, indent=1))
