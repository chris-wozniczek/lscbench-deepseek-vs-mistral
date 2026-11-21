"""Export one compact JSON for the website page + PDF (all numbers come from extracted trial CSVs)."""
import csv, json, math, re, statistics as st, sys
from pathlib import Path
from importlib import util
ROOT = Path("/home/ubuntu/lscb-bench")
ARMS = ["deepseek-cc", "mistral-vibe"]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "consolidated/lscbench.json"

spec = util.spec_from_file_location("b", ROOT / "report150/build_report.py"); b = util.module_from_spec(spec); spec.loader.exec_module(b)


def n(v):
    try: return float(v)
    except (TypeError, ValueError): return None


def i(v):
    x = n(v); return None if x is None else int(x)


def wilson(k, m, z=1.959964):
    p = k / m; d = 1 + z * z / m; c = (p + z * z / (2 * m)) / d; h = z * math.sqrt(p * (1 - p) / m + z * z / (4 * m * m)) / d
    return [round(c - h, 4), round(c + h, 4)]


def mcnemar(b_, c_):
    k, m = min(b_, c_), b_ + c_
    return min(1.0, 2 * sum(math.comb(m, j) for j in range(k + 1)) / 2 ** m)


def load(p):
    return [r for r in csv.DictReader(open(p)) if r["official"] == "1"]


def short(s, k=220):
    s = re.sub(r"\s+", " ", s or "").strip(); return s if len(s) <= k else s[:k - 1] + "…"


def arm_summary(rows):
    out = {}
    for a in ARMS:
        rs = [r for r in rows if r["arm"] == a]; m = len(rs)
        ex = [n(r["agent_execution_s"]) for r in rs if n(r["agent_execution_s"]) is not None]
        rew = sum(i(r["reward"]) or 0 for r in rs)
        cost = sum(n(r["cost_usd"]) or 0 for r in rs)
        out[a] = {"n": m, "functional": sum(i(r["functional"]) or 0 for r in rs), "secure": sum(i(r["secure"]) or 0 for r in rs),
                  "reward": rew, "reward_ci95": wilson(rew, m),
                  "functional_not_secure": sum(1 for r in rs if i(r["functional"]) == 1 and i(r["reward"]) == 0),
                  "exceptions": sum(1 for r in rs if r["exception_type"]),
                  "median_agent_min": round(st.median(ex) / 60, 2), "p90_agent_min": round(b.p90(ex) / 60, 2),
                  "sum_agent_h": round(sum(ex) / 3600, 2),
                  "input_tokens": sum(i(r["input_tokens"]) or 0 for r in rs), "cached_input_tokens": sum(i(r["cached_input_tokens"]) or 0 for r in rs),
                  "output_tokens": sum(i(r["output_tokens"]) or 0 for r in rs),
                  "rows_without_tokens": sum(1 for r in rs if not r["input_tokens"]),
                  "cost_usd": round(cost, 4), "cost_per_secure_solve": round(cost / rew, 4) if rew else None,
                  "median_steps": st.median([n(r["steps"]) for r in rs if n(r["steps"]) is not None] or [0])}
    return out


def h2h(rows):
    by = {(r["arm"], r["task"]): i(r["reward"]) or 0 for r in rows}
    tasks = sorted({r["task"] for r in rows}); c = {"both": 0, "deepseek_only": 0, "mistral_only": 0, "neither": 0}
    for t in tasks:
        d, m = by.get((ARMS[0], t)), by.get((ARMS[1], t))
        c[{(1, 1): "both", (1, 0): "deepseek_only", (0, 1): "mistral_only", (0, 0): "neither"}[(d, m)]] += 1
    c["mcnemar_exact_p"] = round(mcnemar(c["deepseek_only"], c["mistral_only"]), 4); return c


main = load(ROOT / "run150/report/data/trials.csv"); pilot = load(ROOT / "report/data/trials.csv")
ft = {t["name"] if isinstance(t, dict) else t: t for t in json.load(open(ROOT / "notes/function_tasks.json"))} if False else None
pub = json.load(open(ROOT / "notes/published150.json"))
rep = json.load(open(ROOT / "consolidated/repeat_summary.json"))
rep_rows = list(csv.DictReader(open(ROOT / "consolidated/repeat_pilot_vs_run150.csv")))
sens = b.sens_rows()
pilot_tasks = set(rep["pilot_tasks"])

