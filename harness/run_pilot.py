import argparse
import csv
import json
import os
import shlex
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path("/home/ubuntu/lscb-bench")
HARNESS = ROOT / "harness"
JOBS = ROOT / "jobs"
DATA = ROOT / "data"
HARBOR = ROOT / ".venv/bin/harbor"
DOCKER_CONFIG = DATA / "docker-anon"
TASKS_FILE = ROOT / "notes/pilot30.json"
DATASET = "last-secure-code-benchmark/last-secure-code-benchmark@v1.0"
BASE_IMAGE_REPO = "lscbench/last-secure-code-bench"
BALANCE_URL = "https://api.deepseek.com/user/balance"
LOG_PATH = DATA / "pilot_runner.log"
BALANCE_PATH = DATA / "deepseek_balance.csv"
SAMPLER_PATH = DATA / "host_samples_pilot_runner.csv"
IMAGE_PULLS_PATH = DATA / "image_pulls_pilot.csv"
PREFIXES_TO_SCRUB = (
    "ANTHROPIC_",
    "CLAUDE_",
    "DEEPSEEK_",
    "MISTRAL_",
    "OPENAI_",
    "VIBE_",
)


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(message: str) -> None:
    line = f"{timestamp()} {message}"
    with LOG_PATH.open("a") as output:
        output.write(line + "\n")
    print(line, flush=True)


def task_names() -> list[str]:
    data = json.loads(TASKS_FILE.read_text())
    tasks = data["tasks"]
    names = [task["task"] for task in tasks]
    if len(names) != 30 or len(set(names)) != 30:
        raise RuntimeError("Expected 30 unique task names in frozen pilot30.json")
    return names


def batches(names: list[str]) -> list[list[str]]:
    return [names[index::3] for index in range(3)]


def command(
    arm: str,
    batch_num: int,
    task_names_for_batch: list[str],
    job_name_override: str | None = None,
) -> tuple[str, list[str]]:
    if arm == "deepseek":
        job_name = f"pilot30-b{batch_num}-deepseek-cc"
        agent_path = "lscb_agents:ClaudeCodeFallbackInstall"
        model = "deepseek-flash"
        agent_args = [
            "--ak",
            "version=2.1.143",
            "--ak",
            "reasoning_effort=max",
            "--allow-agent-host",
            "api.deepseek.com",
        ]
    else:
        job_name = f"pilot30-b{batch_num}-mistral-vibe"
        agent_path = "lscb_agents:VibeNoPluginCache"
        model = "mistral/mistral-large-4-0"
        agent_args = [
            "--ak",
            "version=3.1.3",
            "--ak",
            "thinking=high",
            "--allow-agent-host",
            "api.mistral.ai",
        ]
    if job_name_override is not None:
        job_name = job_name_override
    args = [
        str(HARBOR),
        "run",
        "-d",
        DATASET,
        "--agent",
        agent_path,
        "-m",
        model,
        *agent_args,
    ]
    for task in task_names_for_batch:
        args.extend(["-i", f"last-secure-code-benchmark/{task}"])
    args.extend(
        [
            "-n",
            "3",
            "--max-retries",
            "0",
            "--jobs-dir",
            str(JOBS),
            "--job-name",
            job_name,
        ]
    )
    return job_name, args


def infra_rerun_selection() -> dict[str, list[str]]:
    selected = {"deepseek": [], "mistral": []}
    arm_suffixes = {"deepseek": "deepseek-cc", "mistral": "mistral-vibe"}
    for batch_num in range(1, 4):
        for arm, suffix in arm_suffixes.items():
            job_dir = JOBS / f"pilot30-b{batch_num}-{suffix}"
            if not job_dir.is_dir():
                continue
            for trial_dir in sorted(path for path in job_dir.iterdir() if path.is_dir()):
                result_path = trial_dir / "result.json"
                if not result_path.is_file():
                    continue
                try:
                    result = json.loads(result_path.read_text())
                except (OSError, json.JSONDecodeError):
                    continue
                if not result.get("exception_info"):
                    continue
                execution = result.get("agent_execution")
                execution_started = isinstance(execution, dict) and bool(
                    execution.get("started_at")
                )
                if execution_started:
                    continue
                task_name = str(result.get("task_name") or trial_dir.name).rsplit("/", 1)[-1]
                if task_name not in selected[arm]:
                    selected[arm].append(task_name)
    return selected


