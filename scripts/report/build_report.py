#!/usr/bin/env python3
import csv
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "report"
DATA = REPORT / "data"
CHARTS = REPORT / "charts"
TRIALS_PATH = DATA / "trials.csv"
SUMMARY_PATH = DATA / "summary.json"
MANIFEST_PATH = ROOT / "notes" / "pilot30.json"
BALANCE_PATH = ROOT / "data" / "deepseek_balance.csv"
RUNNER_LOG_PATH = ROOT / "data" / "pilot_runner.log"
RERUN1_LOG_PATH = ROOT / "data" / "rerun1_runner.log"
RERUN2_LOG_PATH = ROOT / "data" / "rerun2_runner.log"
PULLS_PATH = ROOT / "data" / "image_pulls_pilot.csv"
COMMANDS_PATH = ROOT / "notes" / "pilot30-commands.md"
VOID_TRIALS_PATH = ROOT / "notes" / "void_trials.json"

ARM_ORDER = ("deepseek-cc", "mistral-vibe")
ARM_LABELS = {
    "deepseek-cc": "DeepSeek Flash / Claude Code",
    "mistral-vibe": "Mistral Large 4 / Vibe",
}
ARM_SHORT = {"deepseek-cc": "DeepSeek", "mistral-vibe": "Mistral"}
ARM_COLORS = {"deepseek-cc": "#4C6EF5", "mistral-vibe": "#F76707"}
SCORE_COLUMNS = (
    ("functional", "Functional"),
    ("secure", "Secure"),
    ("reward", "Reward"),
)
TIME_COLUMNS = (
    ("environment_setup_s", "Environment setup"),
    ("agent_setup_s", "Agent setup"),
    ("agent_execution_s", "Agent execution"),
    ("verifier_s", "Verifier"),
    ("trial_total_s", "Trial total"),
)
Z_95 = 1.96

