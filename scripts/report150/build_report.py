"""Build the 150-task function-level report (run150/report) reusing the pilot report helpers/charts."""
import importlib.util, json, re, statistics, glob, os
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("B", ROOT / "report/build_report.py")
B = importlib.util.module_from_spec(spec); spec.loader.exec_module(B)

RUN = ROOT / "run150"
B.REPORT = REPORT = RUN / "report"
B.DATA = DATA = REPORT / "data"
B.CHARTS = CHARTS = REPORT / "charts"
NOTES = ROOT / "notes"
ARMS, LBL, SHORT = B.ARM_ORDER, B.ARM_LABELS, B.ARM_SHORT
PUB_MODELS = ["GLM-5.3", "DeepSeek-V4-Pro", "Qwen3.8-Max", "Claude-Fable-5", "GPT-5.6-Sol", "Kimi-K3"]


def num(v):
    return B.as_number(v)


def pct(k, n):
    lo, hi = B.wilson_interval(k, n)
    return f"{k}/{n} ({100*k/n:.1f}%, 95% CI {100*lo:.0f}–{100*hi:.0f}%)" if n else "—"


def med(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def p90(vals):
    return B.nearest_rank([v for v in vals if v is not None], 90)


def short(s, n=110):
    s = B.clean_text(s or "").replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def runner_events(text):
    ev = []
    for line in text.splitlines():
        m = re.match(r"^(\S+)\s+((?:batch\d|b1rest|run150-sens\S*)\s+(?:start|end|aborted.*)|MANUAL:.*|WATCHER:.*|CHAIN:.*)$", line)
        if m:
            ev.append((m.group(1)[:19].replace("T", " "), short(m.group(2), 160)))
    return ev


def sens_rows():
    out = []
    for f in sorted(glob.glob(str(RUN / "jobs/run150-sens*-mistral-vibe/*/result.json"))):
        r = json.load(open(f)); v = (r.get("verifier_result") or {}).get("rewards") or {}
        e = r.get("exception_info") or {}
        out.append({"job": f.split("/")[-3], "task": r["task_name"].split("/")[-1], "functional": v.get("functional"),
                    "secure": v.get("secure"), "reward": v.get("reward"), "exception": e.get("exception_type", ""),
                    "msg": short(e.get("exception_message", ""), 80)})
    return out


def main():
    rows = B.read_csv(DATA / "trials.csv")
    summary = json.loads((DATA / "summary.json").read_text())
    pub = json.loads((NOTES / "published150.json").read_text())
    manifest = json.loads((NOTES / "function_tasks.json").read_text())
    for item in manifest:
        item["published_reward"] = pub["per_task"].get(item["task"], {})
    void = json.loads((NOTES / "void_trials_run150.json").read_text())
    sens_spec = json.loads((NOTES / "sens_run150.json").read_text())
    runner = (RUN / "data/run150_runner.log").read_text(errors="replace")
    commands = (NOTES / "run150-commands.md").read_text(errors="replace")

    official = B.official_rows(rows)
    by_arm = B.group_by_arm(official)
    index = B.official_index(official)
    by_lang = B.grouped_reward_counts(manifest, index, "lang")
    by_cwe = B.grouped_reward_counts(manifest, index, "cwe")

    CHARTS.mkdir(parents=True, exist_ok=True)
    B.plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "svg.fonttype": "none"})
    B.plot_rates(by_arm)
    B.plot_reward_by_language(by_lang, {a: len(by_arm[a]) for a in ARMS})
    B.plot_heatmap(manifest, index, by_arm)
    B.plot_outcomes(by_arm)
    B.plot_agent_time(by_arm)
    B.plot_cost_per_task(manifest, index)
    B.plot_tokens(by_arm)
    B.write_group_csv(DATA / "by_language.csv", "language", by_lang)
    B.write_group_csv(DATA / "by_cwe.csv", "cwe", by_cwe)
    B.make_csv(DATA / "per_task_wide.csv",
               ["task", "language", "cwe", "DS_functional", "DS_secure", "DS_reward", "M_functional", "M_secure", "M_reward",
                "DS_agent_minutes", "M_agent_minutes", "DS_total_tokens", "M_total_tokens",
                "GLM-5.3_published_reward", "DeepSeek-V4-Pro_published_reward"],
               B.build_per_task_rows(manifest, index))

    L = []
    w = L.append
    w("# LSCBench function-level run (all 150 tasks): DeepSeek Flash vs Mistral Large 4\n")
    w("**Caveat:** all 150 `*_function` tasks of LSCBench v1.0 (one of three tiers; the official score uses all 450). "
      "Not an official LSCBench leaderboard score. Each arm is a model **plus** its agent harness "
      "(Claude Code 2.1.143 for DeepSeek, Vibe 3.1.3 for Mistral), so differences are not pure model differences.\n")


    ev = runner_events(runner)
    w("## Setup\n")
    w(B.markdown_table(["Setting", "DeepSeek arm", "Mistral arm", "Shared / notes"], [
        ["Agent + version", "claude-code 2.1.143 (`lscb_agents:ClaudeCodeFallbackInstall`)", "vibe 3.1.3 (`lscb_agents:VibeNoPluginCache`)", "Same wrappers as the 30-task pilot"],
        ["Model ID", "deepseek-flash", "mistral-large-4-0", "—"],
        ["Reasoning", "effort=max", "thinking=high", "—"],
        ["Provider + endpoint", "https://api.deepseek.com/anthropic (official API)", "https://api.mistral.ai (Vibe CLI, Mistral plan)", "Only these hosts allowed from the agent"],
        ["Harness / dataset", "Harbor 0.26.0", "Harbor 0.26.0", "last-secure-code-benchmark@v1.0, all 150 `*_function` tasks"],
        ["Concurrency", "5 trials", "5 trials", "Both arms concurrent; 8 strided batches of 18–19; retries 0"],
        ["Host", "—", "—", "Factory VPS: 16 vCPU, 62 GB RAM; separate Docker 29.9.2 daemon under /srv/bench (isolated from Otter)"],
        ["Run window (UTC)", ev[0][0] if ev else "—", ev[-1][0] if ev else "—", "First and last runner event; timeline below"],
    ]) + "\n")
    w("## Headline\n")
    hdr = ["Metric"] + [LBL[a] for a in ARMS]
    t = []
    for col, name in (("reward", "Works and secure (reward)"), ("functional", "Works (functional)"), ("secure", "Secure")):
        t.append([name] + [pct(sum(B.score_pass(r, col) for r in by_arm[a]), len(by_arm[a])) for a in ARMS])
    t.append(["Trials with an exception"] + [str(sum(1 for r in by_arm[a] if r.get("exception_type"))) for a in ARMS])
    t.append(["Median / p90 agent time per task (min)"] + [f"{B.format_minutes(med([num(r['agent_execution_s']) for r in by_arm[a]]))} / {B.format_minutes(p90([num(r['agent_execution_s']) for r in by_arm[a]]))}" for a in ARMS])
    for a in ARMS:
        pass
    tok = {a: (sum(num(r["input_tokens"]) or 0 for r in by_arm[a]), sum(num(r["cached_input_tokens"]) or 0 for r in by_arm[a]),
               sum(num(r["output_tokens"]) or 0 for r in by_arm[a])) for a in ARMS}
    t.append(["Input tokens (cached share) / output tokens"] + [f"{tok[a][0]/1e6:.1f}M ({100*tok[a][1]/max(tok[a][0],1):.0f}%) / {tok[a][2]/1e6:.2f}M" for a in ARMS])
    cost = {a: sum(num(r["cost_usd"]) or 0 for r in by_arm[a]) for a in ARMS}
    t.append(["Cost (official rows)", f"${cost[ARMS[0]]:.2f} billed (DeepSeek list price)", f"${cost[ARMS[1]]:.2f} API-equivalent (covered by the Mistral plan)"])
    rew = {a: sum(B.score_pass(r, "reward") for r in by_arm[a]) for a in ARMS}
    t.append(["Cost per secure solve"] + [f"${cost[a]/rew[a]:.3f}" if rew[a] else "—" for a in ARMS])
    missing = {a: sum(1 for r in by_arm[a] if not r.get("input_tokens")) for a in ARMS}
    t.append(["Official rows without token telemetry"] + [str(missing[a]) for a in ARMS])
    w(B.markdown_table(hdr, t) + "\n")

    ds, mi = index[ARMS[0]], index[ARMS[1]]
    common = sorted(set(ds) & set(mi))
    both = sum(B.score_pass(ds[k], "reward") and B.score_pass(mi[k], "reward") for k in common)
    d_only = sum(B.score_pass(ds[k], "reward") and not B.score_pass(mi[k], "reward") for k in common)
    m_only = sum(not B.score_pass(ds[k], "reward") and B.score_pass(mi[k], "reward") for k in common)
    w("## Head-to-head on the same tasks\n")
    w(B.markdown_table(["Both secure", "DeepSeek only", "Mistral only", "Neither", "Exact McNemar p"],
                       [[both, d_only, m_only, len(common) - both - d_only - m_only, f"{B.mcnemar_exact(d_only, m_only):.3f}"]]) + "\n")

    w("## Published results on the same 150 function tasks\n")
    w("From the upstream `traces/catalog.json` (Claude Code / Codex, max effort). Different agents and settings; context only.\n")
    w(B.markdown_table(["Model (published)", "Reward", "Functional"],
                       [[m, f"{pub['totals'][m]['reward']}/150 ({100*pub['totals'][m]['reward']/150:.1f}%)", f"{pub['totals'][m]['functional']}/150"] for m in PUB_MODELS]) + "\n")

    w("## Outcome classes\n")
    cls = {a: Counter(B.classify_outcome(r) for r in by_arm[a]) for a in ARMS}
    keys = ["reward pass", "functional only", "functional fail", "unscored (exception, no verifier result)"]
    w(B.markdown_table(["Outcome"] + [SHORT[a] for a in ARMS], [[k] + [cls[a][k] for a in ARMS] for k in keys]) + "\n")
    w("![Rates](charts/rates_ci.svg)\n\n![Outcomes](charts/outcomes.svg)\n")

    def group_table(groups, key):
        return B.markdown_table([key, "n", "DeepSeek reward", "Mistral reward"],
                                [[g, c[ARMS[0]][1], f"{c[ARMS[0]][0]}/{c[ARMS[0]][1]}", f"{c[ARMS[1]][0]}/{c[ARMS[1]][1]}"] for g, c in groups])
    w("## By language\n"); w(group_table(by_lang, "Language") + "\n"); w("![By language](charts/reward_by_language.svg)\n")
    w("## By CWE\n"); w(group_table(by_cwe, "CWE") + "\n")

    w("## Speed (seconds, official rows)\n")
    w(B.markdown_table(["Phase"] + [f"{SHORT[a]} median" for a in ARMS] + [f"{SHORT[a]} p90" for a in ARMS],
                       [[name] + [B.format_seconds(med([num(r[c]) for r in by_arm[a]])) for a in ARMS] + [B.format_seconds(p90([num(r[c]) for r in by_arm[a]])) for a in ARMS]
                        for c, name in B.TIME_COLUMNS]) + "\n")
    w("![Agent time](charts/agent_time.svg)\n\n![Tokens](charts/tokens.svg)\n\n![Cost per task](charts/cost_per_task.svg)\n")

    bal = [float(x) for x in re.findall(r"deepseek_balance=([0-9.]+)", runner)]
    allcost = sum(num(r["cost_usd"]) or 0 for r in rows if r["arm"] == ARMS[0])
    w("## DeepSeek cost check\n")
    if bal:
        w(f"Balance from the runner's guard log: first ${bal[0]:.2f}, last ${bal[-1]:.2f} (drop ${bal[0]-bal[-1]:.2f}). "
          f"Computed list-price cost of all DeepSeek trials in this report, including void ones: ${allcost:.2f}. "
          "Runs after the last guard sample are not in the drop.\n")


    w("## What the models missed\n")
    w("Every official row with `secure=0` (security miss) or `functional=0` (functional miss). Full rows are in `data/trials.csv`.\n")
    mc = {a: Counter(r["cwe"] for r in by_arm[a] if B.score_pass(r, "functional") and r.get("secure") not in ("", None) and not B.score_pass(r, "secure")) for a in ARMS}
    cw = sorted(set(mc[ARMS[0]]) | set(mc[ARMS[1]]), key=lambda c: -(mc[ARMS[0]][c] + mc[ARMS[1]][c]))
    w("### Works but not secure, by CWE\n")
    w(B.markdown_table(["CWE", "DeepSeek", "Mistral"], [[c, mc[ARMS[0]][c], mc[ARMS[1]][c]] for c in cw]) + "\n")
    w("### Security failures\n")
    w(B.markdown_table(["Arm", "Task", "CWE", "n_failed_vuln", "vulnerability_msg (≤200 chars)"],
                       [[SHORT[r["arm"]], r["task"], r["cwe"], r.get("n_failed_vuln", ""), B.vulnerability_display(r)]
                        for a in ARMS for r in by_arm[a] if r.get("secure") not in ("", None) and not B.score_pass(r, "secure")]) + "\n")
    w("### Functional failures\n")
    w(B.markdown_table(["Arm", "Task", "n_failed_func", "failed_func_tests", "Exception"],
                       [[SHORT[r["arm"]], r["task"], r.get("n_failed_func", ""), short(r.get("failed_func_tests") or "—", 160), r.get("exception_type") or "—"]
                        for a in ARMS for r in by_arm[a] if not B.score_pass(r, "functional")]) + "\n")
    w("## Errors and exceptions (official rows)\n")
    er = [[SHORT[r["arm"]], r["task"], r["exception_type"], "yes" if r.get("reward") not in ("", None) else "no", short(r.get("exception_msg"), 90)]
          for r in official if r.get("exception_type")]
    w(B.markdown_table(["Arm", "Task", "Exception", "Scored", "Message"], er) + "\n")

    w("## Vibe self-termination (Mistral)\n")
    w("Harbor's Vibe adapter passes the task text on Vibe's command line (`--prompt=<text>`). When the model runs `pkill -f <pattern>` "
      "and the pattern also matches text in the prompt, it kills its own Vibe process (exit 143). Claude Code receives the prompt differently, "
      "so the DeepSeek arm cannot hit this. Main-run results keep these trials as scored attempts (the verifier grades whatever code exists).\n")
    sk = [[r["task"], r["batch"], re.search(r"exit (\d+)", r.get("exception_msg") or "").group(1), r.get("functional"), r.get("secure"), r.get("reward")]
          for r in by_arm[ARMS[1]] if re.search(r"exit 1(43|37)", r.get("exception_msg") or "")]
    w(B.markdown_table(["Task", "Batch", "Exit", "F", "S", "R"], sk) + "\n")
    w(f"Sensitivity rule: {sens_spec['rule']}\n")
    sr = sens_rows()
    if sr:
        mrow = index[ARMS[1]]
        w(B.markdown_table(["Job", "Task", "Main-run F/S/R", "Sensitivity F/S/R", "Sensitivity exception"],
                           [[s["job"], s["task"], "/".join(str(mrow.get(s["task"], {}).get(c, "—")) for c in ("functional", "secure", "reward")),
                             f'{s["functional"]}/{s["secure"]}/{s["reward"]}', s["exception"] or "—"] for s in sr]) + "\n")
        done = {s["task"]: s for s in sr}
        main_r = sum(B.score_pass(r, "reward") for r in by_arm[ARMS[1]])
        delta = sum((done[t]["reward"] or 0) - (1 if B.score_pass(mrow[t], "reward") else 0) for t in done if t in mrow)
        w(f"Sensitivity view (not the headline): replacing the {len(done)} affected Mistral trials with their prompt-file re-runs gives "
          f"{main_r + delta}/{len(by_arm[ARMS[1]])} reward for Mistral (main run: {main_r}/{len(by_arm[ARMS[1]])}). "
          "Each re-run is a fresh sample, so changes mix the runner fix with normal run-to-run variation; DeepSeek trials were not re-run, so this is a check of the runner flaw, not a head-to-head. "
          "cve-2019-15150 ended with exit 143 again under `--prompt-file` (and Vibe's logs were again lost when the container's init process stopped), so that termination is not explained by the prompt being on the command line.\n")
    else:
        w("Sensitivity re-run results: not available yet.\n")

    w("## Void trials and re-runs\n")
    w(f"Policy: {void.get('policy', '')}\n")
    vr = []
    for e in void["void"] + void.get("infra_rerun", []) + void.get("infra_rerun2", []):
        arm = "deepseek-cc" if e["job"].endswith("deepseek-cc") else "mistral-vibe"
        rep = index[arm].get(e["task"], {})
        vr.append([e["job"], e["task"], short(e["reason"], 70), rep.get("job", "—"), B.rerun_outcome(rep) if rep else "no replacement"])
    for t_ in void.get("pending_never_started", {}).get("tasks", []):
        for arm in ARMS:
            rep = index[arm].get(t_, {})
            vr.append([f"run150-b1-{arm}", t_, "never started (batch-1 job crash)", rep.get("job", "—"), B.rerun_outcome(rep) if rep else "no replacement"])
    w(B.markdown_table(["Original job", "Task", "Reason", "Official row from", "Outcome"], vr) + "\n")

    w("## Run timeline (UTC)\n")
    w(B.markdown_table(["Time", "Event"], [list(e) for e in runner_events(runner)]) + "\n")

    w("## Per-task results\n")
    pt = []
    for item in manifest:
        k = item["task"]; a, b = ds.get(k, {}), mi.get(k, {})
        f = lambda r: "".join("—" if r.get(c) in ("", None) else ("✓" if B.score_pass(r, c) else "✗") for c in ("functional", "secure", "reward")) if r else "missing"
        pt.append([k, item["lang"], item["cwe"], f(a), f(b), B.format_minutes(num(a.get("agent_execution_s"))), B.format_minutes(num(b.get("agent_execution_s"))),
                   item["published_reward"].get("GLM-5.3", "—"), item["published_reward"].get("DeepSeek-V4-Pro", "—")])
    w("F/S/R = functional / secure / reward.\n")
    w(B.markdown_table(["Task", "Lang", "CWE", "DeepSeek F/S/R", "Mistral F/S/R", "DS agent min", "M agent min", "GLM-5.3 pub.", "DSV4-Pro pub."], pt) + "\n")
    w("![Heatmap](charts/task_heatmap.svg)\n")

    w("## Run notes (verbatim)\n")
    w(commands + "\n")
    w("## Provenance\n")
    for s in ["Tasks: `notes/function_tasks.json`", "Commands, settings and incidents: `notes/run150-commands.md`",
              "Void/re-run policy: `notes/void_trials_run150.json`", "Sensitivity rule: `notes/sens_run150.json`",
              "Published reference: `notes/published150.json`", "Trial rows: `run150/report/data/trials.csv` (from `report150/extract.py`)",
              "Runner log, host samples, pulls, Harbor logs: `run150/data/`", "Raw Harbor jobs: `run150/jobs/run150-*`",
              "Generator: `python3 report150/build_report.py`"]:
        w(f"- {s}")
    out = "\n".join(L) + "\n"
    out = B.PATH_RE.sub(lambda m: m.group(0), out) if hasattr(B, "PATH_RE") else out
    (REPORT / "README.md").write_text(out, encoding="utf-8")
    print("built", REPORT / "README.md", len(out))


if __name__ == "__main__":
    main()
