import csv
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


output_path = Path(sys.argv[1])
columns = ("ts", "loadavg1", "mem_used_gb", "disk_free_gb", "n_containers")
new_file = not output_path.exists()

with output_path.open("a", newline="") as output:
    writer = csv.writer(output)
    if new_file:
        writer.writerow(columns)
        output.flush()

    while True:
        loadavg1 = float(Path("/proc/loadavg").read_text().split()[0])
        memory = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith(("MemTotal:", "MemAvailable:")):
                key, value, *_ = line.split()
                memory[key.rstrip(":")] = int(value)
        mem_used_gb = (memory["MemTotal"] - memory["MemAvailable"]) * 1024 / 1e9
        disk_free_gb = shutil.disk_usage("/srv/bench/lscb").free / 1e9
        containers = subprocess.run(
            ["docker", "ps", "-q"],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        ).stdout.splitlines()
        writer.writerow(
            (
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                f"{loadavg1:.2f}",
                f"{mem_used_gb:.3f}",
                f"{disk_free_gb:.3f}",
                len(containers),
            )
        )
        output.flush()
        time.sleep(30)