SECRET_RE = re.compile(
    r"(?i)\b(?:sk-[A-Za-z0-9_-]{10,}|"
    r"(?:api[_ -]?key|access[_ -]?token|bearer)\s*[:= ]\s*[^\s,;]+)\b"
)
PATH_RE = re.compile(
    r"(?<![A-Za-z0-9])/(?:[A-Za-z0-9._~-]+/)+[^\s\"'<>|;,)]*"
    r"|(?<![A-Za-z0-9])/(?:home|root|tmp|var|etc|usr|opt|mnt|srv|tests|logs|app|data|proc|sys|run|dev|private|Users|Volumes)(?=$|[\s\"'<>|;,])"
)
HOST_RE = re.compile(r"\b(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\b")
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def as_number(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def as_int(value: object) -> int | None:
    number = as_number(value)
    return int(number) if number is not None else None


def flag(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def clean_text(value: object) -> str:
    text = ("" if value is None else str(value)).replace("\r", " ").replace("\n", " ").strip()
    endpoints = (
        "https://api.deepseek.com/anthropic",
        "https://api.mistral.ai",
    )
    protected = {}
    for index, endpoint in enumerate(endpoints):
        marker = f"__PUBLIC_ENDPOINT_{index}__"
        text = text.replace(endpoint, marker)
        protected[marker] = endpoint
    text = SECRET_RE.sub("[redacted]", text)
    text = PATH_RE.sub("[path]", text)
    text = HOST_RE.sub("[host]", text)
    text = IP_RE.sub("[host]", text)
    for marker, endpoint in protected.items():
        text = text.replace(marker, endpoint)
    return text


def md_cell(value: object) -> str:
    return clean_text(value).replace("|", r"\|").replace("`", r"\`")


def markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    lines = [
        "| " + " | ".join(md_cell(item) for item in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend(
        "| " + " | ".join(md_cell(item) for item in row) + " |"
        for row in rows
    )
    return "\n".join(lines)


def format_int(value: int | float | None) -> str:
    if value is None:
        return "—"
    return f"{int(value):,}"


def format_seconds(value: float | None) -> str:
    return "—" if value is None else f"{value:,.1f}"


def format_minutes(value: float | None) -> str:
    return "—" if value is None else f"{value / 60:.1f}"


def format_usd(value: float | None, digits: int = 4) -> str:
    return "—" if value is None else f"${value:,.{digits}f}"


def wilson_interval(successes: int, n: int, z: float = Z_95) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 0.0)
    p = successes / n
    z2 = z * z
    denominator = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denominator
    margin = z * math.sqrt((p * (1 - p) / n) + (z2 / (4 * n * n))) / denominator
    return (max(0.0, center - margin), min(1.0, center + margin))


def format_rate(rows: list[dict[str, str]], column: str) -> str:
    n = len(rows)
    if n == 0:
        return "0/0 (n/a)"
    successes = sum(as_number(row.get(column)) == 1 for row in rows)
    low, high = wilson_interval(successes, n)
    return (
        f"{successes}/{n} ({100 * successes / n:.1f}%, "
        f"CI {100 * low:.1f}–{100 * high:.1f}%)"
    )


def nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil((percentile / 100) * len(ordered)))
    return ordered[rank - 1]


def binomial_cdf(k: int, n: int) -> float:
    if n <= 0:
        return 1.0
    return sum(math.comb(n, i) for i in range(k + 1)) / (2**n)


def mcnemar_exact(b: int, c: int) -> float:
    discordant = b + c
    if discordant == 0:
        return 1.0
    return min(1.0, 2 * binomial_cdf(min(b, c), discordant))


def score_pass(row: dict[str, str] | None, column: str) -> bool:
    return row is not None and as_number(row.get(column)) == 1


def group_by_arm(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped = {arm: [] for arm in ARM_ORDER}
    for row in rows:
        if row.get("arm") in grouped:
            grouped[row["arm"]].append(row)
    return grouped


def official_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if flag(row.get("official"))]


def official_index(rows: list[dict[str, str]]) -> dict[str, dict[str, dict[str, str]]]:
    indexed: dict[str, dict[str, dict[str, str]]] = {arm: {} for arm in ARM_ORDER}
    for row in rows:
        arm = row.get("arm", "")
        task = row.get("task", "")
        if arm in indexed and task:
            indexed[arm][task] = row
    return indexed


def ratio_text(harbor_total: float, computed_total: float) -> str:
    if computed_total <= 0:
        return "not available"
    return f"about {harbor_total / computed_total:.1f}×"


def exception_display_message(row: dict[str, str]) -> str:
    raw = row.get("exception_msg") or row.get("vibe_error") or ""
    first_line = raw.splitlines()[0].strip() if raw.splitlines() else ""
    if re.search(r"docker\s+compose|compose command failed", first_line, re.I):
        return clean_text(first_line[:120]) or "—"
    command_failure = re.match(r"Command failed \(exit (\d+)\):", first_line)
    if command_failure:
        return f"Command failed (exit {command_failure.group(1)}): agent CLI"
    return clean_text(first_line) or "—"


def vulnerability_display(row: dict[str, str]) -> str:
    message = (row.get("vulnerability_msg") or "").strip()
    if message:
        return clean_text(message[:200]) or "—"
    failed_tests = (row.get("failed_vuln_tests") or "").strip()
    test_names = [name.strip() for name in failed_tests.split(";") if name.strip()]
    if test_names:
        return clean_text("tests: " + "; ".join(test_names[:2])[:200]) or "—"
    return clean_text(row.get("vsb_summary", "")) or "—"


def rerun_outcome(row: dict[str, str]) -> str:
    scores = (
        f"functional {row.get('functional') or '—'}, "
        f"secure {row.get('secure') or '—'}, "
        f"reward {row.get('reward') or '—'}"
    )
    exception = row.get("exception_type", "").strip()
    return f"{scores}; exception {exception}" if exception else scores


def void_rerun_rows(
    void_data: dict[str, object],
    rows: list[dict[str, str]],
) -> list[list[object]]:
    void_rows = void_data.get("void", [])
    result = []
    for void_row in void_rows if isinstance(void_rows, list) else []:
        if not isinstance(void_row, dict):
            continue
        original = next(
            (
                row
                for row in rows
                if row.get("job") == void_row.get("job")
                and row.get("trial") == void_row.get("trial")
            ),
            None,
        )
        candidates = []
        if original is not None:
            candidates = [
                row
                for row in rows
                if row.get("arm") == original.get("arm")
                and row.get("task") == original.get("task")
                and row.get("job", "").startswith("pilot30-rerun")
                and flag(row.get("official"))
            ]
        replacement = candidates[-1] if candidates else None
        result.append(
            [
                void_row.get("job", ""),
                void_row.get("trial", ""),
                void_row.get("reason", ""),
                f"{replacement['job']} / {replacement['trial']}" if replacement else "—",
                rerun_outcome(replacement) if replacement else "No official replacement row found",
            ]
        )
    return result


def parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def timestamp_label(value: datetime | None) -> str:
    if value is None:
        return "unknown"
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def batch_intervals(log_text: str) -> dict[int, tuple[datetime | None, datetime | None, str]]:
    start_re = re.compile(
        r"^(\S+)\s+batch([1-3]) start$"
    )
    close_re = re.compile(
        r"^(\S+)\s+batch([1-3]) (end|aborted)(?::.*)?$"
    )
    starts: dict[int, list[datetime]] = defaultdict(list)
    closes: dict[int, list[tuple[datetime, str]]] = defaultdict(list)
    for line in log_text.splitlines():
        start_match = start_re.match(line)
        if start_match:
            stamp = parse_timestamp(start_match.group(1))
            if stamp is not None:
                starts[int(start_match.group(2))].append(stamp)
            continue
        close_match = close_re.match(line)
        if close_match:
            stamp = parse_timestamp(close_match.group(1))
            if stamp is not None:
                closes[int(close_match.group(2))].append(
                    (stamp, close_match.group(3))
                )

    intervals = {}
    for batch_num in (1, 2, 3):
        if not starts[batch_num]:
            intervals[batch_num] = (None, None, "not started")
            continue
        start = starts[batch_num][-1]
        close = next(
            (item for item in closes[batch_num] if item[0] > start),
            None,
        )
        if close is None:
            intervals[batch_num] = (start, None, "in progress")
        else:
            intervals[batch_num] = (start, close[0], close[1])
    return intervals


def duration_text(start: datetime | None, end: datetime | None) -> str:
    if start is None:
        return "—"
    if end is None:
        return "in progress"
    seconds = max(0, int((end - start).total_seconds()))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    return f"{minutes}m {seconds:02d}s"


def make_csv(path: Path, headers: list[str], rows: list[list[object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)


def plot_rates(official_by_arm: dict[str, list[dict[str, str]]]) -> None:
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    x = list(range(len(SCORE_COLUMNS)))
    width = 0.34
    for arm_index, arm in enumerate(ARM_ORDER):
        rates = []
        lower = []
        upper = []
        for column, _ in SCORE_COLUMNS:
            rows = official_by_arm[arm]
            n = len(rows)
            successes = sum(as_number(row.get(column)) == 1 for row in rows)
            rate = successes / n if n else 0
            low, high = wilson_interval(successes, n)
            rates.append(rate)
            lower.append(rate - low)
            upper.append(high - rate)
        positions = [value + (arm_index - 0.5) * width for value in x]
        ax.bar(
            positions,
            rates,
            width=width,
            color=ARM_COLORS[arm],
            label=ARM_SHORT[arm],
            zorder=2,
        )
        ax.errorbar(
            positions,
            rates,
            yerr=[lower, upper],
            fmt="none",
            ecolor="#212529",
            capsize=3,
            linewidth=1,
            zorder=3,
        )
        for pos, rate in zip(positions, rates):
            ax.text(pos, rate + 0.035, f"{rate:.0%}", ha="center", va="bottom", fontsize=8)
    ns = [len(official_by_arm[arm]) for arm in ARM_ORDER]
    ax.set_title(
        f"Functional, secure, and reward rates with Wilson 95% CI "
        f"(n={ns[0]} DeepSeek, n={ns[1]} Mistral)"
    )
    ax.set_xticks(x, [label for _, label in SCORE_COLUMNS])
    ax.set_ylim(0, 1.13)
    ax.set_ylabel("Rate")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda value, _: f"{value:.0%}"))
    ax.grid(axis="y", alpha=0.25, zorder=0)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(
        CHARTS / "rates_ci.svg",
        format="svg",
        bbox_inches="tight",
        metadata={"Title": ax.get_title(), "Creator": "LSCBench report builder"},
    )
    plt.close(fig)


def grouped_reward_counts(
    manifest: list[dict[str, object]],
    index: dict[str, dict[str, dict[str, str]]],
    field: str,
) -> list[tuple[str, dict[str, tuple[int, int]]]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for task in manifest:
        groups[str(task.get(field) or "unknown")].append(str(task["task"]))
    result = []
    for group in sorted(groups, key=lambda value: value.lower()):
        arm_counts = {}
        for arm in ARM_ORDER:
            members = [
                index[arm][task]
                for task in groups[group]
                if task in index[arm]
            ]
            passes = sum(score_pass(row, "reward") for row in members)
            arm_counts[arm] = (passes, len(members))
        result.append((group, arm_counts))
    return result


def plot_reward_by_language(
    groups: list[tuple[str, dict[str, tuple[int, int]]]],
    n_by_arm: dict[str, int],
) -> None:
    fig, ax = plt.subplots(figsize=(10, 5.4))
    x = list(range(len(groups)))
    width = 0.36
    for arm_index, arm in enumerate(ARM_ORDER):
        values = []
        positions = [value + (arm_index - 0.5) * width for value in x]
        for _, counts in groups:
            passes, n = counts[arm]
            values.append(passes / n if n else 0)
        bars = ax.bar(
            positions,
            values,
            width=width,
            color=ARM_COLORS[arm],
            label=ARM_SHORT[arm],
            zorder=2,
        )
        for bar, (_, counts) in zip(bars, groups):
            passes, n = counts[arm]
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                max(bar.get_height(), 0) + 0.025,
                f"{passes}/{n}",
                ha="center",
                va="bottom",
                fontsize=7,
                rotation=90 if len(groups) > 6 else 0,
            )
    ax.set_title(
        "Reward rate by language "
        f"(n={n_by_arm[ARM_ORDER[0]]} DeepSeek, "
        f"n={n_by_arm[ARM_ORDER[1]]} Mistral; group n shown)"
    )
    ax.set_xticks(x, [group for group, _ in groups], rotation=30, ha="right")
    ax.set_ylim(0, 1.22)
    ax.set_ylabel("Reward rate")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda value, _: f"{value:.0%}"))
    ax.grid(axis="y", alpha=0.25, zorder=0)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(
        CHARTS / "reward_by_language.svg",
        format="svg",
        bbox_inches="tight",
        metadata={"Title": ax.get_title(), "Creator": "LSCBench report builder"},
    )
    plt.close(fig)


