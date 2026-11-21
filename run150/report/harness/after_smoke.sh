#!/bin/bash
# Wait for the VibePromptFile smoke to finish; start the full sensitivity job only if the smoke shows no agent kill (exit 143/137).
LOG=/srv/bench/lscb/data/run150_runner.log
cd /srv/bench/lscb
while pgrep -u bench -f "run_sens.py run150-senssmoke" >/dev/null; do sleep 30; done
bad=$(python3 -c "
import json,glob
for f in glob.glob('jobs/run150-senssmoke-mistral-vibe/*/result.json'):
    m=(json.load(open(f)).get('exception_info') or {}).get('exception_message') or ''
    print('bad' if ('exit 143' in m or 'exit 137' in m) else 'ok')
")
echo "$(date -u +%FT%T+00:00) AFTER_SMOKE: smoke result check = ${bad:-missing}" >> "$LOG"
[ "$bad" = "ok" ] || exit 1
su - bench -c "cd /srv/bench/lscb && set -a && . /srv/bench/etc/keys.env && set +a && .venv/bin/python harness/run_sens.py >> data/run150_stdout.log 2>&1 < /dev/null"
echo "$(date -u +%FT%T+00:00) AFTER_SMOKE: full sens exited rc=$?" >> "$LOG"