def dry_run(names: list[str], start_batch: int, rerun_infra: bool = False) -> None:
    print("DRY RUN: three round-robin batches; no Harbor jobs will be launched.")
    for batch_index, tasks in enumerate(batches(names), start=1):
        if batch_index < start_batch:
            continue
        print(f"\nBatch {batch_index}: {len(tasks)} tasks")
        print("Tasks: " + ", ".join(tasks))
        for arm in ("deepseek", "mistral"):
            job_name, args = command(arm, batch_index, tasks)
            print(f"{job_name}: {shlex.join(args)}")
    if rerun_infra:
        print("\nInfra rerun selection (after successful completion of all three batches):")
        selection = infra_rerun_selection()
        suffixes = {"deepseek": "deepseek-cc", "mistral": "mistral-vibe"}
        any_selected = False
        for arm, tasks in selection.items():
            if not tasks:
                continue
            any_selected = True
            job_name = f"pilot30-rerun1-{suffixes[arm]}"
            print(f"{job_name}: {', '.join(tasks)}")
            _, args = command(arm, 3, tasks, job_name)
            print(f"{job_name} command: {shlex.join(args)}")
        if not any_selected:
            print("No qualifying infrastructure failures found.")


def scrubbed_env(arm: str, deepseek_key: str, mistral_key: str) -> dict[str, str]:
    env = os.environ.copy()
    for name in list(env):
        if name.startswith(PREFIXES_TO_SCRUB) or name == "MAX_THINKING_TOKENS":
            env.pop(name, None)
    env["DOCKER_CONFIG"] = str(DOCKER_CONFIG)
    env["PYTHONPATH"] = str(HARNESS)
    if arm == "deepseek":
        env["ANTHROPIC_API_KEY"] = deepseek_key
        env["ANTHROPIC_BASE_URL"] = "https://api.deepseek.com/anthropic"
    else:
        env["MISTRAL_API_KEY"] = mistral_key
    return env


def read_mistral_key() -> str:
    path = Path("/home/ubuntu/.vibe/.env")
    for line in path.read_text().splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip().removeprefix("export ").strip() == "MISTRAL_API_KEY":
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            if value:
                return value
    raise RuntimeError("MISTRAL_API_KEY missing or empty in /home/ubuntu/.vibe/.env")