def plot_heatmap(
    manifest: list[dict[str, object]],
    index: dict[str, dict[str, dict[str, str]]],
    official_by_arm: dict[str, list[dict[str, str]]],
) -> None:
    matrix = []
    for item in manifest:
        task = str(item["task"])
        values = []
        for arm in ARM_ORDER:
            row = index[arm].get(task)
            for column, _ in SCORE_COLUMNS:
                score = as_number(row.get(column)) if row else None
                values.append(2 if score is None else int(score == 1))
        matrix.append(values)
    cmap = ListedColormap(["#E03131", "#2F9E44", "#ADB5BD"])
    norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5], cmap.N)
    height = max(8.5, 0.34 * len(manifest))
    fig, ax = plt.subplots(figsize=(11.5, height))
    ax.imshow(matrix, aspect="auto", cmap=cmap, norm=norm)
    ax.set_xticks(
        range(6),
        ["DS F", "DS S", "DS R", "M F", "M S", "M R"],
    )
    ax.set_yticks(range(len(manifest)), [str(item["task"]) for item in manifest], fontsize=7)
    ax.tick_params(axis="x", top=True, bottom=False, labeltop=True, labelbottom=False)
    ax.set_title(
        f"Official per-task outcomes (n={len(manifest)} manifest tasks; "
        f"observed {len(official_by_arm[ARM_ORDER[0]])}/{len(official_by_arm[ARM_ORDER[1]])})"
    )
    ax.legend(
        handles=[
            Patch(color="#2F9E44", label="Pass"),
            Patch(color="#E03131", label="Fail"),
            Patch(color="#ADB5BD", label="Missing"),
        ],
        loc="lower center",
        bbox_to_anchor=(0.5, -0.04),
        ncol=3,
        frameon=False,
    )
    fig.tight_layout()
    fig.savefig(
        CHARTS / "task_heatmap.svg",
        format="svg",
        bbox_inches="tight",
        metadata={"Title": ax.get_title(), "Creator": "LSCBench report builder"},
    )
    plt.close(fig)


def classify_outcome(row: dict[str, str]) -> str:
    if as_number(row.get("reward")) == 1:
        return "reward pass"
    if as_number(row.get("functional")) == 1:
        return "functional only"
    if as_number(row.get("functional")) == 0:
        return "functional fail"
    return "unscored (exception, no verifier result)"


def plot_outcomes(official_by_arm: dict[str, list[dict[str, str]]]) -> None:
    categories = (
        "reward pass",
        "functional only",
        "functional fail",
        "unscored (exception, no verifier result)",
    )
    colors = {
        "reward pass": "#2F9E44",
        "functional only": "#F59F00",
        "functional fail": "#E03131",
        "unscored (exception, no verifier result)": "#868E96",
    }
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    x = list(range(len(ARM_ORDER)))
    bottoms = [0] * len(ARM_ORDER)
    counts_by_arm = {
        arm: Counter(classify_outcome(row) for row in official_by_arm[arm])
        for arm in ARM_ORDER
    }
    for category in categories:
        values = [counts_by_arm[arm][category] for arm in ARM_ORDER]
        bars = ax.bar(
            x,
            values,
            bottom=bottoms,
            color=colors[category],
            label=category,
            zorder=2,
        )
        for position, bar, value in zip(x, bars, values):
            if value:
                ax.text(
                    position,
                    bottoms[position] + value / 2,
                    str(value),
                    ha="center",
                    va="center",
                    color="white" if category != "functional only" else "#212529",
                    fontsize=9,
                    fontweight="bold",
                )
        bottoms = [bottom + value for bottom, value in zip(bottoms, values)]
    ns = [len(official_by_arm[arm]) for arm in ARM_ORDER]
    ax.set_title(f"Official outcome composition (n={ns[0]} DeepSeek, n={ns[1]} Mistral)")
    ax.set_xticks(x, [ARM_SHORT[arm] for arm in ARM_ORDER])
    ax.set_ylabel("Trials")
    ax.grid(axis="y", alpha=0.25, zorder=0)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=4)
    fig.tight_layout()
    fig.savefig(
        CHARTS / "outcomes.svg",
        format="svg",
        bbox_inches="tight",
        metadata={"Title": ax.get_title(), "Creator": "LSCBench report builder"},
    )
    plt.close(fig)


def plot_agent_time(official_by_arm: dict[str, list[dict[str, str]]]) -> None:
    values = {
        arm: [
            number / 60
            for row in official_by_arm[arm]
            if (number := as_number(row.get("agent_execution_s"))) is not None
        ]
        for arm in ARM_ORDER
    }
    fig, ax = plt.subplots(figsize=(8.5, 5.3))
    data = [values[arm] for arm in ARM_ORDER]
    box = ax.boxplot(
        data,
        positions=[1, 2],
        widths=0.5,
        patch_artist=True,
        showfliers=False,
        medianprops={"color": "#212529", "linewidth": 1.5},
    )
    for patch, arm in zip(box["boxes"], ARM_ORDER):
        patch.set_facecolor(ARM_COLORS[arm])
        patch.set_alpha(0.45)
    for position, arm in enumerate(ARM_ORDER, start=1):
        jitter = [
            position + ((index % 7) - 3) * 0.025
            for index in range(len(values[arm]))
        ]
        ax.scatter(
            jitter,
            values[arm],
            s=18,
            color=ARM_COLORS[arm],
            alpha=0.75,
            edgecolors="white",
            linewidths=0.3,
            zorder=3,
        )
    ns = [len(values[arm]) for arm in ARM_ORDER]
    ax.set_title(f"Agent execution time in minutes (n={ns[0]} DeepSeek, n={ns[1]} Mistral)")
    ax.set_xticks([1, 2], [ARM_SHORT[arm] for arm in ARM_ORDER])
    ax.set_ylabel("Minutes")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(
        CHARTS / "agent_time.svg",
        format="svg",
        bbox_inches="tight",
        metadata={"Title": ax.get_title(), "Creator": "LSCBench report builder"},
    )
    plt.close(fig)


def plot_cost_per_task(
    manifest: list[dict[str, object]],
    index: dict[str, dict[str, dict[str, str]]],
) -> None:
    tasks = [str(item["task"]) for item in manifest]
    positions = list(range(len(tasks)))
    height = max(8, 0.31 * len(tasks))
    fig, ax = plt.subplots(figsize=(13, height))
    bar_height = 0.36
    for offset, arm in ((-bar_height / 2, ARM_ORDER[0]), (bar_height / 2, ARM_ORDER[1])):
        values = [
            as_number(index[arm].get(task, {}).get("cost_usd"))
            for task in tasks
        ]
        ax.barh(
            [position + offset for position in positions],
            [value or 0 for value in values],
            height=bar_height,
            color=ARM_COLORS[arm],
            label=ARM_SHORT[arm],
        )
    ax.set_yticks(positions, tasks, fontsize=7)
    ax.invert_yaxis()
    ax.set_xlabel(
        "Cost (USD) — DeepSeek: billed, list price; "
        "Mistral: API-equivalent, billed to plan ($0)"
    )
    ax.set_title(f"Computed cost per task (n={len(tasks)} manifest tasks; missing cost shown as zero width)")
    ax.grid(axis="x", alpha=0.25, zorder=0)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(
        CHARTS / "cost_per_task.svg",
        format="svg",
        bbox_inches="tight",
        metadata={"Title": ax.get_title(), "Creator": "LSCBench report builder"},
    )
    plt.close(fig)


