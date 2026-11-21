"""Build per-trial table + summary for the 30-task pilot from Harbor job dirs."""
import csv, glob, json, os, re
from datetime import datetime

ROOT = "/home/ubuntu/lscb-bench"
MANIFEST = {t["task"]: t for t in json.load(open(f"{ROOT}/notes/pilot30.json"))["tasks"]}
ARMS = {"deepseek-cc": "DeepSeek Flash / Claude Code", "mistral-vibe": "Mistral Large 4 / Vibe"}
# DeepSeek-V4.1-Flash official list prices, USD per 1M tokens (api-docs.deepseek.com, fetched 2026-11-20)
DS = {"peak": (0.30, 0.006, 1.20), "offpeak": (0.15, 0.003, 0.60)}  # (miss, hit, output)
SETUP_PHASES = ("environment_setup", "agent_setup")


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def dur(d, k):
    p = d.get(k) or {}
    a, b = ts(p.get("started_at")), ts(p.get("finished_at"))
    return round((b - a).total_seconds(), 3) if a and b else None


def ds_peak(t):
    return t.weekday() < 5 and (1 <= t.hour < 4 or 6 <= t.hour < 10)


def verifier_details(rdir):
    f = f"{rdir}/verifier/test-stdout.txt"
    out = dict(vsb_build=None, vsb_summary=None, n_failed_func=0, n_failed_vuln=0,
               failed_func_tests="", failed_vuln_tests="", vulnerability_msg="", verifier_error="")
    if not os.path.exists(f):
        return out
    txt = open(f, errors="replace").read()
    m = re.findall(r"^VSB_BUILD=(\S+)", txt, re.M)
    out["vsb_build"] = m[-1] if m else None
    m = re.findall(r"^VSB functional=.*$", txt, re.M)
    out["vsb_summary"] = m[-1].strip() if m else None
    ff = sorted(set(re.findall(r"^(?:FAILED|ERROR) (?:\S*/)?test_func\.py::(\S+)", txt, re.M)))
    fv = sorted(set(re.findall(r"^(?:FAILED|ERROR) (?:\S*/)?test_vuln\.py::(\S+)", txt, re.M)))
    out.update(n_failed_func=len(ff), n_failed_vuln=len(fv), failed_func_tests=";".join(ff), failed_vuln_tests=";".join(fv))
    if out["vsb_summary"]:
        mf = re.search(r"functional: (\d+) failed", out["vsb_summary"]); ms = re.search(r"secure: (\d+) failed", out["vsb_summary"])
        out["n_failed_func"] = int(mf.group(1)) if mf else out["n_failed_func"]
        out["n_failed_vuln"] = int(ms.group(1)) if ms else out["n_failed_vuln"]
    v = re.findall(r"VULNERABILITY:\s*(.+)", txt)
    out["vulnerability_msg"] = v[0].strip()[:300] if v else ""
    e = [l.strip() for l in txt.splitlines() if l.startswith("ERROR:") or "[VSB] cannot" in l]
    out["verifier_error"] = " | ".join(e)[:300]
    return out


def trial_row(rdir, job, arm, batch, rerun):
    d = json.load(open(f"{rdir}/result.json"))
    task = d["task_id"]["name"]
    m = MANIFEST[task]
    rw = (d.get("verifier_result") or {}).get("rewards") or {}
    ex = d.get("exception_info") or {}
    ar = d.get("agent_result") or {}
    row = dict(arm=arm, arm_label=ARMS[arm], batch=batch, job=job, trial=os.path.basename(rdir), task=task,
               lang=m["lang"], cwe=m["cwe"], severity=m["sev"], rerun_infra=int(rerun),
               functional=rw.get("functional"), secure=rw.get("secure"), reward=rw.get("reward"),
               reward_valid=d.get("reward_valid"),
               exception_type=ex.get("exception_type"),
               exception_msg=(str(ex.get("exception_message") or "").strip().splitlines() or [""])[0][:300],
               started_at=d.get("started_at"), finished_at=d.get("finished_at"))
    for k in ("environment_setup", "agent_setup", "agent_execution", "verifier"):
        row[f"{k}_s"] = dur(d, k)
    a, b = ts(d.get("started_at")), ts(d.get("finished_at"))
    row["trial_total_s"] = round((b - a).total_seconds(), 3) if a and b else None
    # failure phase: where the exception happened
    phase = None
    if ex:
        et = ex.get("exception_type") or ""
        if not (d.get("agent_execution") or {}).get("started_at"):
            phase = "agent_setup" if (d.get("agent_setup") or {}).get("started_at") else "environment_setup"
        elif "Verifier" in et or "Reward" in et:
            phase = "verifier"
        else:
            phase = "agent_execution"
    row["exception_phase"] = phase
    row.update(verifier_details(rdir))
    row["infra_failure"] = int(bool(ex) and phase in SETUP_PHASES)
    row["install_fallback"] = int(os.path.exists(f"{rdir}/agent/install_fallback.txt"))
    tin = tcache = tout = steps = cost = None
    cost_basis = None
    if arm == "deepseek-cc":
        tin, tcache, tout = ar.get("n_input_tokens"), ar.get("n_cache_tokens"), ar.get("n_output_tokens")
        tj = f"{rdir}/agent/trajectory.json"
        if os.path.exists(tj):
            steps = len(json.load(open(tj)).get("steps") or [])
        start = ts((d.get("agent_execution") or {}).get("started_at"))
        if tin is not None and start:
            miss, hit, outp = DS["peak" if ds_peak(start) else "offpeak"]
            cost = ((tin - (tcache or 0)) * miss + (tcache or 0) * hit + (tout or 0) * outp) / 1e6
            cost_basis = "deepseek_list_" + ("peak" if ds_peak(start) else "offpeak")
        row["harbor_cost_usd"] = ar.get("cost_usd")
    else:
        ex_path = f"{rdir}/agent/vibe-export/export.json"
        if os.path.exists(ex_path):
            e = json.load(open(ex_path))
            u = e.get("usage") or {}
            tin, tcache, tout = u.get("input_tokens"), u.get("cached_input_tokens"), u.get("output_tokens")
            steps, cost = e.get("steps"), e.get("cost_usd")
            cost_basis = "vibe_export_api_equivalent"
            row["vibe_outcome"], row["vibe_stop_reason"], row["vibe_error"] = e.get("outcome"), e.get("stop_reason"), e.get("error")
    row.update(input_tokens=tin, cached_input_tokens=tcache, output_tokens=tout,
               uncached_input_tokens=(tin - tcache) if tin is not None and tcache is not None else None,
               steps=steps, cost_usd=round(cost, 6) if cost is not None else None, cost_basis=cost_basis)
    return row


