"""Run batch-1 leftovers once: void (harness-cancelled) trials + never-started tasks."""
import json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import run_150 as R

v = json.load(open(R.ROOT / "notes/void_trials_run150.json"))
pending = v["pending_never_started"]["tasks"]
sel = {"deepseek": list(pending), "mistral": list(pending)}
for e in v["void"]:
    if e["job"] == "run150-b1-deepseek-cc":
        sel["deepseek"].append(e["task"])
    elif e["job"] == "run150-b1-mistral-vibe":
        sel["mistral"].append(e["task"])
for e in v.get("infra_rerun", []):
    arm = "deepseek" if e["job"].endswith("deepseek-cc") else "mistral"
    if e["task"] not in sel[arm]:
        sel[arm].append(e["task"])
names = {"deepseek": "run150-b1rest-deepseek-cc", "mistral": "run150-b1rest-mistral-vibe"}
dk = os.environ["DEEPSEEK_API_KEY"]
mk = R.read_mistral_key()
prefixes = [dk[:12].encode(), mk[:12].encode()]
env = {k: x for k, x in os.environ.items() if not k.startswith(R.PREFIXES_TO_SCRUB)}
sampler = subprocess.Popen([sys.executable, str(R.DATA / "host_sampler.py"), str(R.DATA / "host_samples_run150_b1rest.csv")],
                           env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
time.sleep(5)
R.log("b1rest selection deepseek: " + ", ".join(sel["deepseek"]))
R.log("b1rest selection mistral: " + ", ".join(sel["mistral"]))
try:
    rc = R.run_batch(1, list(dict.fromkeys(sel["deepseek"] + sel["mistral"])), dk, mk, prefixes, sampler,
                     tasks_by_arm=sel, job_name_overrides=names, stage_label="b1rest",
                     pull_batch_label="b1rest", cleanup_job_names=list(names.values()))
finally:
    sampler.terminate()
sys.exit(rc)