def plot_tokens(official_by_arm: dict[str, list[dict[str, str]]]) -> None:
    totals = {}
    for arm in ARM_ORDER:
        uncached = 0
        cached = 0
        output = 0
        for row in official_by_arm[arm]:
            input_total = as_number(row.get("input_tokens")) or 0
            cached_total = as_number(row.get("cached_input_tokens")) or 0
            uncached_total = as_number(row.get("uncached_input_tokens"))
            if uncached_total is None:
                uncached_total = max(0, input_total - cached_total)
            uncached += uncached_total
            cached += cached_total
            output += as_number(row.get("output_tokens")) or 0
        totals[arm] = (uncached, cached, output)

    component_colors = {
        ARM_ORDER[0]: ("#4C6EF5", "#8FA3FC", "#D5DCFE"),
        ARM_ORDER[1]: ("#F76707", "#FFA15C", "#FFD3B2"),
    }
    fig, ax = plt.subplots(figsize=(8.5, 5.4))
    x = list(range(len(ARM_ORDER)))
    labels = ("Uncached input", "Cached input", "Output")
    for index, arm in enumerate(ARM_ORDER):
        bottom = 0
        for component_index, value in enumerate(totals[arm]):
            ax.bar(
                index,
                value,
                bottom=bottom,
                width=0.58,
                color=component_colors[arm][component_index],
                edgecolor="white",
                label=labels[component_index] if index == 0 else None,
            )
            bottom += value
    handles = [
        Patch(facecolor="#4C6EF5", label="Uncached input"),
        Patch(facecolor="#8FA3FC", label="Cached input"),
        Patch(facecolor="#D5DCFE", label="Output"),
    ]
    ns = [len(official_by_arm[arm]) for arm in ARM_ORDER]
    ax.set_title(f"Official token totals (n={ns[0]} DeepSeek, n={ns[1]} Mistral)")
    ax.set_xticks(x, [ARM_SHORT[arm] for arm in ARM_ORDER])
    ax.set_ylabel("Tokens")
    ax.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda value, _: f"{value / 1_000_000:.0f}M")
    )
    ax.grid(axis="y", alpha=0.25, zorder=0)
    ax.legend(handles=handles, frameon=False)
    fig.tight_layout()
    fig.savefig(
        CHARTS / "tokens_stacked.svg",
        format="svg",
        bbox_inches="tight",
        metadata={"Title": ax.get_title(), "Creator": "LSCBench report builder"},
    )
    plt.close(fig)


def write_group_csv(
    path: Path,
    key_name: str,
    groups: list[tuple[str, dict[str, tuple[int, int]]]],
) -> None:
    headers = [
        key_name,
        "n_deepseek",
        "reward_passes_deepseek",
        "reward_rate_deepseek",
        "n_mistral",
        "reward_passes_mistral",
        "reward_rate_mistral",
    ]
    rows = []
    for key, counts in groups:
        row: list[object] = [key]
        for arm in ARM_ORDER:
            passes, n = counts[arm]
            row.extend((n, passes, f"{passes / n:.6f}" if n else ""))
        rows.append(row)
    make_csv(path, headers, rows)


def build_per_task_rows(
    manifest: list[dict[str, object]],
    index: dict[str, dict[str, dict[str, str]]],
) -> list[list[object]]:
    output = []
    for item in manifest:
        task = str(item["task"])
        deepseek = index[ARM_ORDER[0]].get(task, {})
        mistral = index[ARM_ORDER[1]].get(task, {})
        published = item.get("published_reward", {})
        deepseek_tokens = as_number(deepseek.get("input_tokens"))
        deepseek_output = as_number(deepseek.get("output_tokens"))
        mistral_tokens = as_number(mistral.get("input_tokens"))
        mistral_output = as_number(mistral.get("output_tokens"))
        values: list[object] = [
            task,
            item.get("lang", ""),
            item.get("cwe", ""),
        ]
        for row in (deepseek, mistral):
            values.extend(
                "" if as_int(row.get(column)) is None else as_int(row.get(column))
                for column in ("functional", "secure", "reward")
            )
        values.extend(
            (
                "" if as_number(deepseek.get("agent_execution_s")) is None
                else f"{as_number(deepseek.get('agent_execution_s')) / 60:.3f}",
                "" if as_number(mistral.get("agent_execution_s")) is None
                else f"{as_number(mistral.get('agent_execution_s')) / 60:.3f}",
                "" if deepseek_tokens is None and deepseek_output is None
                else int((deepseek_tokens or 0) + (deepseek_output or 0)),
                "" if mistral_tokens is None and mistral_output is None
                else int((mistral_tokens or 0) + (mistral_output or 0)),
                published.get("GLM-5.3", ""),
                published.get("DeepSeek-V4-Pro", ""),
            )
        )
        output.append(values)
    return output


def consistency_notes(
    rows: list[dict[str, str]],
    summary: dict[str, object],
    manifest: list[dict[str, object]],
) -> list[str]:
    notes = []
    scored = group_by_arm(official_rows(rows))
    task_names = {str(item["task"]) for item in manifest}
    for arm in ARM_ORDER:
        actual = scored[arm]
        expected = summary.get(arm, {}) if isinstance(summary, dict) else {}
        computed = {
            "n_tasks": len(actual),
            "functional": sum(as_number(row.get("functional")) == 1 for row in actual),
            "secure": sum(as_number(row.get("secure")) == 1 for row in actual),
            "reward": sum(as_number(row.get("reward")) == 1 for row in actual),
            "exceptions": sum(bool(row.get("exception_type", "").strip()) for row in actual),
            "infra_failures": sum(flag(row.get("infra_failure")) for row in actual),
        }
        for key, value in computed.items():
            if key in expected and expected[key] != value:
                notes.append(
                    f"{ARM_SHORT[arm]}: summary.json {key}={expected[key]} but "
                    f"official CSV rows yield {value}."
                )
        seen = Counter(row.get("task", "") for row in actual)
        duplicates = sorted(task for task, count in seen.items() if count > 1)
        if duplicates:
            notes.append(
                f"{ARM_SHORT[arm]}: duplicate official task rows: {', '.join(duplicates)}."
            )
        outside = sorted(set(seen) - task_names)
        if outside:
            notes.append(
                f"{ARM_SHORT[arm]}: official CSV tasks absent from manifest: "
                f"{', '.join(outside)}."
            )
    return notes


