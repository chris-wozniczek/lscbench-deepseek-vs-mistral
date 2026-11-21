#!/bin/bash
# After run_150.py exits: stop the resume watcher, run b1rest, then a 1-task VibePromptFile smoke.
LOG=/srv/bench/lscb/data/run150_runner.log
while pgrep -u bench -f "harness/run_150.py" >/dev/null; do sleep 30; done
sleep 90
pgrep -u bench -f "harness/run_150.py" >/dev/null && exec "$0"
W=$(pgrep -f "resume_watch""\.sh"); [ -n "$W" ] && kill $W
echo "$(date -u +%FT%T+00:00) CHAIN: run_150 finished; watcher stopped; starting run_b1rest.py" >> $LOG
su - bench -c "cd /srv/bench/lscb && set -a && . /srv/bench/etc/keys.env && set +a && .venv/bin/python harness/run_b1rest.py >> data/run150_stdout.log 2>&1 < /dev/null"
echo "$(date -u +%FT%T+00:00) CHAIN: run_b1rest.py exited rc=$?; starting sens smoke" >> $LOG
su - bench -c "cd /srv/bench/lscb && set -a && . /srv/bench/etc/keys.env && set +a && .venv/bin/python harness/run_sens.py run150-senssmoke-mistral-vibe cve-2021-46104_function >> data/run150_stdout.log 2>&1 < /dev/null"
echo "$(date -u +%FT%T+00:00) CHAIN: sens smoke exited rc=$?" >> $LOG