tasks = {}
for r in main:
    t = tasks.setdefault(r["task"], {"task": r["task"], "lang": r["lang"], "cwe": r["cwe"], "severity": r["severity"],
                                     "in_pilot": r["task"] in pilot_tasks, "published": pub["per_task"].get(r["task"], {})})
    k = "ds" if r["arm"] == ARMS[0] else "m"
    t[k] = {"f": i(r["functional"]) or 0, "s": i(r["secure"]) or 0, "r": i(r["reward"]) or 0, "scored": r["reward"] != "",
            "min": round(n(r["agent_execution_s"]) / 60, 2) if n(r["agent_execution_s"]) is not None else None,
            "tok": (i(r["input_tokens"]) or 0) + (i(r["output_tokens"]) or 0) if r["input_tokens"] else None,
            "out_tok": i(r["output_tokens"]), "cost": round(n(r["cost_usd"]), 4) if n(r["cost_usd"]) is not None else None,
            "steps": i(r["steps"]), "exc": r["exception_type"], "exc_msg": short(r["exception_msg"], 160),
            "n_func_fail": i(r["n_failed_func"]), "n_vuln_fail": i(r["n_failed_vuln"]),
            "vuln_tests": short(r["failed_vuln_tests"], 200), "vuln_msg": short(r["vulnerability_msg"], 260),
            "func_tests": short(r["failed_func_tests"], 200), "job": r["job"], "trial": r["trial"],
            "rerun": r["rerun_infra"] == "1", "vibe_exit": r.get("vibe_outcome", "")}
for rr in rep_rows:
    k = "ds" if rr["arm"] == ARMS[0] else "m"
    tasks[rr["task"]].setdefault("pilot", {})[k] = {"f": i(rr["pilot_functional"]) or 0, "s": i(rr["pilot_secure"]) or 0, "r": i(rr["pilot_reward"]) or 0}


def groups(key):
    g = {}
    for t in tasks.values():
        x = g.setdefault(t[key], {"key": t[key], "n": 0, "ds": 0, "m": 0, "ds_f": 0, "m_f": 0})
        x["n"] += 1; x["ds"] += t["ds"]["r"]; x["m"] += t["m"]["r"]; x["ds_f"] += t["ds"]["f"]; x["m_f"] += t["m"]["f"]
    return sorted(g.values(), key=lambda x: (-x["n"], x["key"]))


data = {
    "generated_from": "lscb-bench/run150/report/data/trials.csv + report/data/trials.csv (official rows only)",
    "arms": {ARMS[0]: {"label": "DeepSeek Flash", "agent": "Claude Code 2.1.143", "model": "deepseek-flash", "effort": "max",
                       "endpoint": "api.deepseek.com/anthropic (official)", "cost_basis": "DeepSeek list price, billed"},
             ARMS[1]: {"label": "Mistral Large 4", "agent": "Mistral Vibe 3.1.3", "model": "mistral-large-4-0", "effort": "thinking high",
                       "endpoint": "api.mistral.ai (official)", "cost_basis": "API-equivalent list price (run on subscription)"}},
    "run150": {"summary": arm_summary(main), "h2h": h2h(main), "by_lang": groups("lang"), "by_cwe": groups("cwe")},
    "pilot30": {"summary": arm_summary(pilot), "h2h": h2h(pilot)},
    "repeat": rep["repeat_summary"],
    "published": pub["totals"],
    "sensitivity": sens,
    "agent_minutes": {a: sorted(round(n(r["agent_execution_s"]) / 60, 2) for r in main if r["arm"] == a and n(r["agent_execution_s"]) is not None) for a in ARMS},
    "tasks": sorted(tasks.values(), key=lambda t: t["task"]),
}
OUT.write_text(json.dumps(data, separators=(",", ":")))
print(OUT, OUT.stat().st_size, "bytes")
for k in ("run150", "pilot30"):
    for a, s in data[k]["summary"].items():
        print(k, a, {x: s[x] for x in ("n", "functional", "reward", "reward_ci95", "median_agent_min", "p90_agent_min", "cost_usd", "cost_per_secure_solve", "rows_without_tokens")})
    print(k, data[k]["h2h"])