def make_readme(
    rows: list[dict[str, str]],
    summary: dict[str, object],
    manifest: list[dict[str, object]],
    balance: list[dict[str, str]],
    runner_text: str,
    pulls: list[dict[str, str]],
    commands_text: str,
    void_data: dict[str, object],
    official: list[dict[str, str]],
    by_arm: dict[str, list[dict[str, str]]],
    index: dict[str, dict[str, dict[str, str]]],
    by_language: list[tuple[str, dict[str, tuple[int, int]]]],
    by_cwe: list[tuple[str, dict[str, tuple[int, int]]]],
    consistency: list[str],
) -> str:
    intervals = batch_intervals(runner_text)
    log_timestamps = [
        stamp
        for line in runner_text.splitlines()
        if (stamp := parse_timestamp(line.split(maxsplit=1)[0] if line else "")) is not None
    ]
    run_start_label = (
        timestamp_label(intervals[1][0])
        if intervals[1][0] is not None
        else "unknown"
    )
    rerun2_ends = [
        stamp
        for line in runner_text.splitlines()
        if (
            match := re.match(
                r"^(\S+)\s+pilot30-rerun2-mistral-vibe exited with status \d+$",
                line,
            )
        )
        and (stamp := parse_timestamp(match.group(1))) is not None
    ]
    run_end = max(rerun2_ends) if rerun2_ends else (max(log_timestamps) if log_timestamps else None)
    run_window = f"{run_start_label} through {timestamp_label(run_end)}"
    lines = [
        "# LSCBench function-level pilot (30 tasks): DeepSeek Flash vs Mistral Large 4",
        "",
        "**Caveat:** Assistant-selected 30-task subset (seed 20261120) of the 150 function-level tasks; NOT an official LSCBench score; model+agent comparison, not model-only.",
        "",
        "## Setup",
        "",
        markdown_table(
            ["Setting", "DeepSeek arm", "Mistral arm", "Shared / notes"],
            [
                [
                    "Agent + version",
                    "claude-code 2.1.143",
                    "vibe 3.1.3",
                    "Custom install/cache wrappers described below",
                ],
                [
                    "Model ID",
                    "deepseek-flash (DeepSeek-V4.1-Flash-1017)",
                    "mistral-large-4-0",
                    "Model IDs from the frozen run configuration",
                ],
                [
                    "Reasoning",
                    "effort=max",
                    "thinking=high",
                    "—",
                ],
                [
                    "Provider + endpoint",
                    "DeepSeek: https://api.deepseek.com/anthropic (Anthropic-compatible)",
                    "Mistral: https://api.mistral.ai (Vibe CLI, Le Chat Pro plan)",
                    "Provider endpoints used by the agents",
                ],
                [
                    "Harness / dataset",
                    "Harbor 0.26.0",
                    "Harbor 0.26.0",
                    "last-secure-code-benchmark@v1.0",
                ],
                [
                    "Concurrency",
                    "3 trials",
                    "3 trials",
                    "Both arms concurrent; 3 strided batches of 10; retries 0",
                ],
                [
                    "Host",
                    "—",
                    "—",
                    "8 vCPU, 31 GB RAM, Docker 29.9.2",
                ],
                [
                    "Run dates (UTC)",
                    run_window,
                    run_window,
                    "Timestamps and per-batch wall-clock below",
                ],
            ],
        ),
        "",
        "## Headline",
        "",
        "Scores use only `official=1` rows. Each rate denominator is the official trial count; missing scores on an official exception are not counted as passes.",
        "",
    ]

    headline_rows = []
    for arm in ARM_ORDER:
        arm_rows = by_arm[arm]
        reward_passes = sum(score_pass(row, "reward") for row in arm_rows)
        known_costs = [
            as_number(row.get("cost_usd"))
            for row in arm_rows
            if as_number(row.get("cost_usd")) is not None
        ]
        total_cost = sum(known_costs) if known_costs else None
        reward_cost = (
            total_cost / reward_passes
            if total_cost is not None and reward_passes
            else None
        )
        execution = [
            number
            for row in arm_rows
            if (number := as_number(row.get("agent_execution_s"))) is not None
        ]
        steps = [
            number
            for row in arm_rows
            if (number := as_number(row.get("steps"))) is not None
        ]
        input_tokens = sum(as_number(row.get("input_tokens")) or 0 for row in arm_rows)
        cached_tokens = sum(
            as_number(row.get("cached_input_tokens")) or 0 for row in arm_rows
        )
        output_tokens = sum(as_number(row.get("output_tokens")) or 0 for row in arm_rows)
        headline_rows.append(
            [
                ARM_LABELS[arm],
                len(arm_rows),
                format_rate(arm_rows, "functional"),
                format_rate(arm_rows, "secure"),
                format_rate(arm_rows, "reward"),
                sum(bool(row.get("exception_type", "").strip()) for row in arm_rows),
                sum(flag(row.get("infra_failure")) for row in arm_rows),
                f"{format_int(input_tokens)} / {format_int(cached_tokens)} / {format_int(output_tokens)}",
                format_usd(total_cost),
                format_usd(reward_cost),
                format_seconds(statistics.median(execution)) if execution else "—",
                format_seconds(statistics.median(steps)) if steps else "—",
            ]
        )
    lines.extend(
        [
            markdown_table(
                [
                    "Arm",
                    "n",
                    "Functional",
                    "Secure",
                    "Reward",
                    "Exceptions",
                    "Infra failures",
                    "Input incl. cached / cached / output tokens",
                    "Computed cost",
                    "Cost per reward pass",
                    "Median agent execution (s)",
                    "Median steps",
                ],
                headline_rows,
            ),
            "",
            "Official rows: 30 per arm. Void trials are excluded and replaced by their re-run.",
            "DeepSeek's computed cost uses the per-row `cost_basis`; Mistral uses the Vibe export cost. Token totals omit trials without usage telemetry.",
            "Rate intervals are Wilson 95% confidence intervals with z=1.96.",
            "",
            "![Functional, secure, and reward rates with Wilson intervals](charts/rates_ci.svg)",
            "",
            "## Head-to-head",
            "",
        ]
    )

    paired_rows = []
    discordant: dict[str, list[tuple[str, str, str]]] = {}
    common_tasks = sorted(set(index[ARM_ORDER[0]]) & set(index[ARM_ORDER[1]]))
    for column, label in SCORE_COLUMNS:
        both = only_deepseek = only_mistral = neither = 0
        differences = []
        for task in common_tasks:
            ds_pass = score_pass(index[ARM_ORDER[0]][task], column)
            m_pass = score_pass(index[ARM_ORDER[1]][task], column)
            if ds_pass and m_pass:
                both += 1
            elif ds_pass:
                only_deepseek += 1
                differences.append((task, "pass", "fail"))
            elif m_pass:
                only_mistral += 1
                differences.append((task, "fail", "pass"))
            else:
                neither += 1
        discordant[column] = differences
        paired_rows.append(
            [
                label,
                both,
                only_deepseek,
                only_mistral,
                neither,
                f"{mcnemar_exact(only_deepseek, only_mistral):.6f}",
            ]
        )
    lines.extend(
        [
            f"Paired comparison uses {len(common_tasks)} tasks present in both arms; blank metric values count as non-passes.",
            "Exact two-sided McNemar p = min(1, 2 × BinomCDF(min(b,c); b+c, 0.5)); p=1 when b+c=0.",
            "",
            markdown_table(
                [
                    "Metric",
                    "Both pass",
                    "Only DeepSeek",
                    "Only Mistral",
                    "Neither",
                    "Exact two-sided McNemar p",
                ],
                paired_rows,
            ),
            "",
            "Tasks with differing outcomes:",
            "",
        ]
    )
    differences = []
    for column, label in SCORE_COLUMNS:
        for task, ds_result, m_result in discordant[column]:
            differences.append([label, task, ds_result, m_result])
    lines.append(
        markdown_table(
            ["Metric", "Task", "DeepSeek", "Mistral"],
            differences or [["—", "No discordant outcomes", "—", "—"]],
        )
    )

    def group_md_table(
        groups: list[tuple[str, dict[str, tuple[int, int]]]],
        label: str,
    ) -> str:
        return markdown_table(
            [
                label,
                "DeepSeek n",
                "DeepSeek reward",
                "Mistral n",
                "Mistral reward",
            ],
            [
                [
                    name,
                    counts[ARM_ORDER[0]][1],
                    format_count_rate(*counts[ARM_ORDER[0]]),
                    counts[ARM_ORDER[1]][1],
                    format_count_rate(*counts[ARM_ORDER[1]]),
                ]
                for name, counts in groups
            ],
        )

    lines.extend(
        [
            "",
            "## By language and by CWE",
            "",
            "Reward rates use official trials; `n` is the number of official tasks observed in that group for the arm.",
            "",
            "### By language",
            "",
            group_md_table(by_language, "Language"),
            "",
            "### By CWE",
            "",
            group_md_table(by_cwe, "CWE"),
            "",
            "![Reward rates by language](charts/reward_by_language.svg)",
            "",
            "## Per-task results",
            "",
            "F/S/R are functional, secure, and reward; execution time is agent minutes; total tokens are input plus output. Gray heatmap cells indicate missing scores.",
            "",
        ]
    )

    task_md_rows = []
    for item in manifest:
        task = str(item["task"])
        ds = index[ARM_ORDER[0]].get(task)
        ms = index[ARM_ORDER[1]].get(task)
        task_md_rows.append(
            [
                task,
                item.get("lang", ""),
                item.get("cwe", ""),
                format_fsr(ds),
                format_fsr(ms),
                format_minutes(as_number(ds.get("agent_execution_s")) if ds else None),
                format_minutes(as_number(ms.get("agent_execution_s")) if ms else None),
                format_int(row_total_tokens(ds)),
                format_int(row_total_tokens(ms)),
                published_value(item, "GLM-5.3"),
                published_value(item, "DeepSeek-V4-Pro"),
            ]
        )
    lines.extend(
        [
            markdown_table(
                [
                    "Task",
                    "Lang",
                    "CWE",
                    "DS F/S/R",
                    "M F/S/R",
                    "DS agent min",
                    "M agent min",
                    "DS total tokens",
                    "M total tokens",
                    "GLM-5.3 reward",
                    "DeepSeek-V4-Pro reward",
                ],
                task_md_rows,
            ),
            "",
            "![Per-task score heatmap](charts/task_heatmap.svg)",
            "",
            "## Errors & exceptions",
            "",
            "All CSV rows with an exception are shown, including void and superseded rows. `Counted as` distinguishes official, voided/re-run, and pre-prompt infrastructure failures.",
            "",
        ]
    )

    exception_rows = [row for row in rows if row.get("exception_type", "").strip()]
    error_table_rows = []
    for row in exception_rows:
        arm = row.get("arm", "")
        task = row.get("task", "")
        if flag(row.get("official")):
            counted = "official"
        elif flag(row.get("void")):
            counted = f"void — re-run ({row.get('void_reason', '').strip()})"
        elif flag(row.get("infra_failure")):
            counted = "superseded by re-run (infra failure before prompt)"
        else:
            counted = "not official"
        error_table_rows.append(
            [
                ARM_SHORT.get(arm, arm),
                task,
                row.get("exception_type", ""),
                row.get("exception_phase", "") or "—",
                exception_display_message(row),
                counted,
            ]
        )
    lines.append(
        markdown_table(
            ["Arm", "Task", "Exception type", "Phase", "Message (first line)", "Counted as"],
            error_table_rows or [["—", "No exception rows", "—", "—", "—", "—"]],
        )
    )
    verifier_rows = [
        row for row in rows if row.get("verifier_error", "").strip()
    ]
    lines.extend(["", "Verifier errors:", ""])
    if verifier_rows:
        lines.append(
            markdown_table(
                ["Arm", "Task", "Verifier error"],
                [
                    [
                        ARM_SHORT.get(row.get("arm", ""), row.get("arm", "")),
                        row.get("task", ""),
                        clean_text(row.get("verifier_error", "")),
                    ]
                    for row in verifier_rows
                ],
            )
        )
    else:
        lines.append("None recorded.")
    timeout_rows = [row for row in rows if row.get("exception_type") == "AgentTimeoutError"]
    fallback_rows = [row for row in rows if flag(row.get("install_fallback"))]
    lines.extend(["", "One-hour agent timeouts (graded on the code at timeout):", ""])
    lines.append(
        markdown_table(
            ["Arm", "Task", "Agent execution (s)", "Reward"],
            [
                [
                    ARM_SHORT.get(row.get("arm", ""), row.get("arm", "")),
                    row.get("task", ""),
                    format_seconds(as_number(row.get("agent_execution_s"))),
                    row.get("reward", "") or "—",
                ]
                for row in timeout_rows
            ]
            or [["—", "None recorded", "—", "—"]],
        )
    )
    lines.extend(["", "Trials using the Claude Code install fallback:", ""])
    lines.append(
        markdown_table(
            ["Arm", "Task", "Job", "Trial", "Official", "install_fallback"],
            [
                [
                    ARM_SHORT.get(row.get("arm", ""), row.get("arm", "")),
                    row.get("task", ""),
                    row.get("job", ""),
                    row.get("trial", ""),
                    "1" if flag(row.get("official")) else "0",
                    "1",
                ]
                for row in fallback_rows
            ]
            or [["—", "None recorded", "—", "—", "—", "—"]],
        )
    )
    lines.extend(
        [
            "",
            "![Official outcome composition](charts/outcomes.svg)",
            "",
            "## What the models missed",
            "",
            "Security failures are listed for every official row with `secure=0`; functional failures are listed separately for every official row with `functional=0`.",
            "",
            "### Security failures",
            "",
        ]
    )
    security_misses = [
        row
        for row in official
        if as_number(row.get("secure")) == 0
    ]
    lines.append(
        markdown_table(
            ["Arm", "Task", "CWE", "n_failed_vuln", "vulnerability_msg (≤200 chars)"],
            [
                [
                    ARM_SHORT.get(row.get("arm", ""), row.get("arm", "")),
                    row.get("task", ""),
                    row.get("cwe", ""),
                    row.get("n_failed_vuln", ""),
                    vulnerability_display(row),
                ]
                for row in security_misses
            ]
            or [["—", "None recorded", "—", "—", "—"]],
        )
    )
    functional_misses = [
        row
        for row in official
        if as_number(row.get("functional")) == 0
    ]
    lines.extend(["", "### Functional failures", ""])
    lines.append(
        markdown_table(
            ["Arm", "Task", "n_failed_func", "failed_func_tests"],
            [
                [
                    ARM_SHORT.get(row.get("arm", ""), row.get("arm", "")),
                    row.get("task", ""),
                    row.get("n_failed_func", ""),
                    clean_text(row.get("failed_func_tests", "")) or "—",
                ]
                for row in functional_misses
            ]
            or [["—", "None recorded", "—", "—"]],
        )
    )

    lines.extend(["", "## Speed", ""])
    time_rows = []
    for phase, label in TIME_COLUMNS:
        for arm in ARM_ORDER:
            values = [
                number
                for row in by_arm[arm]
                if (number := as_number(row.get(phase))) is not None
            ]
            time_rows.append(
                [
                    label,
                    ARM_SHORT[arm],
                    len(values),
                    format_seconds(min(values) if values else None),
                    format_seconds(statistics.median(values) if values else None),
                    format_seconds(nearest_rank(values, 90)),
                    format_seconds(max(values) if values else None),
                ]
            )
    lines.extend(
        [
            markdown_table(
                ["Phase (s)", "Arm", "n", "Min", "Median", "P90 (nearest-rank)", "Max"],
                time_rows,
            ),
            "",
            "Batch wall-clock intervals from the runner log:",
            "",
        ]
    )
    batch_rows = []
    for batch_num in (1, 2, 3):
        start, end, status = intervals[batch_num]
        batch_rows.append(
            [
                f"Batch {batch_num}",
                timestamp_label(start),
                timestamp_label(end) if end else "—",
                duration_text(start, end),
                status,
            ]
        )
    lines.extend(
        [
            markdown_table(
                ["Batch", "Start (UTC)", "End (UTC)", "Wall-clock", "Status"],
                batch_rows,
            ),
            "",
            "![Agent execution time by arm](charts/agent_time.svg)",
            "",
            "## Tokens & cost",
            "",
        ]
    )

    cost_rows = []
    for arm in ARM_ORDER:
        values = [
            as_number(row.get("cost_usd"))
            for row in by_arm[arm]
            if as_number(row.get("cost_usd")) is not None
        ]
        costs = sum(values)
        basis = sorted(
            {
                row.get("cost_basis", "")
                for row in by_arm[arm]
                if row.get("cost_basis", "").strip()
            }
        )
        total_input = sum(as_number(row.get("input_tokens")) or 0 for row in by_arm[arm])
        total_cached = sum(
            as_number(row.get("cached_input_tokens")) or 0 for row in by_arm[arm]
        )
        total_output = sum(
            as_number(row.get("output_tokens")) or 0 for row in by_arm[arm]
        )
        harbor_values = [
            as_number(row.get("harbor_cost_usd"))
            for row in by_arm[arm]
            if as_number(row.get("harbor_cost_usd")) is not None
        ]
        cost_rows.append(
            [
                ARM_SHORT[arm],
                format_int(total_input),
                format_int(total_cached),
                format_int(total_output),
                format_usd(costs),
                ", ".join(basis) or "—",
                format_usd(sum(harbor_values) if harbor_values else None),
            ]
        )
    ds_computed = sum(
        as_number(row.get("cost_usd")) or 0 for row in by_arm[ARM_ORDER[0]]
    )
    ds_harbor = sum(
        as_number(row.get("harbor_cost_usd")) or 0 for row in by_arm[ARM_ORDER[0]]
    )
    ds_all_jobs = {
        "pilot30-b1-deepseek-cc",
        "pilot30-b2-deepseek-cc",
        "pilot30-b3-deepseek-cc",
        "pilot30-rerun1-deepseek-cc",
    }
    ds_all_rows = [
        row
        for row in rows
        if row.get("arm") == ARM_ORDER[0] and row.get("job") in ds_all_jobs
    ]
    ds_all_cost = sum(as_number(row.get("cost_usd")) or 0 for row in ds_all_rows)
    lines.extend(
        [
            markdown_table(
                [
                    "Arm",
                    "Input incl. cached",
                    "Cached input",
                    "Output",
                    "Computed cost",
                    "CSV cost_basis",
                    "Harbor cost estimate",
                ],
                cost_rows,
            ),
            "",
            "Cost basis: DeepSeek uses the DeepSeek-V4.1-Flash official list price recorded per row in `cost_basis` (off-peak: $0.15/M uncached input, $0.003/M cached input, $0.60/M output; peak pricing applies only where the row basis says so). Harbor's own estimate is shown alongside but was not used; it is "
            + ratio_text(ds_harbor, ds_computed)
            + " the computed DeepSeek cost in this snapshot. Mistral cost is Vibe export `cost_usd` (API-equivalent); the Le Chat Pro subscription billing for these calls is $0.",
            "",
            "Per-task computed cost:",
            "",
            "![Computed cost per task](charts/cost_per_task.svg)",
            "",
            "Token mix:",
            "",
            "![Uncached input, cached input, and output token totals](charts/tokens_stacked.svg)",
            "",
            "DeepSeek balance observations:",
            "",
        ]
    )

    clean_start = intervals[1][0]
    clean_balance_start = None
    if clean_start is not None:
        for row in balance:
            stamp = parse_timestamp(row.get("ts_utc", ""))
            if (
                row.get("label") == "batch1-boundary-start"
                and stamp is not None
                and stamp >= clean_start
            ):
                clean_balance_start = row
                break
    balance_rows = []
    if balance:
        for row in (balance[0], balance[-1]):
            balance_rows.append(
                [row.get("ts_utc", ""), row.get("label", ""), row.get("total_balance", "")]
            )
    boundary_rows = [
        row for row in balance if "boundary" in row.get("label", "").lower()
    ]
    for row in boundary_rows:
        balance_rows.append(
            [row.get("ts_utc", ""), row.get("label", ""), row.get("total_balance", "")]
        )
    unique_balance_rows = []
    seen_balance_rows = set()
    for row in balance_rows:
        key = tuple(row)
        if key not in seen_balance_rows:
            seen_balance_rows.add(key)
            unique_balance_rows.append(row)
    lines.append(
        markdown_table(
            ["Timestamp (UTC)", "Label", "Balance (USD)"],
            unique_balance_rows or [["—", "No balance rows", "—"]],
        )
    )
    if clean_balance_start is not None and balance:
        clean_value = as_number(clean_balance_start.get("total_balance"))
        latest_value = as_number(balance[-1].get("total_balance"))
        delta = (
            latest_value - clean_value
            if clean_value is not None and latest_value is not None
            else None
        )
        signed_delta = (
            f"-{format_usd(abs(delta), 2)}"
            if delta is not None and delta < 0
            else format_usd(delta, 2)
        )
        lines.extend(
            [
                "",
                "DeepSeek reconciliation (balance rounded to cents; all DeepSeek rows, "
                "official + void):",
                "",
                markdown_table(
                    [
                        "Scope",
                        "Balance change",
                        "Computed cost",
                        "Rows included",
                    ],
                    [
                        [
                            "pilot30-b1/b2/b3 and rerun1",
                            f"{format_usd(clean_value, 2)} "
                            f"({clean_balance_start.get('ts_utc', '')}) → "
                            f"{format_usd(latest_value, 2)} "
                            f"({balance[-1].get('ts_utc', '')}); "
                            f"change {signed_delta}",
                            format_usd(ds_all_cost, 6),
                            f"{len(ds_all_rows)} DeepSeek CSV rows, including void trials",
                        ]
                    ],
                ),
                "",
                f"The rounded balance debit is {format_usd(abs(delta), 2)} versus "
                f"{format_usd(ds_all_cost, 6)} computed cost; the "
                f"{format_usd(abs(abs(delta) - ds_all_cost), 6)} difference is within "
                "cent-rounding precision.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "Clean-run balance change is not yet available from the supplied balance rows.",
            ]
        )

    incident_text = [
        "Two aborted attempts (disk exhaustion at 16:54 UTC; earlier disk guard at ~15:55 UTC) are preserved under jobs/*-aborted1 and jobs/pilot30-deepseek-cc and excluded from scores.",
        "Docker Hub anonymous pulls: one token-fetch failure (batch 3, first attempt) and one HTTP 429; retried; no task ran on a partially pulled image.",
        "Claude Code's apt-based installer fails on some old task images; a fallback uses Anthropic's native bootstrap installer for the same version (2.1.143). Trials using it are marked install_fallback=1.",
        "Vibe: Harbor 0.26 cannot copy Vibe's plugin cache (hardlinks) or parse Vibe 3.1.3 session logs, so a wrapper deletes the plugin cache after the run and passes --output-dir to Vibe; token counts come from Vibe's export.json.",
        "Re-run policy (fixed before any re-run): a trial is re-run once only if it failed before the agent received the prompt; timeouts and in-run errors count as the single attempt.",
        "Trials that hit the 1-hour agent timeout are still graded on the code present at timeout (Harbor behaviour).",
        "Mistral/Vibe self-termination: in the official xss_codeforge_readme_render_function trial (re-run 2), Mistral's agent ran `pkill -f` 9 times while 'stopping the app' after verifying its work; Vibe was then terminated (exit 143) after 20 steps. The code present at that point was graded (functional 1, secure 0).",
        "For the official Mistral/Vibe vert_priv_module_revoke_bypass_function trial (exit 143), the unified-session store was absent and 0 pkill/killall/kill command matches were available; cause of exit 143 not determined from logs.",
    ]
    lines.extend(["", "## Incidents & deviations", ""])
    lines.extend(f"- {item}" for item in incident_text)

    void_policy = void_data.get("policy", "")
    lines.extend(
        [
            "",
            "### Void trials and re-runs",
            "",
            "Policy (verbatim from `notes/void_trials.json`):",
            "",
            str(void_policy),
            "",
            "The batch-3 disk guard fired at 20:25:11 UTC when free disk fell from 34.5 GB to 5.4 GB in one minute during concurrent environment-image builds; re-runs used 2 concurrent trials per arm.",
            "",
            markdown_table(
                [
                    "Voided job",
                    "Voided trial",
                    "Reason",
                    "Replacement job / trial",
                    "Replacement outcome",
                ],
                void_rerun_rows(void_data, rows)
                or [["—", "No void rows", "—", "—", "—"]],
            ),
        ]
    )

    pull_counts = Counter(
        (row.get("batch", ""), row.get("status", ""))
        for row in pulls
    )
    pull_batches = sorted(
        {row.get("batch", "") for row in pulls},
        key=lambda value: (not value.isdigit(), int(value) if value.isdigit() else value),
    )
    pull_statuses = ("ok", "retry_failed", "failed", "failed_429", "timeout")
    lines.extend(
        [
            "",
            "Image-pull CSV attempt counts (includes prior aborted attempts):",
            "",
            markdown_table(
                ["Batch", *pull_statuses],
                [
                    [
                        batch,
                        *(pull_counts[(batch, status)] for status in pull_statuses),
                    ]
                    for batch in pull_batches
                ]
                or [["—", *(0 for _ in pull_statuses)]],
            ),
        ]
    )

    lines.extend(
        [
            "",
            "Published timeout trials:",
            "",
            markdown_table(
                ["Arm", "Task"],
                [
                    [ARM_SHORT.get(row.get("arm", ""), row.get("arm", "")), row.get("task", "")]
                    for row in timeout_rows
                ]
                or [["—", "None recorded"]],
            ),
            "",
            "Trials with `install_fallback=1`:",
            "",
            "The job, trial, and official-status list appears in the Errors & exceptions section above.",
            "",
            "## Published context",
            "",
            "Published reward totals for these same 30 tasks, from the LSCBench traces; these are Claude Code max-effort runs and are not directly the same arm configuration as this pilot.",
            "",
        ]
    )
    published_rows = []
    for model in ("GLM-5.3", "DeepSeek-V4-Pro"):
        known = [
            as_number(item.get("published_reward", {}).get(model))
            for item in manifest
            if as_number(item.get("published_reward", {}).get(model)) is not None
        ]
        total = int(sum(known)) if known else 0
        published_rows.append([model, f"{total}/{len(known)}", len(known)])
    lines.extend(
        [
            markdown_table(["Published model", "Reward passes / tasks", "n"], published_rows),
            "",
            "## Reproduce / files",
            "",
            "Generator command: `python3 report/build_report.py`.",
            "",
            "Inputs and provenance:",
            "",
            "- Manifest: `notes/pilot30.json`",
            "- Void and re-run manifest: `notes/void_trials.json`",
            "- Run commands and incident notes: `notes/pilot30-commands.md`",
            "- Frozen trial rows: `report/data/trials.csv`",
            "- Frozen aggregate input: `report/data/summary.json`",
            "- Balance observations: `data/deepseek_balance.csv`",
            "- Batch timeline: `data/pilot_runner.log`",
            "- Manual rerun telemetry: `data/rerun1_runner.log`, `data/rerun2_runner.log`",
            "- Pull telemetry: `data/image_pulls_pilot.csv`",
            "- Presentation generator: `report/build_report.py`",
            "- Extractor provenance only; not invoked by this generator: `report/extract.py`",
            "- Report page: `report/README.md`",
            "- Generated language summary: `report/data/by_language.csv`",
            "- Generated CWE summary: `report/data/by_cwe.csv`",
            "- Generated per-task table: `report/data/per_task_wide.csv`",
            "- Generated charts: `report/charts/rates_ci.svg`, `report/charts/reward_by_language.svg`, `report/charts/task_heatmap.svg`, `report/charts/outcomes.svg`, `report/charts/agent_time.svg`, `report/charts/cost_per_task.svg`, `report/charts/tokens_stacked.svg`",
            "- Pilot jobs: `jobs/pilot30-b1-deepseek-cc/`, `jobs/pilot30-b1-mistral-vibe/`, `jobs/pilot30-b2-deepseek-cc/`, `jobs/pilot30-b2-mistral-vibe/`, `jobs/pilot30-b3-deepseek-cc/`, `jobs/pilot30-b3-mistral-vibe/`",
            "- Re-run jobs: `jobs/pilot30-rerun1-deepseek-cc/`, `jobs/pilot30-rerun1-mistral-vibe/`, `jobs/pilot30-rerun2-mistral-vibe/`",
            "",
            f"Input snapshot: {len(rows)} CSV rows, {len(official)} official rows, "
            f"{len(manifest)} manifest tasks; current official coverage is "
            f"{len(by_arm[ARM_ORDER[0]])}/{len(manifest)} DeepSeek and "
            f"{len(by_arm[ARM_ORDER[1]])}/{len(manifest)} Mistral.",
            "",
        ]
    )
    if consistency:
        lines.extend(["Input consistency warnings:", ""])
        lines.extend(f"- {item}" for item in consistency)
        lines.append("")
    lines.append(
        "The generator reads the frozen CSV and metadata only; it does not inspect job directories or recompute extracted trial metrics."
    )
    return "\n".join(lines) + "\n"


