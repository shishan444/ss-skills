#!/usr/bin/env python3
"""Validate, merge, summarize, and export deep-research evidence records."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SOURCE_ROLES = {"primary", "secondary", "discovery", "local"}
EXTRACTION_METHODS = {"curl", "web-chrome-dom", "web-chrome-gui", "local-file"}
CLAIM_KINDS = {"fact", "opinion"}
DATA_TYPES = {"actual", "estimate", "forecast", "opinion"}
CONFIDENCE_LEVELS = {"high", "medium", "low"}
SUPPORT_LEVELS = {"direct", "indirect", "context"}
ACCESS_STATUSES = {"verified", "partial", "blocked", "not_relevant"}
PRIORITIES = {"high", "medium", "low"}
TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "source",
}


def canonicalize_url(value: str) -> str:
    value = (value or "").strip()
    parts = urlsplit(value)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        raise ValueError("source_url must be an absolute http(s) URL")
    host = (parts.hostname or "").lower()
    if parts.port and not (
        (parts.scheme.lower() == "http" and parts.port == 80)
        or (parts.scheme.lower() == "https" and parts.port == 443)
    ):
        host = f"{host}:{parts.port}"
    query = []
    for key, val in parse_qsl(parts.query, keep_blank_values=True):
        key_lower = key.lower()
        if key_lower.startswith("utm_") or key_lower in TRACKING_PARAMS:
            continue
        query.append((key, val))
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), host, path, urlencode(query), ""))


def normalized_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def stable_id(*parts: str) -> str:
    material = "\x1f".join(parts).encode("utf-8")
    return "ev_" + hashlib.sha256(material).hexdigest()[:16]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, path)


def atomic_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    os.replace(tmp, path)


def load_ledger(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {line_no}: invalid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"line {line_no}: record must be a JSON object")
            records.append(value)
    return records


def _valid_iso_datetime(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except (TypeError, ValueError):
        return False


def validate_record(record: dict, index: int | None = None) -> list[str]:
    prefix = f"record {index}" if index is not None else "record"
    issues = []
    source_url = normalized_text(record.get("source_url"))
    local_path = normalized_text(record.get("local_path"))
    if bool(source_url) == bool(local_path):
        issues.append(f"{prefix}: exactly one of source_url or local_path is required")
    if source_url:
        try:
            canonicalize_url(source_url)
        except ValueError as exc:
            issues.append(f"{prefix}: {exc}")
    for field in ("title", "publisher", "retrieved_at"):
        if not normalized_text(record.get(field)):
            issues.append(f"{prefix}: missing non-empty field '{field}'")
    retrieved_at = normalized_text(record.get("retrieved_at"))
    if retrieved_at and not _valid_iso_datetime(retrieved_at):
        issues.append(f"{prefix}: retrieved_at must be ISO 8601")
    role = record.get("source_role")
    if role not in SOURCE_ROLES:
        issues.append(f"{prefix}: source_role must be one of {sorted(SOURCE_ROLES)}")
    method = record.get("extraction_method")
    if method not in EXTRACTION_METHODS:
        issues.append(
            f"{prefix}: extraction_method must be one of {sorted(EXTRACTION_METHODS)}"
        )
    if local_path and role != "local":
        issues.append(f"{prefix}: local_path records must use source_role='local'")
    if local_path and method != "local-file":
        issues.append(f"{prefix}: local_path records must use extraction_method='local-file'")
    access_status = record.get("access_status")
    if access_status not in ACCESS_STATUSES:
        issues.append(
            f"{prefix}: access_status must be one of {sorted(ACCESS_STATUSES)}"
        )
    failure_reason = normalized_text(record.get("failure_reason"))
    if access_status in {"partial", "blocked"} and not failure_reason:
        issues.append(f"{prefix}: {access_status} access requires failure_reason")

    questions = record.get("research_questions")
    if not isinstance(questions, list) or not all(normalized_text(q) for q in questions):
        issues.append(f"{prefix}: research_questions must be a non-empty string list")
    elif not questions:
        issues.append(f"{prefix}: research_questions must not be empty")

    claims = record.get("claims")
    if not isinstance(claims, list):
        issues.append(f"{prefix}: claims must be a list")
        return issues
    if access_status in {"blocked", "not_relevant"} and claims:
        issues.append(f"{prefix}: {access_status} records must not contain claims")
    for claim_index, claim in enumerate(claims):
        cp = f"{prefix} claim {claim_index}"
        if not isinstance(claim, dict):
            issues.append(f"{cp}: claim must be an object")
            continue
        statement = normalized_text(claim.get("statement"))
        locator = normalized_text(claim.get("locator"))
        if not statement:
            issues.append(f"{cp}: statement is required")
        if not locator:
            issues.append(f"{cp}: locator is required")
        if claim.get("kind") not in CLAIM_KINDS:
            issues.append(f"{cp}: kind must be one of {sorted(CLAIM_KINDS)}")
        if claim.get("data_type") not in DATA_TYPES:
            issues.append(f"{cp}: data_type must be one of {sorted(DATA_TYPES)}")
        if claim.get("confidence") not in CONFIDENCE_LEVELS:
            issues.append(f"{cp}: confidence must be one of {sorted(CONFIDENCE_LEVELS)}")
        if claim.get("support") not in SUPPORT_LEVELS:
            issues.append(f"{cp}: support must be one of {sorted(SUPPORT_LEVELS)}")
        if claim.get("kind") == "opinion" and claim.get("data_type") != "opinion":
            issues.append(f"{cp}: opinion claims must use data_type='opinion'")
        if role == "discovery" and claim.get("confidence") == "high":
            issues.append(f"{cp}: discovery sources cannot yield high-confidence claims")

        quote = normalized_text(claim.get("quote"))
        if len(quote) > 1200:
            issues.append(f"{cp}: quote is too long; keep only the minimum verification excerpt")

        has_numeric_value = normalized_text(claim.get("value")) != ""
        if has_numeric_value:
            for field in ("metric", "unit", "period", "scope"):
                if not normalized_text(claim.get(field)):
                    issues.append(f"{cp}: numeric claim is missing '{field}'")
        contradicts = claim.get("contradicts", [])
        if not isinstance(contradicts, list):
            issues.append(f"{cp}: contradicts must be a list")
    return issues


def normalize_record(record: dict) -> dict:
    normalized = dict(record)
    if normalized_text(record.get("source_url")):
        normalized["source_url"] = canonicalize_url(record["source_url"])
        normalized["local_path"] = ""
        source_key = normalized["source_url"]
    else:
        normalized["source_url"] = ""
        normalized["local_path"] = normalized_text(record.get("local_path"))
        source_key = normalized["local_path"]
    for field in (
        "title",
        "publisher",
        "published_at",
        "retrieved_at",
        "failure_reason",
    ):
        normalized[field] = normalized_text(record.get(field))
    normalized["research_questions"] = sorted(
        set(normalized_text(q) for q in record.get("research_questions", []) if normalized_text(q))
    )
    normalized_claims = []
    for claim in record.get("claims", []):
        item = dict(claim)
        for field in (
            "statement",
            "metric",
            "value",
            "unit",
            "period",
            "scope",
            "locator",
            "quote",
        ):
            item[field] = normalized_text(claim.get(field))
        item["contradicts"] = sorted(
            set(normalized_text(value) for value in claim.get("contradicts", []) if normalized_text(value))
        )
        item["evidence_id"] = stable_id(source_key, item["locator"], item["statement"])
        normalized_claims.append(item)
    normalized["claims"] = normalized_claims
    normalized["source_id"] = stable_id(source_key)
    return normalized


def source_key(record: dict) -> str:
    return record.get("source_url") or record.get("local_path") or ""


def claim_key(claim: dict) -> tuple[str, str]:
    return (normalized_text(claim.get("statement")), normalized_text(claim.get("locator")))


def merge_record(existing: dict, incoming: dict) -> dict:
    merged = dict(existing)
    merged["research_questions"] = sorted(
        set(existing.get("research_questions", []))
        | set(incoming.get("research_questions", []))
    )
    claims_by_key = {claim_key(claim): dict(claim) for claim in existing.get("claims", [])}
    for claim in incoming.get("claims", []):
        key = claim_key(claim)
        if key not in claims_by_key:
            claims_by_key[key] = claim
            continue
        current = claims_by_key[key]
        current["contradicts"] = sorted(
            set(current.get("contradicts", [])) | set(claim.get("contradicts", []))
        )
    merged["claims"] = sorted(
        claims_by_key.values(), key=lambda item: item.get("evidence_id", "")
    )
    if incoming.get("retrieved_at", "") > existing.get("retrieved_at", ""):
        merged["retrieved_at"] = incoming["retrieved_at"]
    for field in ("title", "publisher", "published_at"):
        if not merged.get(field) and incoming.get(field):
            merged[field] = incoming[field]
    return merged


def ledger_stats(records: list[dict]) -> dict:
    claims = [claim for record in records for claim in record.get("claims", [])]
    domains = set()
    publishers = set()
    for record in records:
        if record.get("source_url"):
            domains.add(urlsplit(record["source_url"]).hostname or "")
        publishers.add(normalized_text(record.get("publisher")).lower())
    return {
        "record_count": len(records),
        "claim_count": len(claims),
        "unique_domains": len({domain for domain in domains if domain}),
        "unique_publishers": len({publisher for publisher in publishers if publisher}),
        "source_roles": dict(Counter(record.get("source_role", "unknown") for record in records)),
        "extraction_methods": dict(
            Counter(record.get("extraction_method", "unknown") for record in records)
        ),
        "data_types": dict(Counter(claim.get("data_type", "unknown") for claim in claims)),
        "confidence": dict(Counter(claim.get("confidence", "unknown") for claim in claims)),
        "access_status": dict(
            Counter(record.get("access_status", "unknown") for record in records)
        ),
        "blocked_sources": [
            {
                "title": normalized_text(record.get("title")),
                "url": record.get("source_url") or "",
                "failure_reason": normalized_text(record.get("failure_reason")),
            }
            for record in records
            if record.get("access_status") == "blocked"
        ],
    }


def flatten_questions(outline: dict) -> list[dict]:
    result = []
    seen_ids = set()
    sequential = 1
    for chapter_index, chapter in enumerate(outline.get("chapters", []), 1):
        for question in chapter.get("sub_questions", []):
            if isinstance(question, str):
                question = {"question": question}
            qid = normalized_text(question.get("id")) or f"q{sequential}"
            sequential += 1
            if qid in seen_ids:
                raise ValueError(f"outline contains duplicate question id: {qid}")
            seen_ids.add(qid)
            priority = question.get("priority", "medium")
            if priority not in PRIORITIES:
                raise ValueError(f"question {qid}: invalid priority '{priority}'")
            result.append(
                {
                    "id": qid,
                    "question": normalized_text(question.get("question")),
                    "priority": priority,
                    "coverage_exception": normalized_text(question.get("coverage_exception")),
                    "chapter": chapter_index,
                }
            )
    if not result:
        raise ValueError("outline has no sub_questions")
    return result


def source_identity(record: dict) -> str:
    publisher = normalized_text(record.get("publisher")).lower()
    if publisher:
        return "publisher:" + publisher
    if record.get("source_url"):
        return "domain:" + (urlsplit(record["source_url"]).hostname or "").lower()
    return "local:" + normalized_text(record.get("local_path")).lower()


def _year_for_claim(record: dict, claim: dict) -> str:
    for candidate in (claim.get("period"), record.get("published_at")):
        match = re.search(r"(19|20)\d{2}", normalized_text(candidate))
        if match:
            return match.group(0)
    return ""


def fact_from_claim(record: dict, claim: dict) -> dict:
    statement = normalized_text(claim.get("statement"))
    numeric = normalized_text(claim.get("value")) != ""
    return {
        "src": normalized_text(record.get("publisher")),
        "yr": _year_for_claim(record, claim),
        "met": normalized_text(claim.get("metric")) or (
            "来源观点" if claim.get("kind") == "opinion" else "事实主张"
        ),
        "val": normalized_text(claim.get("value")) or statement,
        "u": normalized_text(claim.get("unit")) if numeric else "不适用",
        "ctx": normalized_text(claim.get("scope")) or statement,
        "url": record.get("source_url") or "",
        "local_path": record.get("local_path") or "",
        "title": normalized_text(record.get("title")),
        "conf": claim.get("confidence"),
        "data_type": claim.get("data_type"),
        "source_role": record.get("source_role"),
        "support": claim.get("support"),
        "evidence_id": claim.get("evidence_id"),
        "locator": normalized_text(claim.get("locator")),
        "quote": normalized_text(claim.get("quote")),
        "contradicts": claim.get("contradicts", []),
    }


def export_datapool(records: list[dict], outline: dict, profile: dict) -> tuple[list[dict], dict]:
    questions = flatten_questions(outline)
    known_question_ids = {question["id"] for question in questions}
    unknown_question_ids = sorted(
        {
            qid
            for record in records
            for qid in record.get("research_questions", [])
            if qid not in known_question_ids
        }
    )
    if unknown_question_ids:
        raise ValueError(
            "ledger references unknown outline question ids: "
            + ", ".join(unknown_question_ids)
        )
    by_question = defaultdict(list)
    for record in records:
        for qid in record.get("research_questions", []):
            by_question[qid].append(record)

    datapool = []
    coverage_counts = Counter()
    for question in questions:
        qid = question["id"]
        related = by_question.get(qid, [])
        facts = []
        identities = set()
        publishers = set()
        for record in related:
            usable_claims = record.get("claims", [])
            if record.get("source_role") != "discovery" and usable_claims:
                identities.add(source_identity(record))
            if record.get("publisher"):
                publishers.add(record["publisher"])
            facts.extend(fact_from_claim(record, claim) for claim in usable_claims)

        minimum = (
            int(profile.get("high_priority_min_sources", 2))
            if question["priority"] == "high"
            else 1
        )
        exception = question.get("coverage_exception")
        if facts and (len(identities) >= minimum or (exception and len(identities) >= 1)):
            status = "supported"
            gaps = []
        elif facts:
            status = "insufficient"
            gaps = [
                f"仅有 {len(identities)} 个可独立计数的来源，当前要求 {minimum} 个"
            ]
        else:
            status = "insufficient"
            gaps = ["未获得可引用证据"]
        if exception:
            gaps.append(f"覆盖例外：{exception}")
        coverage_counts[status] += 1
        datapool.append(
            {
                "question_id": qid,
                "question": question["question"],
                "priority": question["priority"],
                "chapter": question["chapter"],
                "src": sorted(publishers),
                "facts": facts,
                "gaps": gaps,
                "coverage_status": status,
                "independent_source_count": len(identities),
            }
        )

    total = len(datapool)
    insufficient = coverage_counts["insufficient"]
    high_total = sum(1 for item in datapool if item["priority"] == "high")
    high_supported = sum(
        1
        for item in datapool
        if item["priority"] == "high" and item["coverage_status"] == "supported"
    )
    stats = ledger_stats(records)
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": outline.get("mode", "standard"),
        "language": outline.get("language", "zh"),
        **stats,
        "fact_count": sum(len(item["facts"]) for item in datapool),
        "coverage": {
            "total_questions": total,
            "supported": coverage_counts["supported"],
            "insufficient": insufficient,
            "high_priority_total": high_total,
            "high_priority_supported": high_supported,
            "ratio": round(coverage_counts["supported"] / total, 3) if total else 0,
        },
        "insufficient_count": insufficient,
        "data_limited": bool(total and insufficient / total >= 1 / 3),
    }
    return datapool, manifest


def load_profiles() -> dict:
    path = Path(__file__).resolve().parent.parent / "profiles.json"
    return load_json(path)


def read_record_argument(value: str) -> dict:
    if value == "-":
        raw = sys.stdin.read()
        record = json.loads(raw)
    else:
        record = load_json(Path(value))
    if not isinstance(record, dict):
        raise ValueError("record input must be a JSON object")
    return record


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deep research evidence ledger")
    sub = parser.add_subparsers(dest="command", required=True)

    command = sub.add_parser("init", help="Create an empty ledger if it does not exist")
    command.add_argument("ledger")

    command = sub.add_parser("add", help="Validate and merge a source record")
    command.add_argument("ledger")
    command.add_argument("--record", required=True, help="JSON file, or - for stdin")

    command = sub.add_parser("validate", help="Validate every ledger record")
    command.add_argument("ledger")

    command = sub.add_parser("stats", help="Summarize ledger contents")
    command.add_argument("ledger")

    command = sub.add_parser("export-datapool", help="Export data-pool and manifest")
    command.add_argument("ledger")
    command.add_argument("--outline", required=True)
    command.add_argument("--mode", choices=("quick", "standard", "deep"), required=True)
    command.add_argument("--output", required=True)
    command.add_argument("--manifest", required=True)
    return parser


def emit(result: dict, passed: bool = True) -> int:
    print(json.dumps({"passed": passed, **result}, ensure_ascii=False, indent=2))
    return 0 if passed else 1


def main() -> int:
    args = build_parser().parse_args()
    ledger_path = Path(args.ledger)
    try:
        if args.command == "init":
            if ledger_path.exists():
                records = load_ledger(ledger_path)
                return emit({"ledger": str(ledger_path), **ledger_stats(records)})
            atomic_jsonl(ledger_path, [])
            return emit({"ledger": str(ledger_path), **ledger_stats([])})

        records = load_ledger(ledger_path)
        if args.command == "add":
            incoming_raw = read_record_argument(args.record)
            issues = validate_record(incoming_raw)
            if issues:
                return emit({"issues": issues}, passed=False)
            incoming = normalize_record(incoming_raw)
            by_source = {source_key(record): record for record in records}
            key = source_key(incoming)
            action = "merged" if key in by_source else "added"
            by_source[key] = (
                merge_record(by_source[key], incoming) if key in by_source else incoming
            )
            result_records = sorted(by_source.values(), key=source_key)
            atomic_jsonl(ledger_path, result_records)
            return emit(
                {
                    "action": action,
                    "source_id": by_source[key]["source_id"],
                    **ledger_stats(result_records),
                }
            )

        if args.command == "validate":
            issues = []
            for index, record in enumerate(records):
                issues.extend(validate_record(record, index))
            return emit(
                {"issues": issues, **ledger_stats(records)}, passed=not issues
            )

        if args.command == "stats":
            return emit(ledger_stats(records))

        if args.command == "export-datapool":
            issues = []
            for index, record in enumerate(records):
                issues.extend(validate_record(record, index))
            if issues:
                return emit({"issues": issues}, passed=False)
            outline = load_json(Path(args.outline))
            profiles = load_profiles()
            profile = profiles[args.mode]
            outline["mode"] = args.mode
            datapool, manifest = export_datapool(records, outline, profile)
            atomic_json(Path(args.output), datapool)
            atomic_json(Path(args.manifest), manifest)
            return emit(
                {
                    "output": args.output,
                    "manifest": args.manifest,
                    "record_count": manifest["record_count"],
                    "fact_count": manifest["fact_count"],
                    "coverage": manifest["coverage"],
                }
            )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return emit({"issues": [str(exc)]}, passed=False)
    return emit({"issues": ["unknown command"]}, passed=False)


if __name__ == "__main__":
    sys.exit(main())