def read_balance(deepseek_key: str) -> float:
    request = urllib.request.Request(
        BALANCE_URL,
        headers={"Authorization": f"Bearer {deepseek_key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read())
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read DeepSeek balance ({type(exc).__name__})") from exc
    if payload.get("error"):
        raise RuntimeError("DeepSeek balance endpoint returned an error")
    return float(payload["balance_infos"][0]["total_balance"])


def record_balance(label: str, balance: float) -> None:
    new_file = not BALANCE_PATH.exists()
    with BALANCE_PATH.open("a", newline="") as output:
        writer = csv.writer(output)
        if new_file:
            writer.writerow(("ts_utc", "label", "total_balance"))
        writer.writerow((timestamp(), label, f"{balance:.2f}"))


def available_disk_gb() -> float:
    stat = os.statvfs(ROOT)
    return stat.f_bavail * stat.f_frsize / 1_000_000_000


def record_image_pull(
    batch_num: int | str,
    task: str,
    image: str,
    size_bytes: int,
    pull_seconds: float,
    status: str,
) -> None:
    new_file = not IMAGE_PULLS_PATH.exists() or IMAGE_PULLS_PATH.stat().st_size == 0
    with IMAGE_PULLS_PATH.open("a", newline="") as output:
        writer = csv.writer(output)
        if new_file:
            writer.writerow(("batch", "task", "image", "bytes", "pull_s", "status", "ts_utc"))
        writer.writerow(
            (
                batch_num,
                task,
                image,
                size_bytes,
                f"{pull_seconds:.3f}",
                status,
                timestamp(),
            )
        )


def pull_batch_images(batch_num: int | str, tasks: list[str]) -> bool:
    batch_label = f"batch{batch_num}" if isinstance(batch_num, int) else batch_num
    pull_env = os.environ.copy()
    for name in list(pull_env):
        if name.startswith(PREFIXES_TO_SCRUB) or name == "MAX_THINKING_TOKENS":
            pull_env.pop(name, None)
    pull_env["DOCKER_CONFIG"] = str(DOCKER_CONFIG)

    total_started = time.monotonic()
    total_bytes = 0
    retry_delays = (30, 60, 120)
    for task in tasks:
        image = f"{BASE_IMAGE_REPO}:{task}_lscb"
        for attempt in range(1, 5):
            pull_started = time.monotonic()
            status = "ok"
            size_bytes = 0
            detail = ""
            try:
                result = subprocess.run(
                    ["docker", "pull", image],
                    env=pull_env,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=1800,
                )
                if result.returncode != 0:
                    status = "failed"
                    detail = (result.stderr or result.stdout or "docker pull failed").strip()
                else:
                    inspected = subprocess.run(
                        ["docker", "image", "inspect", "--format", "{{.Size}}", image],
                        env=pull_env,
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=30,
                    )
                    if inspected.returncode != 0:
                        status = "failed"
                        detail = (
                            inspected.stderr or inspected.stdout or "image inspect failed"
                        ).strip()
                    else:
                        size_bytes = int(inspected.stdout.strip())
            except subprocess.TimeoutExpired:
                status = "failed"
                detail = "docker pull timed out after 1800 seconds"
            except Exception as exc:
                status = "failed"
                detail = f"{type(exc).__name__}: {exc}"

            pull_seconds = time.monotonic() - pull_started
            if status == "ok":
                record_image_pull(
                    batch_num,
                    task,
                    image,
                    size_bytes,
                    pull_seconds,
                    "ok",
                )
                log(
                    f"{batch_label} pull {task} attempt={attempt}/4: image={image} "
                    f"bytes={size_bytes} pull_s={pull_seconds:.3f} status=ok"
                )
                total_bytes += size_bytes
                break

            retrying = attempt < 4
            record_image_pull(
                batch_num,
                task,
                image,
                0,
                pull_seconds,
                "retry_failed",
            )
            if detail:
                log(
                    f"{batch_label} pull {task} attempt={attempt}/4 failed: "
                    f"{detail[-600:].replace(chr(10), ' | ')}"
                )
            if not retrying:
                log(
                    f"{batch_label} pull {task} exhausted 4 attempts; "
                    "aborting batch"
                )
                total_seconds = time.monotonic() - total_started
                log(
                    f"{batch_label} pull total before failure: bytes={total_bytes} "
                    f"pull_s={total_seconds:.3f}"
                )
                return False

            rate_limited = "429" in detail or "toomanyrequests" in detail.casefold()
            delay = 900 if rate_limited else retry_delays[attempt - 1]
            reason = "rate limit" if rate_limited else "transient failure"
            log(
                f"{batch_label} pull {task} status=retry_failed; "
                f"retrying in {delay}s after {reason}"
            )
            time.sleep(delay)

    total_seconds = time.monotonic() - total_started
    log(
        f"{batch_label} pull total: images={len(tasks)} bytes={total_bytes} "
        f"pull_s={total_seconds:.3f}"
    )
    return True


def df_line() -> str:
    result = subprocess.run(
        ["df", "-h", "/"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return result.stdout.splitlines()[-1]


def log_df(label: str) -> None:
    log(f"{label}: {df_line()}")


def key_prefix_hits(job_dir: Path, prefixes: list[bytes]) -> list[Path]:
    hits = []
    if not job_dir.exists():
        return hits
    for path in job_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            content = path.read_bytes()
        except OSError:
            continue
        if any(prefix in content for prefix in prefixes):
            hits.append(path)
    return hits


def stop_jobs(processes: dict[str, subprocess.Popen]) -> None:
    for process in processes.values():
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGINT)
            except ProcessLookupError:
                pass


def finish_jobs(processes: dict[str, subprocess.Popen]) -> None:
    for process in processes.values():
        if process.poll() is None:
            try:
                process.wait(timeout=120)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=5)


def scan_finished_jobs(
    processes: dict[str, subprocess.Popen],
    audited: set[str],
    prefixes: list[bytes],
) -> bool:
    found_hit = False
    for name, process in processes.items():
        if name in audited or process.poll() is None:
            continue
        hits = key_prefix_hits(JOBS / name, prefixes)
        audited.add(name)
        if hits:
            found_hit = True
            for path in hits:
                log(f"STOP: key-prefix match in job file {path}")
        else:
            log(f"{name} prefix scan: zero hits")
    return found_hit


def batch_container_ids(tasks: list[str]) -> list[str]:
    result = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.ID}}\t{{.Names}}"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    prefixes = tuple(f"{task}__".casefold() for task in tasks)
    return [
        fields[0]
        for line in result.stdout.splitlines()
        if len(fields := line.split("\t", 1)) == 2
        and fields[1].casefold().startswith(prefixes)
    ]