def format_count_rate(passes: int, n: int) -> str:
    return f"{passes}/{n} ({100 * passes / n:.1f}%)" if n else "0/0 (n/a)"


def format_fsr(row: dict[str, str] | None) -> str:
    if row is None:
        return "— / — / —"
    values = [
        "—" if as_int(row.get(column)) is None else str(as_int(row.get(column)))
        for column, _ in SCORE_COLUMNS
    ]
    return " / ".join(values)


def row_total_tokens(row: dict[str, str] | None) -> int | None:
    if row is None:
        return None
    input_tokens = as_number(row.get("input_tokens"))
    output_tokens = as_number(row.get("output_tokens"))
    if input_tokens is None and output_tokens is None:
        return None
    return int((input_tokens or 0) + (output_tokens or 0))


def published_value(item: dict[str, object], model: str) -> object:
    values = item.get("published_reward", {})
    return values.get(model, "—") if isinstance(values, dict) else "—"


def main() -> int:
    rows = read_csv(TRIALS_PATH)
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    manifest_data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest = manifest_data.get("tasks", [])
    balance = read_csv(BALANCE_PATH)
    pulls = read_csv(PULLS_PATH)
    runner_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in (RUNNER_LOG_PATH, RERUN1_LOG_PATH, RERUN2_LOG_PATH)
        if path.exists()
    )
    commands_text = COMMANDS_PATH.read_text(encoding="utf-8", errors="replace")
    void_data = json.loads(VOID_TRIALS_PATH.read_text(encoding="utf-8"))
    _ = pulls, commands_text

    official = official_rows(rows)
    by_arm = group_by_arm(official)
    index = official_index(official)
    by_language = grouped_reward_counts(manifest, index, "lang")
    by_cwe = grouped_reward_counts(manifest, index, "cwe")
    consistency = consistency_notes(rows, summary, manifest)

    CHARTS.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(
        {
            "font.size": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "svg.fonttype": "none",
        }
    )

    plot_rates(by_arm)
    plot_reward_by_language(
        by_language,
        {arm: len(by_arm[arm]) for arm in ARM_ORDER},
    )
    plot_heatmap(manifest, index, by_arm)
    plot_outcomes(by_arm)
    plot_agent_time(by_arm)
    plot_cost_per_task(manifest, index)
    plot_tokens(by_arm)

    write_group_csv(DATA / "by_language.csv", "language", by_language)
    write_group_csv(DATA / "by_cwe.csv", "cwe", by_cwe)
    make_csv(
        DATA / "per_task_wide.csv",
        [
            "task",
            "language",
            "cwe",
            "DS_functional",
            "DS_secure",
            "DS_reward",
            "M_functional",
            "M_secure",
            "M_reward",
            "DS_agent_minutes",
            "M_agent_minutes",
            "DS_total_tokens",
            "M_total_tokens",
            "GLM-5.3_published_reward",
            "DeepSeek-V4-Pro_published_reward",
        ],
        build_per_task_rows(manifest, index),
    )
    readme = make_readme(
        rows,
        summary,
        manifest,
        balance,
        runner_text,
        pulls,
        commands_text,
        void_data,
        official,
        by_arm,
        index,
        by_language,
        by_cwe,
        consistency,
    )
    (REPORT / "README.md").write_text(readme, encoding="utf-8")
    print(
        "Built report/README.md, report/data/by_language.csv, "
        "report/data/by_cwe.csv, report/data/per_task_wide.csv, "
        "and seven SVG charts under report/charts/."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
