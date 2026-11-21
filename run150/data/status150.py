import json, glob, sys
for j in sorted(glob.glob("/srv/bench/lscb/jobs/run150-*")):
    rs = [json.load(open(f)) for f in glob.glob(j + "/*/result.json")]
    out = []
    for r in rs:
        v = (r.get("verifier_result") or {}).get("rewards") or {}
        e = (r.get("exception_info") or {}).get("exception_type")
        out.append(f"{r['task_name'].split('/')[-1][:22]}:{v.get('functional')}/{v.get('secure')}" + (f" {e}" if e else ""))
    rw = sum(1 for r in rs if ((r.get("verifier_result") or {}).get("rewards") or {}).get("reward") == 1)
    print(j.split("/")[-1], len(glob.glob(j + "/*/")), "trials", len(rs), "done", "reward", rw)
    if "-v" in sys.argv: print("   ", "; ".join(out))
