#!/usr/bin/env python3
"""Create an isolated deep-research workspace without deleting existing data."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path


MODES = ("quick", "standard", "deep")


def sanitize_keyword(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").strip()
    chars = []
    for char in normalized:
        if char.isalnum() or "\u4e00" <= char <= "\u9fff":
            chars.append(char)
    keyword = "".join(chars)[:6]
    return keyword or "research"


def atomic_json(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, path)


def ensure_within(path: Path, parent: Path) -> None:
    try:
        path.relative_to(parent)
    except ValueError as exc:
        raise ValueError(f"Path escapes allowed root: {path}") from exc


def create_workspace(
    workspace: Path,
    keyword: str,
    mode: str,
    lang: str,
    final_root: Path | None = None,
    now: datetime | None = None,
) -> dict:
    workspace = workspace.expanduser().resolve()
    now = now or datetime.now().astimezone()
    keyword = sanitize_keyword(keyword)

    temp_root = (workspace / "works" / "tmp").resolve()
    final_root = (final_root or workspace / "works" / "research").expanduser().resolve()
    ensure_within(temp_root, workspace)
    ensure_within(final_root, workspace)

    task_dir = (temp_root / f"{now:%Y%m%d%H}-{keyword}").resolve()
    final_dir = (final_root / f"{now:%Y%m%d-%H%M%S}-{keyword}").resolve()
    ensure_within(task_dir, temp_root)
    ensure_within(final_dir, final_root)

    marker = task_dir / ".deep-research.json"
    if task_dir.exists() and not marker.exists():
        raise FileExistsError(
            f"Refusing to reuse non-research directory: {task_dir}. "
            "Choose a different keyword or hour."
        )
    if marker.exists():
        with marker.open("r", encoding="utf-8-sig") as handle:
            existing = json.load(handle)
        if existing.get("keyword") != keyword:
            raise FileExistsError(f"Workspace marker does not match keyword: {task_dir}")
        return existing

    task_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=False)
    for name in ("raw", "notes", "chapters", "records"):
        (task_dir / name).mkdir(exist_ok=True)

    metadata = {
        "schema_version": 1,
        "created_at": now.isoformat(timespec="seconds"),
        "keyword": keyword,
        "mode": mode,
        "language": lang,
        "workspace": str(workspace),
        "task_dir": str(task_dir),
        "final_dir": str(final_dir),
        "paths": {
            "outline": str(task_dir / "outline.json"),
            "ledger": str(task_dir / "evidence.jsonl"),
            "datapool": str(task_dir / "data-pool.json"),
            "manifest": str(task_dir / "manifest.json"),
            "report": str(final_dir / "report.md"),
        },
    }
    atomic_json(marker, metadata)
    return metadata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create an isolated workspace under works/tmp and works/research."
    )
    parser.add_argument("--workspace", required=True, help="Project workspace root")
    parser.add_argument("--keyword", required=True, help="Task keyword; sanitized to 6 characters")
    parser.add_argument("--mode", choices=MODES, default="standard")
    parser.add_argument("--lang", default="zh")
    parser.add_argument(
        "--final-root",
        default=None,
        help="Optional final output root; it must remain inside the workspace",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = create_workspace(
            workspace=Path(args.workspace),
            keyword=args.keyword,
            mode=args.mode,
            lang=args.lang,
            final_root=Path(args.final_root) if args.final_root else None,
        )
    except (OSError, ValueError) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"passed": True, **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
