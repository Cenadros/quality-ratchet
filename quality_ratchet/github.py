from __future__ import annotations

import os

from .baseline import Delta


def emit(deltas: list[Delta], baseline_score: int, score: int) -> None:
    for d in deltas:
        if d.status == "fail":
            print(f"::error title=quality-ratchet::{d.name} {d.baseline} → {d.now} ({d.delta:+g})")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    lines = ["## quality-ratchet", "", "| metric | baseline | now | delta | status |", "|---|---:|---:|---:|---|"]
    for d in deltas:
        base = "—" if d.baseline is None else f"{d.baseline:g}"
        lines.append(f"| {d.name} | {base} | {d.now:g} | {d.delta:+g} | {d.status} |")
    lines.append(f"| **score** | {baseline_score} | {score} | {score - baseline_score:+d} | |")
    with open(summary_path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
