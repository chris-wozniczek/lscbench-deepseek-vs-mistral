# LSCBench raw results: DeepSeek Flash (Claude Code) vs Mistral Large 4 (Vibe)

Every raw artifact behind the report at **https://lab.chris-wozniczek.dev/lab/lscbench**: Harbor job directories, agent sessions, verifier output, runner logs, host samples, manifests, harness code and the scripts that compute every number in the report.

Benchmark: [LSCBench v1.0](https://github.com/alibaba/last-secure-code-benchmark) via Harbor (`last-secure-code-benchmark/last-secure-code-benchmark@v1.0`), the 150 function-level tasks. This is **not** an official 450-task LSCBench score, and it compares model plus agent, not bare models.

## Headline (150-task run, official rows only)

| | DeepSeek Flash / Claude Code 2.1.143, effort max | Mistral Large 4 / Vibe 3.1.3, thinking high |
| --- | --- | --- |
| Works and secure (reward) | 39/150 (26.0%, 95% Wilson 19.6 to 33.6%) | 29/150 (19.3%, 13.8 to 26.4%) |
| Works (functional) | 144/150 | 143/150 |
| Median / p90 agent time | 3.0 / 11.5 min | 5.8 / 21.9 min |
| Cost | $6.25 (official API usage, list price) | $42.87 API-equivalent (ran on a subscription) |

Paired: 26 both, 13 DeepSeek only, 3 Mistral only, 108 neither; exact McNemar p = 0.021. The 30-task pilot (20 Nov 2026) is a separate earlier run on 30 of the same tasks and is used only as a repeat: same outcome on 28/30 (DeepSeek) and 27/30 (Mistral) tasks.

## Layout

```
run150/jobs/     Harbor job dirs, one per batch and arm: run150-b1..b8 (main), b1rest (one-time re-runs),
                 infra2 (second infra re-run of cve-2024-1086, documented deviation),
                 sens / senssmoke (Mistral prompt-file sensitivity re-runs, NOT in the headline)
  <job>/<task>__<id>/result.json   rewards (functional, secure, reward), timings, exception
  <job>/<task>__<id>/agent/        full agent session: Claude Code stream-json + trajectory, or Vibe session journal
  <job>/<task>__<id>/verifier/     verifier output: functional and vulnerability test results
  <job>/<task>__<id>/artifacts/    files collected from the container after the run
run150/data/     runner logs, harbor_<job>.log, host samples, image-pull timings, DeepSeek balance samples
run150/report/   generated 150-task report (README.md), charts, trials.csv, per-task and group CSVs, summary.json
pilot30/         same structure for the 30-task pilot, including aborted and void attempts
notes/           task manifests (function_tasks.json, pilot30.json), exact commands and settings,
                 void/re-run rules and mappings (void_trials*.json), sensitivity rule (sens_run150.json),
                 published same-task reference scores (published150.json), run timeline (run150-plan.md)
harness/         runner scripts and the custom Harbor agent wrappers (lscb_agents.py)
scripts/         extraction and report generators (extract.py, build_report.py, export_site.py, consolidate.py)
```

## Rules applied

- One attempt per task per model, no automatic retries, 60-minute agent limit, 10-minute environment start limit.
- A trial is re-run once only if it failed before the model received the prompt, or was killed by the harness or its disk guard. Agent errors, timeouts and self-kills count as the attempt. Rules and lists were written in `notes/` before any re-run. `void=1` / `official=0` rows in `trials.csv` mark replaced trials.
- Mistral sensitivity re-runs (`run150-sens*`) never replace main-run results.

## Verify the headline yourself

```
python3 - <<'PY'
import csv
rows = [r for r in csv.DictReader(open("run150/report/data/trials.csv")) if r["official"] == "1"]
for arm in ("deepseek-cc", "mistral-vibe"):
    rs = [r for r in rows if r["arm"] == arm]
    print(arm, len(rs), "reward", sum(r["reward"] == "1" for r in rs), "functional", sum(r["functional"] == "1" for r in rs))
PY
```

Each row's `job` and `trial` columns point to `run150/jobs/<job>/<trial>/result.json`, which holds the verifier's rewards. `scripts/report150/extract.py` rebuilds `trials.csv` from the job directories.

## Notes

- 3 Mistral trials in the 150 run have no token data: Vibe stopped its container before Harbor copied the logs. Grades are unaffected.
- The server address is replaced with `<vps-host>`. No API keys are present (scanned for both provider key prefixes and generic key patterns).
- Task text and tests belong to LSCBench and keep its canary string. Please do not use this data for model training.
- Runs, harness and analysis by Devin (Cognition) for Chris Wozniczek.
