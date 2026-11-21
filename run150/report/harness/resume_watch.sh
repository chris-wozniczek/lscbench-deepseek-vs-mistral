#!/bin/bash
# Relaunch run_150.py at the next batch if it aborted on a batch image-cleanup timeout.
LOG=/srv/bench/lscb/data/run150_runner.log
D=/srv/bench/lscb/data
export DOCKER_HOST=unix:///run/bench-docker.sock
while true; do
  if ! pgrep -u bench -f "harness/run_150.py" >/dev/null; then
    sleep 20
    pgrep -u bench -f "harness/run_150.py" >/dev/null && continue
    last=$(grep -E "aborted: batch[0-9]+ image cleanup failed" "$LOG" | tail -1)
    n=$(echo "$last" | sed -E 's/.*aborted: batch([0-9]+).*/\1/')
    [ -z "$n" ] && exit 0
    [ -f "$D/resumed_$n" ] && exit 0
    [ "$n" -ge 8 ] && exit 0
    touch "$D/resumed_$n"
    timeout 1200 docker image prune -af >/dev/null 2>&1
    timeout 1200 docker builder prune -af >/dev/null 2>&1
    echo "$(date -u +%FT%T+00:00) WATCHER: runner aborted after batch$n (image cleanup timeout); images pruned; relaunching --start-batch $((n+1))" >> "$LOG"
    su - bench -c "cd /srv/bench/lscb && set -a && . /srv/bench/etc/keys.env && set +a && setsid nohup .venv/bin/python harness/run_150.py --start-batch $((n+1)) >> data/run150_stdout.log 2>&1 < /dev/null &"
    sleep 120
  fi
  sleep 60
done
