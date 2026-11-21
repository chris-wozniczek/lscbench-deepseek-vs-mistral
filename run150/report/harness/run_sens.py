"""Mistral-only sensitivity re-run with lscb_agents:VibePromptFile (prompt via --prompt-file).

Usage: run_sens.py [JOB_NAME] [TASK ...]   (defaults: notes/sens_run150.json job + tasks)
Results are reported separately and never replace main-run results.
"""
import json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import run_150 as R

spec = json.load(open(R.ROOT / "notes/sens_run150.json"))
job = sys.argv[1] if len(sys.argv) > 1 else spec["job"]
tasks = sys.argv[2:] or spec["tasks"]

_command = R.command
def command_prompt_file(*args, **kwargs):
    name, argv = _command(*args, **kwargs)
    argv = ["lscb_agents:VibePromptFile" if a == "lscb_agents:VibeNoPluginCache" else a for a in argv]
    assert "lscb_agents:VibePromptFile" in argv
    return name, argv
R.command = command_prompt_file

dk = os.environ["DEEPSEEK_API_KEY"]
mk = R.read_mistral_key()
prefixes = [dk[:12].encode(), mk[:12].encode()]
env = {k: x for k, x in os.environ.items() if not k.startswith(R.PREFIXES_TO_SCRUB)}
sampler = subprocess.Popen([sys.executable, str(R.DATA / "host_sampler.py"), str(R.DATA / f"host_samples_{job}.csv")],
                           env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
time.sleep(5)
R.log(f"{job} selection mistral ({len(tasks)}): " + ", ".join(tasks))
try:
    rc = R.run_batch(0, tasks, dk, mk, prefixes, sampler, arms=("mistral",),
                     tasks_by_arm={"mistral": tasks}, job_name_overrides={"mistral": job},
                     stage_label=job, pull_batch_label=job, cleanup_job_names=[job])
finally:
    sampler.terminate()
sys.exit(rc)
