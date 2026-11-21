# LSCBench secure-code comparison: DeepSeek Flash (Claude Code) vs Mistral Large 4 (Vibe)

Consolidated report: the 150-task function-level run (headline) and the 30-task pilot (repeat run). Web version: https://lab.chris-wozniczek.dev/lab/lscbench. Raw results: https://github.com/chris-wozniczek/lscbench-deepseek-vs-mistral.

## TLDR

- DeepSeek Flash in Claude Code 2.1.143 (effort max) wrote working and secure code on 39 of 150 tasks (26.0%, 95% Wilson CI 19.6 to 33.6%). Mistral Large 4 in Vibe 3.1.3 (thinking high) did it on 29 (19.3%, 13.8 to 26.4%).
- Both almost always produce working code: 144 and 143 of 150 pass the functional tests. On 100 tasks both models' code worked and both reintroduced the vulnerability.
- Paired on the same tasks: 26 both secure, 13 only DeepSeek, 3 only Mistral, 108 neither. Exact two-sided McNemar p = 0.021.
- Agent time per task, median / p90: DeepSeek 3.0 / 11.5 min, Mistral 5.8 / 21.9 min.
- Cost for 150 tasks: DeepSeek $6.25 (official API usage at list price), Mistral $42.87 API-equivalent (run on a subscription). Per secure solve: $0.160 vs $1.478.
- Repeat: the 30-task pilot, run a day earlier on a different machine with the same settings, gave the same outcome on 28/30 tasks for DeepSeek and 27/30 for Mistral. The pilot is not pooled with the 150 run.
- Vibe's launcher let Mistral kill its own agent on 12 trials. Re-running those 12 with the prompt passed from a file left Mistral at 29/150 (one gain, one loss). This is a sensitivity check only; the headline is unchanged.
- Scope: the 150 function-level tasks of LSCBench v1.0, not the official 450-task score. It compares model plus agent, not bare models. Published LSCBench traces for the same 150 tasks (GLM-5.3 37, DeepSeek-V4-Pro 34, Qwen3.8-Max 34, Claude-Fable-5 33, GPT-5.6-Sol 30, Kimi-K3 27) are context from other runs, not part of this experiment.

## How the two runs fit together

| | 150-task run (headline) | 30-task pilot (repeat) |
| --- | --- | --- |
| Tasks | All 150 function-level tasks | 30 of the same tasks, seed 20261120 |
| Date | 21 Nov 2026 | 20 Nov 2026 |
| Host | VPS, 16 cores, separate Docker daemon | Cloud VM |
| Concurrency | 5 trials per model | 3 trials per model (2 for re-runs) |
| DeepSeek works and secure | 39/150 | 7/30 |
| Mistral works and secure | 29/150 | 8/30 |
| DeepSeek / Mistral median agent time | 3.0 / 5.8 min | 1.9 / 6.8 min |
| DeepSeek / Mistral cost | $6.25 / $42.87 | $0.90 / $6.60 |
| Head-to-head (DS only / M only) | 13 / 3, p = 0.021 | 1 / 2, p = 1.0 |

Repeat on the 30 shared tasks (pilot vs 150 run, works-and-secure):

| | Both runs secure | Pilot only | 150 run only | Neither | Same outcome |
| --- | --- | --- | --- | --- | --- |
| DeepSeek Flash | 7 | 0 | 2 | 21 | 28/30 |
| Mistral Large 4 | 6 | 2 | 1 | 21 | 27/30 |

Who ran it: the harness, runs and analysis were done by Devin (Cognition's coding agent) on Chris Wozniczek's server. Every number is computed from the raw logs in the GitHub repository.

Part 1 below is the full 150-task report. Part 2 is the full pilot report.