def remove_batch_containers(tasks: list[str], phase: str) -> bool:
    for attempt in (1, 2):
        try:
            container_ids = batch_container_ids(tasks)
        except Exception as exc:
            log(f"{phase}: could not list batch containers ({type(exc).__name__})")
            return False
        if not container_ids:
            if attempt == 1:
                log(f"{phase}: no remaining batch containers")
            return True
        log(
            f"{phase}: docker rm -f attempt {attempt}: "
            + ", ".join(container_ids)
        )
        result = subprocess.run(
            ["docker", "rm", "-f", *container_ids],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        if result.stdout.strip():
            log("docker rm -f: " + result.stdout.strip().replace("\n", " | "))
        if result.stderr.strip():
            log("docker rm -f stderr: " + result.stderr.strip().replace("\n", " | "))
        try:
            remaining = batch_container_ids(tasks)
        except Exception as exc:
            log(f"{phase}: could not verify container removal ({type(exc).__name__})")
            return False
        if not remaining:
            if result.returncode != 0:
                log(f"{phase}: docker rm returned {result.returncode}, but no batch containers remain")
            return True
        log(f"{phase}: containers remain after attempt {attempt}: " + ", ".join(remaining))
    return False


def batch_image_refs(tasks: list[str]) -> list[str]:
    result = subprocess.run(
        ["docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}}"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    refs = set()
    base_refs = {f"{BASE_IMAGE_REPO}:{task}_lscb" for task in tasks}
    for image in result.stdout.splitlines():
        repo, separator, _ = image.rpartition(":")
        if not separator:
            continue
        if image in base_refs or any(
            repo.startswith(f"{task}__") and repo.endswith("__env-main")
            for task in tasks
        ):
            refs.add(image)
    return sorted(refs)


def remove_batch_images(tasks: list[str]) -> None:
    cleanup_error = not remove_batch_containers(tasks, "before batch image removal")
    refs = batch_image_refs(tasks)
    if refs:
        for attempt in (1, 2):
            log(
                f"Removing batch images (attempt {attempt}): "
                + ", ".join(refs)
            )
            result = subprocess.run(
                ["docker", "image", "rm", *refs],
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )
            if result.stdout.strip():
                log("docker image rm: " + result.stdout.strip().replace("\n", " | "))
            if result.stderr.strip():
                log("docker image rm stderr: " + result.stderr.strip().replace("\n", " | "))
            remaining = batch_image_refs(tasks)
            if not remaining:
                refs = []
                if result.returncode != 0:
                    log(
                        f"docker image rm returned {result.returncode}, "
                        "but no batch images remain"
                    )
                break
            if attempt == 1:
                log("Batch image removal incomplete; retrying after container removal")
                if not remove_batch_containers(tasks, "image removal retry"):
                    cleanup_error = True
                refs = remaining
            else:
                refs = remaining
        if refs:
            cleanup_error = True
            log("Batch images remain after retry: " + ", ".join(refs))
    else:
        log("No batch images matched for removal")

    result = subprocess.run(
        ["docker", "builder", "prune", "-af"],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    if result.stdout.strip():
        summary = next(
            (
                line.strip()
                for line in reversed(result.stdout.splitlines())
                if "reclaimed" in line.lower()
            ),
            "builder prune completed",
        )
        log(summary)
    if result.stderr.strip():
        log("docker builder prune stderr: " + result.stderr.strip().replace("\n", " | "))
    if result.returncode != 0:
        cleanup_error = True
        log(f"docker builder prune -af failed with status {result.returncode}")
    if cleanup_error:
        raise RuntimeError("Batch cleanup failed; see cleanup log entries")


def mid_batch_cleanup(
    batch_num: int,
    logger=log,
    job_names: list[str] | None = None,
    label: str | None = None,
) -> None:
    batch_label = label or f"batch{batch_num}"
    if job_names is None:
        job_names = [
            f"pilot30-b{batch_num}-deepseek-cc",
            f"pilot30-b{batch_num}-mistral-vibe",
        ]
    disk_before = available_disk_gb()
    logger(
        f"{batch_label} mid-batch cleanup start: "
        f"disk_available_gb={disk_before:.3f}"
    )
    try:
        result = subprocess.run(
            ["docker", "builder", "prune", "-f"],
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        summary = next(
            (line.strip() for line in reversed(result.stdout.splitlines()) if line.strip()),
            "no output",
        )
        disk_after = available_disk_gb()
        logger(
            f"docker builder prune -f: status={result.returncode} "
            f"freed_gb={max(0.0, disk_after - disk_before):.3f} detail={summary}"
        )
        if result.stderr.strip():
            logger("docker builder prune -f stderr: " + result.stderr.strip().replace("\n", " | "))
    except Exception as exc:
        logger(f"docker builder prune -f failed: {type(exc).__name__}; freed_gb=0.000")

    for job_name in job_names:
        job_dir = JOBS / job_name
        if not job_dir.is_dir():
            continue
        for trial_dir in sorted(path for path in job_dir.iterdir() if path.is_dir()):
            if not (trial_dir / "result.json").is_file():
                continue
            image = f"{trial_dir.name.lower()}__env-main:latest"
            try:
                inspected = subprocess.run(
                    ["docker", "image", "inspect", "--format", "{{.Id}}", image],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=30,
                )
            except Exception as exc:
                logger(
                    f"completed trial image inspect failed: image={image} "
                    f"error={type(exc).__name__}; freed_gb=0.000"
                )
                continue
            if inspected.returncode != 0:
                logger(f"completed trial image absent: image={image}; freed_gb=0.000")
                continue

            image_id = inspected.stdout.strip()
            try:
                containers = subprocess.run(
                    [
                        "docker",
                        "ps",
                        "-a",
                        "--filter",
                        f"ancestor={image_id}",
                        "--format",
                        "{{.ID}}",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=30,
                )
            except Exception as exc:
                logger(
                    f"completed trial image container check failed: image={image} "
                    f"error={type(exc).__name__}; freed_gb=0.000"
                )
                continue
            if containers.returncode != 0:
                logger(
                    f"completed trial image container check failed: image={image} "
                    f"status={containers.returncode}; freed_gb=0.000"
                )
                continue
            container_ids = containers.stdout.split()
            if container_ids:
                logger(
                    f"completed trial image in use; skipped: image={image} "
                    f"containers={','.join(container_ids)}; freed_gb=0.000"
                )
                continue

            disk_before_remove = available_disk_gb()
            try:
                removed = subprocess.run(
                    ["docker", "image", "rm", image],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=120,
                )
                disk_after_remove = available_disk_gb()
                detail = (removed.stderr or removed.stdout or "no output").strip()
                logger(
                    f"completed trial image removal: image={image} "
                    f"status={removed.returncode} "
                    f"freed_gb={max(0.0, disk_after_remove - disk_before_remove):.3f} "
                    f"detail={detail[-400:].replace(chr(10), ' | ')}"
                )
            except Exception as exc:
                logger(
                    f"completed trial image removal failed: image={image} "
                    f"error={type(exc).__name__}; freed_gb=0.000"
                )

    logger(
        f"{batch_label} mid-batch cleanup end: "
        f"disk_available_gb={available_disk_gb():.3f}"
    )


def run_batch(
    batch_num: int,
    tasks: list[str],
    deepseek_key: str,
    mistral_key: str,
    prefixes: list[bytes],
    sampler: subprocess.Popen,
    *,
    arms: tuple[str, ...] = ("deepseek", "mistral"),
    tasks_by_arm: dict[str, list[str]] | None = None,
    job_name_overrides: dict[str, str] | None = None,
    stage_label: str | None = None,
    pull_batch_label: int | str | None = None,
    cleanup_job_names: list[str] | None = None,
) -> int:
    batch_label = stage_label or f"batch{batch_num}"
    pull_label = batch_num if pull_batch_label is None else pull_batch_label
    log(f"{batch_label} start")
    log_df(f"{batch_label} df before")
    processes: dict[str, subprocess.Popen] = {}
    audited: set[str] = set()
    failure: str | None = None
    cleanup_needed = False
    try:
        balance = read_balance(deepseek_key)
        record_balance(f"{batch_label}-boundary-start", balance)
        available = available_disk_gb()
        log(
            f"{batch_label} prelaunch guard: disk_available_gb={available:.3f}, "
            f"deepseek_balance={balance:.2f}"
        )
        if available < 8 or balance < 2:
            failure = f"{batch_label} guard tripped before launch"
            log(failure)
        if failure is None:
            cleanup_needed = True
            if not pull_batch_images(pull_label, tasks):
                failure = f"{batch_label} base-image pull failed"
                log(failure)

        if failure is None:
            if sampler.poll() is not None:
                failure = "host sampler exited before batch jobs started"
                log(failure)
            else:
                balance = read_balance(deepseek_key)
                record_balance(f"{batch_label}-prelaunch", balance)
                available = available_disk_gb()
                log(
                    f"{batch_label} post-pull guard: disk_available_gb={available:.3f}, "
                    f"deepseek_balance={balance:.2f}"
                )
                if available < 8 or balance < 2:
                    failure = f"{batch_label} guard tripped after pulls"
                    log(failure)

        if failure is None:
            for arm in arms:
                arm_tasks = tasks_by_arm.get(arm, tasks) if tasks_by_arm else tasks
                job_name_override = (
                    job_name_overrides.get(arm) if job_name_overrides else None
                )
                name, args = command(
                    arm,
                    batch_num,
                    arm_tasks,
                    job_name_override,
                )
                log(f"command {name}: {shlex.join(args)}")
                process = subprocess.Popen(
                    args,
                    env=scrubbed_env(arm, deepseek_key, mistral_key),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                processes[name] = process
                log(f"started {name} pid={process.pid}")

            next_guard = time.monotonic() + 60
            while any(process.poll() is None for process in processes.values()):
                if sampler.poll() is not None:
                    failure = "host sampler exited while pilot batch was running"
                    stop_jobs(processes)
                    break
                if time.monotonic() >= next_guard:
                    available = available_disk_gb()
                    balance = read_balance(deepseek_key)
                    record_balance(f"{batch_label}-guard", balance)
                    log(
                        f"{batch_label} 60-second guard: disk_available_gb={available:.3f}, "
                        f"deepseek_balance={balance:.2f}"
                    )
                    if batch_num in (2, 3) and available < 30:
                        log(f"{batch_label} disk below 30 GB; running mid-batch cleanup")
                        mid_batch_cleanup(
                            batch_num,
                            job_names=cleanup_job_names,
                            label=batch_label,
                        )
                        available = available_disk_gb()
                        log(
                            f"{batch_label} 60-second guard after cleanup: "
                            f"disk_available_gb={available:.3f}, "
                            f"deepseek_balance={balance:.2f}"
                        )
                    if available < 8 or balance < 2:
                        failure = f"{batch_label} guard tripped; sending SIGINT"
                        log(failure)
                        stop_jobs(processes)
                        break
                    next_guard = time.monotonic() + 60
                if scan_finished_jobs(processes, audited, prefixes):
                    failure = f"{batch_label} key-prefix hit"
                    stop_jobs(processes)
                    break
                time.sleep(1)
    except Exception as exc:
        failure = f"{batch_label} failed ({type(exc).__name__})"
        log(failure)
        stop_jobs(processes)
    finally:
        finish_jobs(processes)
        if scan_finished_jobs(processes, audited, prefixes):
            failure = f"{batch_label} key-prefix hit"
        if cleanup_needed:
            log_df(f"{batch_label} df before cleanup")
            try:
                remove_batch_images(tasks)
            except Exception as exc:
                failure = f"{batch_label} image cleanup failed ({type(exc).__name__})"
                log(failure)
            log_df(f"{batch_label} df after cleanup")
        else:
            log(f"{batch_label} had no pulled batch images; no image cleanup needed")
        try:
            balance = read_balance(deepseek_key)
            record_balance(f"{batch_label}-boundary-end", balance)
            log(f"{batch_label} boundary balance: {balance:.2f}")
        except Exception as exc:
            failure = f"{batch_label} balance check failed ({type(exc).__name__})"
            log(failure)

    if failure is None and any(process.returncode != 0 for process in processes.values()):
        failure = "one or more Harbor jobs exited non-zero"
    if failure:
        log(f"{batch_label} aborted: {failure}")
        return 1
    log(f"{batch_label} end")
    return 0


def run_infra_rerun_stage(
    selection: dict[str, list[str]],
    deepseek_key: str,
    mistral_key: str,
    prefixes: list[bytes],
    sampler: subprocess.Popen,
) -> int:
    suffixes = {"deepseek": "deepseek-cc", "mistral": "mistral-vibe"}
    arms = tuple(arm for arm in ("deepseek", "mistral") if selection[arm])
    if not arms:
        log("rerun1: no qualifying infrastructure failures found")
        return 0

    job_name_overrides = {
        arm: f"pilot30-rerun1-{suffixes[arm]}"
        for arm in arms
    }
    for arm in arms:
        log(
            f"rerun1 selection {job_name_overrides[arm]}: "
            + ", ".join(selection[arm])
        )
    tasks = list(
        dict.fromkeys(task for arm in arms for task in selection[arm])
    )
    return run_batch(
        3,
        tasks,
        deepseek_key,
        mistral_key,
        prefixes,
        sampler,
        arms=arms,
        tasks_by_arm=selection,
        job_name_overrides=job_name_overrides,
        stage_label="rerun1",
        pull_batch_label="rerun1",
        cleanup_job_names=list(job_name_overrides.values()),
    )


def run(start_batch: int, rerun_infra: bool = False) -> int:
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    if not deepseek_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not available in the host environment")
    log(f"pilot runner pid={os.getpid()} start_batch={start_batch}")
    mistral_key = read_mistral_key()
    prefixes = [deepseek_key[:12].encode(), mistral_key[:12].encode()]
    if any(len(prefix) < 12 for prefix in prefixes):
        raise RuntimeError("An API key is shorter than the required audit prefix")

    sampler_env = os.environ.copy()
    for name in list(sampler_env):
        if name.startswith(PREFIXES_TO_SCRUB) or name == "MAX_THINKING_TOKENS":
            sampler_env.pop(name, None)
    sampler_env["DOCKER_CONFIG"] = str(DOCKER_CONFIG)
    sampler = subprocess.Popen(
        [sys.executable, str(DATA / "host_sampler.py"), str(SAMPLER_PATH)],
        env=sampler_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    log(f"host sampler started pid={sampler.pid} output={SAMPLER_PATH}")
    try:
        for _ in range(200):
            if sampler.poll() is not None:
                raise RuntimeError("Pilot host sampler exited during startup")
            if SAMPLER_PATH.exists() and len(SAMPLER_PATH.read_text().splitlines()) > 1:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("Pilot host sampler did not record its first sample")

        names = task_names()
        grouped = batches(names)
        for batch_num in range(start_batch, 4):
            status = run_batch(
                batch_num,
                grouped[batch_num - 1],
                deepseek_key,
                mistral_key,
                prefixes,
                sampler,
            )
            if status != 0:
                return status
        if rerun_infra:
            selection = infra_rerun_selection()
            return run_infra_rerun_stage(
                selection,
                deepseek_key,
                mistral_key,
                prefixes,
                sampler,
            )
        return 0
    finally:
        if sampler.poll() is None:
            sampler.terminate()
            try:
                sampler.wait(timeout=10)
            except subprocess.TimeoutExpired:
                sampler.kill()
                sampler.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-batch", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rerun-infra", action="store_true")
    args = parser.parse_args()
    names = task_names()
    if args.dry_run:
        dry_run(names, args.start_batch, args.rerun_infra)
        return 0
    return run(args.start_batch, args.rerun_infra)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"Pilot runner error: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
