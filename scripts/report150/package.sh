#!/bin/bash
# Package the 150-task report (zip) and raw evidence (tar.zst), after a key-prefix scan.
set -euo pipefail
cd /home/ubuntu/lscb-bench
R=run150/report
mkdir -p $R/data $R/harness deliver
cp notes/function_tasks.json notes/run150-commands.md notes/run150-plan.md notes/void_trials_run150.json notes/sens_run150.json notes/published150.json $R/data/
cp report150/extract.py report150/build_report.py report150/package.sh $R/
cp report/build_report.py $R/pilot_build_report_helpers.py
cp harness/run_150.py harness/run_b1rest.py harness/run_sens.py harness/run_infra2.py harness/lscb_agents.py harness/resume_watch.sh harness/chain_after150.sh harness/after_smoke.sh $R/harness/
eval "$(ssh -i ~/.ssh/otter_factory root@<vps-host> "grep -E '^(DEEPSEEK|MISTRAL)_API_KEY=' /srv/bench/etc/keys.env" | sed 's/^/export /')"
python3 - <<'PY'
import os, pathlib, sys
pre = [os.environ[k][:12].encode() for k in ("DEEPSEEK_API_KEY", "MISTRAL_API_KEY") if os.environ.get(k)]
assert pre, "no key prefixes in env to scan for"
hits = []
for root in ("run150/report", "run150/jobs", "run150/data"):
    for p in pathlib.Path(root).rglob("*"):
        if p.is_file():
            b = p.read_bytes()
            if any(x in b for x in pre):
                hits.append(str(p))
print("key-prefix hits:", len(hits)); [print(" ", h) for h in hits[:20]]
sys.exit(1 if hits else 0)
PY
rm -f deliver/lscbench-run150-report.zip
(cd run150 && zip -qr ../deliver/lscbench-run150-report.zip report -x 'report/__pycache__/*')
tar -C run150 -I 'zstd -10 -T0' -cf deliver/lscbench-run150-raw.tar.zst jobs data
ls -la deliver/lscbench-run150-*