rows = []
for jdir in sorted(glob.glob(f"{ROOT}/jobs/pilot30-*")):
    job = os.path.basename(jdir)
    mm = re.fullmatch(r"pilot30-(b[123]|rerun\d*)-(deepseek-cc|mistral-vibe)", job)
    if not mm:
        continue  # aborted / legacy dirs are excluded
    for r in sorted(glob.glob(f"{jdir}/*/result.json")):
        rows.append(trial_row(os.path.dirname(r), job, mm.group(2), mm.group(1), mm.group(1).startswith("rerun")))

VOID = {(v["job"], v["trial"]): v["reason"] for v in json.load(open(f"{ROOT}/notes/void_trials.json"))["void"]}
for r in rows:
    r["void_reason"] = VOID.get((r["job"], r["trial"]), "")
    r["void"] = int(bool(r["void_reason"]))

# official row per (arm, task): main batch trial, replaced by its rerun only if main was an infra failure
official = {}
for r in rows:
    k = (r["arm"], r["task"])
    if not r["rerun_infra"]:
        official.setdefault(k, r)
for k, r in list(official.items()):
    if r["void"] and not any(x["rerun_infra"] and (x["arm"], x["task"]) == k for x in rows):
        del official[k]  # void with no re-run yet: excluded, task counted as missing
for r in rows:
    k = (r["arm"], r["task"])
    if r["rerun_infra"] and k in official and (official[k]["infra_failure"] or official[k]["void"]):
        official[k]["superseded_by_rerun"] = 1
        official[k] = r
for r in rows:
    r["official"] = int(official.get((r["arm"], r["task"])) is r)

os.makedirs(f"{ROOT}/report/data", exist_ok=True)
keys = sorted({k for r in rows for k in r}, key=lambda k: list(rows[0]).index(k) if k in rows[0] else 999)
with open(f"{ROOT}/report/data/trials.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)

summary = {}
for arm in ARMS:
    o = [r for r in official.values() if r["arm"] == arm]
    n = len(o)
    s = lambda k: sum((r.get(k) or 0) for r in o)
    vals = lambda k: sorted(r[k] for r in o if r.get(k) is not None)
    med = lambda v: (v[len(v)//2] if len(v) % 2 else (v[len(v)//2-1]+v[len(v)//2])/2) if v else None
    summary[arm] = dict(label=ARMS[arm], n_tasks=n, functional=s("functional"), secure=s("secure"), reward=s("reward"),
        exceptions=sum(1 for r in o if r["exception_type"]), infra_failures=s("infra_failure"),
        input_tokens=s("input_tokens"), cached_input_tokens=s("cached_input_tokens"), output_tokens=s("output_tokens"),
        cost_usd=round(s("cost_usd"), 4), median_agent_execution_s=med(vals("agent_execution_s")),
        median_trial_total_s=med(vals("trial_total_s")), sum_agent_execution_s=round(s("agent_execution_s"), 1),
        median_steps=med(vals("steps")))
json.dump(summary, open(f"{ROOT}/report/data/summary.json", "w"), indent=2)
print(json.dumps(summary, indent=2)); print("rows", len(rows), "official", len(official))
