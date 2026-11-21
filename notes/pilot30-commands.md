# Pilot30 DeepSeek launch

- UTC start: `2026-11-20T15:44:53+00:00`
- Frozen task source: `notes/pilot30.json` (30 tasks, file order; unchanged)
- Credentials: `ANTHROPIC_API_KEY` sourced from host `DEEPSEEK_API_KEY`; `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic`.
- Docker configuration: anonymous `/home/ubuntu/lscb-bench/data/docker-anon`.
- DeepSeek balance before launch: USD `6.13` (recorded at `2026-11-20T15:44:53+00:00` in `data/deepseek_balance.csv`).
- Host sampler: `data/host_samples_pilot30.csv` (30-second interval).
- No API key value appears in the command line below.

```sh
```

## Aborted batch 1 — 2026-11-20 UTC

- Started at `16:50:47Z` with `29.390 GB` available and DeepSeek balance `$6.00`.
- Guard samples: `16:51:48Z` `19.657 GB`; `16:52:48Z` `14.867 GB`; `16:53:48Z` `14.959 GB`; `16:54:49Z` `7.540 GB` (guard tripped).
- Cause: concurrent trials built per-trial `__env-main` images on top of the batch base images, consuming about `21.85 GB` in four minutes. Harbor was SIGINTed; image removal then failed for images still referenced by stopped containers.

## Re-run policy (decided 2026-11-20 17:45 UTC, before any re-run)
- A trial is re-run once ONLY if it failed before the agent received the task prompt (agent install/setup or environment build/pull error, e.g. network download failure). Such trials are reported as infra failures and the re-run result is marked `rerun_infra=1`.
- Agent timeouts (exit 143), agent crashes after the prompt, API errors during execution, and verifier failures count as the single official attempt and are never re-run.
- Batch 1: `pilot30-b1-mistral-vibe/ssrf_dms_instance_ping_function` = Vibe install failed (uv Python download "error reading a body from connection") → re-run after batch 3.

## Batch 3 disk-guard incident and void rule (decided 2026-11-20 20:35 UTC, before any re-run)
- 20:24:10 free disk 34.5 GB after mid-batch cleanup; 20:25:10 free 5.4 GB (concurrent environment image builds); guard sent SIGINT at 20:25:11.
- Rule added: trials killed by our own guard SIGINT are void (not a model outcome) and re-run once with identical settings, both arms. Clean finishes after the SIGINT are kept. List: notes/void_trials.json.
- Mistral cve-2020-11008 / cve-2023-51450 were still running after the SIGINT; they are judged by the same rule once they end.

## Re-run 1

Started 2026-11-20T20:44:09+00:00 UTC with `-n 2` per arm and `--max-retries 0`.
Mistral optional-task selection: `cve-2020-11008_function` included because cve-2020-11008_function__SAS3erm: CancelledError; `cve-2023-51450_function` included because cve-2023-51450_function__dowGicm: CancelledError

DeepSeek command (key-free):
```text
/home/ubuntu/lscb-bench/.venv/bin/harbor run -d last-secure-code-benchmark/last-secure-code-benchmark@v1.0 --agent lscb_agents:ClaudeCodeFallbackInstall -m deepseek-flash --ak version=2.1.143 --ak reasoning_effort=max --allow-agent-host api.deepseek.com -i last-secure-code-benchmark/cve-2020-11008_function -i last-secure-code-benchmark/cve-2021-46104_function -i last-secure-code-benchmark/cve-2023-51450_function -i last-secure-code-benchmark/xss_codeforge_readme_render_function -n 2 --max-retries 0 --jobs-dir /home/ubuntu/lscb-bench/jobs --job-name pilot30-rerun1-deepseek-cc
```

Mistral/Vibe command (key-free):
```text
/home/ubuntu/lscb-bench/.venv/bin/harbor run -d last-secure-code-benchmark/last-secure-code-benchmark@v1.0 --agent lscb_agents:VibeNoPluginCache -m mistral/mistral-large-4-0 --ak version=3.1.3 --ak thinking=high --allow-agent-host api.mistral.ai -i last-secure-code-benchmark/ssrf_dms_instance_ping_function -i last-secure-code-benchmark/cve-2017-17714_function -i last-secure-code-benchmark/xss_codeforge_readme_render_function -i last-secure-code-benchmark/cve-2020-11008_function -i last-secure-code-benchmark/cve-2023-51450_function -n 2 --max-retries 0 --jobs-dir /home/ubuntu/lscb-bench/jobs --job-name pilot30-rerun1-mistral-vibe
```

Commands were launched with API credentials supplied only through the host environment.
- Re-run 1, Mistral xss_codeforge_readme_render_function: Vibe was terminated 2 s after launch with no session and no model call (export.json outcome=terminated, usage=null). Under the pre-prompt failure rule it is void and re-run once more as `pilot30-rerun2-mistral-vibe`.

## Re-run 2

Started 2026-11-20T21:18:14+00:00 UTC; one Mistral/Vibe task, `-n 1`, `--max-retries 0`.
Task: `xss_codeforge_readme_render_function`.

Key-free command:
```text
/home/ubuntu/lscb-bench/.venv/bin/harbor run -d last-secure-code-benchmark/last-secure-code-benchmark@v1.0 --agent lscb_agents:VibeNoPluginCache -m mistral/mistral-large-4-0 --ak version=3.1.3 --ak thinking=high --allow-agent-host api.mistral.ai -i last-secure-code-benchmark/xss_codeforge_readme_render_function -n 1 --max-retries 0 --jobs-dir /home/ubuntu/lscb-bench/jobs --job-name pilot30-rerun2-mistral-vibe
```

Mistral credentials were supplied only through the host environment.
