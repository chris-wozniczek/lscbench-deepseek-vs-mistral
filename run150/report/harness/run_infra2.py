"""Second infra re-run of cve-2024-1086_function in both arms, with a 3x environment-build timeout.

The task's environment build (Linux kernel tree) exceeded Harbor's 600 s build timeout in batch 4 and again in
b1rest, in both arms, before the agent received the prompt. Agent, verifier and model settings are unchanged.
"""
import os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import run_150 as R

TASK = "cve-2024-1086_function"
NAMES = {"deepseek": "run150-infra2-deepseek-cc", "mistral": "run150-infra2-mistral-vibe"}
_command = R.command


def command_long_build(*args, **kwargs):
    name, argv = _command(*args, **kwargs)
    return name, argv + ["--environment-build-timeout-multiplier", "3"]


R.command = command_long_build
dk = os.environ["DEEPSEEK_API_KEY"]
mk = R.read_mistral_key()
prefixes = [dk[:12].encode(), mk[:12].encode()]
env = {k: x for k, x in os.environ.items() if not k.startswith(R.PREFIXES_TO_SCRUB)}
sampler = subprocess.Popen([sys.executable, str(R.DATA / "host_sampler.py"), str(R.DATA / "host_samples_infra2.csv")],
                           env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
time.sleep(5)
R.log(f"infra2 selection both arms: {TASK} (environment-build-timeout-multiplier 3)")
try:
    rc = R.run_batch(0, [TASK], dk, mk, prefixes, sampler, tasks_by_arm={"deepseek": [TASK], "mistral": [TASK]},
                     job_name_overrides=NAMES, stage_label="infra2", pull_batch_label="infra2",
                     cleanup_job_names=list(NAMES.values()))
finally:
    sampler.terminate()
sys.exit(rc)
