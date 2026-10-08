#!/usr/bin/env python3
"""Validate an analyze-news research packet without external dependencies."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


CLAIM_STATUSES = {"confirmed", "source_claim", "inference", "disputed", "unknown"}
SOURCE_ROLES = {"original", "official", "independent", "stakeholder", "background"}
USE_STATUSES = {"decisive", "supporting", "position", "blocked"}
TIMELINE_PHASES = {"before", "trigger", "current"}
IMPACT_LEVELS = {"direct", "adjacent", "system"}
IMPACT_STATUSES = {"evidence_based", "inferred", "uncertain", "not_applicable"}


class PacketValidator:
    def __init__(self, data: Any, phase: str) -> None:
        self.data = data
        self.phase = phase
        self.errors: list[str] = []
        self.claims: dict[str, dict[str, Any]] = {}
        self.evidence: dict[str, dict[str, Any]] = {}

    def error(self, path: str, message: str) -> None:
        self.errors.append(f"{path}: {message}")

    def object(self, value: Any, path: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            self.error(path, "must be an object")
            return {}
        return value

    def array(self, value: Any, path: str) -> list[Any]:
        if not isinstance(value, list):
            self.error(path, "must be an array")
            return []
        return value

    def text(self, value: Any, path: str, *, nonempty: bool = True) -> str:
        if not isinstance(value, str):
            self.error(path, "must be a string")
            return ""
        if nonempty and not value.strip():
            self.error(path, "must not be empty")
        return value

    def string_list(self, value: Any, path: str, *, nonempty: bool = False) -> list[str]:
        values = self.array(value, path)
        result: list[str] = []
        for index, item in enumerate(values):
            text = self.text(item, f"{path}[{index}]")
            if text:
                result.append(text)
        if nonempty and not result:
            self.error(path, "must not be empty")
        if len(result) != len(set(result)):
            self.error(path, "must not contain duplicates")
        return result

    def id_map(self, values: list[Any], path: str) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for index, raw in enumerate(values):
            item_path = f"{path}[{index}]"
            item = self.object(raw, item_path)
            item_id = self.text(item.get("id"), f"{item_path}.id")
            if item_id in result:
                self.error(f"{item_path}.id", f"duplicate id {item_id!r}")
            elif item_id:
                result[item_id] = item
        return result

    def refs(self, values: Any, known: dict[str, Any], path: str, *, nonempty: bool = False) -> list[str]:
        refs = self.string_list(values, path, nonempty=nonempty)
        for index, ref in enumerate(refs):
            if ref not in known:
                self.error(f"{path}[{index}]", f"unknown reference {ref!r}")
        return refs

    def validate(self) -> None:
        root = self.object(self.data, "$")
        required = {
            "schema_version", "subject", "workflow", "article", "claims", "evidence",
            "timeline", "viewpoints", "analysis", "gaps", "search", "completion"
        }
        for key in sorted(required - set(root)):
            self.error(f"$.{key}", "missing required field")
        if root.get("schema_version") != "1.0":
            self.error("$.schema_version", "must be '1.0'")

        subject = self.object(root.get("subject"), "$.subject")
        for key in ("title", "question", "input_url", "as_of"):
            self.text(subject.get(key), f"$.subject.{key}", nonempty=False)

        workflow = self.object(root.get("workflow"), "$.workflow")
        for key in ("phase", "research_status", "analysis_status"):
            self.text(workflow.get(key), f"$.workflow.{key}")
        followups = workflow.get("followup_rounds")
        if not isinstance(followups, int) or isinstance(followups, bool) or followups not in {0, 1}:
            self.error("$.workflow.followup_rounds", "must be integer 0 or 1")
        recoveries = workflow.get("delivery_recoveries")
        if not isinstance(recoveries, int) or isinstance(recoveries, bool) or recoveries not in {0, 1}:
            self.error("$.workflow.delivery_recoveries", "must be integer 0 or 1")

        article = self.object(root.get("article"), "$.article")
        for key in ("url", "title", "publisher", "published_at", "access_status"):
            self.text(article.get(key), f"$.article.{key}", nonempty=False)
        if article.get("access_status") not in {"unknown", "accessible", "blocked"}:
            self.error("$.article.access_status", "must be unknown, accessible, or blocked")

        claim_values = self.array(root.get("claims"), "$.claims")
        evidence_values = self.array(root.get("evidence"), "$.evidence")
        self.claims = self.id_map(claim_values, "$.claims")
        self.evidence = self.id_map(evidence_values, "$.evidence")
        self.validate_claims(claim_values)
        self.validate_evidence(evidence_values)
        self.validate_timeline(self.array(root.get("timeline"), "$.timeline"))
        self.validate_gaps(self.array(root.get("gaps"), "$.gaps"))
        self.validate_search(self.object(root.get("search"), "$.search"))

        if self.phase in {"research", "final"}:
            self.validate_research_ready(root)
        if self.phase == "final":
            self.validate_final_ready(root)

    def validate_claims(self, values: list[Any]) -> None:
        for index, raw in enumerate(values):
            path = f"$.claims[{index}]"
            item = self.object(raw, path)
            self.text(item.get("statement"), f"{path}.statement")
            self.text(item.get("kind"), f"{path}.kind")
            status = self.text(item.get("status"), f"{path}.status")
            if status and status not in CLAIM_STATUSES:
                self.error(f"{path}.status", f"unknown status {status!r}")
            if not isinstance(item.get("material"), bool):
                self.error(f"{path}.material", "must be boolean")
            evidence_ids = self.refs(item.get("evidence_ids"), self.evidence, f"{path}.evidence_ids")
            self.text(item.get("limits"), f"{path}.limits", nonempty=False)
            if item.get("material") and (status == "unknown" or not evidence_ids):
                self.error(path, "material claim must be non-unknown and evidence-backed")
            claim_id = item.get("id")
            for evidence_id in evidence_ids:
                if claim_id not in self.evidence.get(evidence_id, {}).get("claim_ids", []):
                    self.error(f"{path}.evidence_ids", f"evidence {evidence_id!r} lacks back-reference")

    def validate_evidence(self, values: list[Any]) -> None:
        adopted_urls: dict[str, str] = {}
        for index, raw in enumerate(values):
            path = f"$.evidence[{index}]"
            item = self.object(raw, path)
            for key in ("url", "title", "publisher", "published_at", "source_role", "location", "use_status"):
                self.text(item.get(key), f"{path}.{key}", nonempty=key not in {"published_at"})
            role = item.get("source_role")
            use_status = item.get("use_status")
            if role not in SOURCE_ROLES:
                self.error(f"{path}.source_role", f"unknown role {role!r}")
            if use_status not in USE_STATUSES:
                self.error(f"{path}.use_status", f"unknown use status {use_status!r}")
            claim_ids = self.refs(item.get("claim_ids"), self.claims, f"{path}.claim_ids")
            evidence_id = item.get("id")
            for claim_id in claim_ids:
                if evidence_id not in self.claims.get(claim_id, {}).get("evidence_ids", []):
                    self.error(f"{path}.claim_ids", f"claim {claim_id!r} lacks back-reference")
            url = item.get("url")
            if use_status != "blocked" and isinstance(url, str) and url:
                if url in adopted_urls:
                    self.error(f"{path}.url", f"duplicate adopted URL also used by {adopted_urls[url]!r}")
                adopted_urls[url] = str(evidence_id)

    def validate_timeline(self, values: list[Any]) -> None:
        seen: set[str] = set()
        for index, raw in enumerate(values):
            path = f"$.timeline[{index}]"
            item = self.object(raw, path)
            phase = self.text(item.get("phase"), f"{path}.phase")
            if phase not in TIMELINE_PHASES:
                self.error(f"{path}.phase", f"unknown phase {phase!r}")
            for key in ("date", "event"):
                self.text(item.get(key), f"{path}.{key}")
            self.refs(item.get("claim_ids"), self.claims, f"{path}.claim_ids", nonempty=True)
            self.refs(item.get("evidence_ids"), self.evidence, f"{path}.evidence_ids", nonempty=True)
            seen.add(phase)
        if self.phase in {"research", "final"} and not TIMELINE_PHASES.issubset(seen):
            self.error("$.timeline", "must cover before, trigger, and current")

    def validate_gaps(self, values: list[Any]) -> None:
        self.id_map(values, "$.gaps")
        for index, raw in enumerate(values):
            path = f"$.gaps[{index}]"
            item = self.object(raw, path)
            for key in ("question", "materiality", "why_material", "suggested_query", "status"):
                self.text(item.get(key), f"{path}.{key}", nonempty=key != "suggested_query")
            if item.get("materiality") not in {"critical", "useful"}:
                self.error(f"{path}.materiality", "must be critical or useful")
            if item.get("status") not in {"open", "resolved", "accepted_unknown"}:
                self.error(f"{path}.status", "must be open, resolved, or accepted_unknown")

    def validate_search(self, search: dict[str, Any]) -> None:
        budget = search.get("source_budget")
        if not isinstance(budget, int) or isinstance(budget, bool) or not 1 <= budget <= 12:
            self.error("$.search.source_budget", "must be an integer between 1 and 12")
            budget = 12
        count = search.get("valid_source_count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            self.error("$.search.valid_source_count", "must be a non-negative integer")
            count = -1
        adopted = [item for item in self.evidence.values() if item.get("use_status") != "blocked"]
        if count != len(adopted):
            self.error("$.search.valid_source_count", f"must equal adopted evidence count {len(adopted)}")
        if isinstance(budget, int) and count > budget:
            self.error("$.search.valid_source_count", "must not exceed source_budget")
        if not isinstance(search.get("counter_search_done"), bool):
            self.error("$.search.counter_search_done", "must be boolean")
        batches = search.get("no_material_change_batches")
        if not isinstance(batches, int) or isinstance(batches, bool) or batches < 0:
            self.error("$.search.no_material_change_batches", "must be a non-negative integer")
        stop_reason = search.get("stop_reason")
        if stop_reason is not None and stop_reason not in {"converged", "budget_exhausted", "access_blocked", "insufficient"}:
            self.error("$.search.stop_reason", f"unknown stop reason {stop_reason!r}")

    def validate_research_ready(self, root: dict[str, Any]) -> None:
        workflow = root.get("workflow", {})
        article = root.get("article", {})
        search = root.get("search", {})
        if workflow.get("research_status") != "complete":
            self.error("$.workflow.research_status", "research phase requires complete")
        if article.get("access_status") != "accessible":
            self.error("$.article.access_status", "research phase requires accessible input article")
        adopted = [item for item in self.evidence.values() if item.get("use_status") != "blocked"]
        if len(adopted) < 3:
            self.error("$.evidence", "research phase requires at least 3 valid sources")
        roles = {item.get("source_role") for item in adopted}
        if not roles.intersection({"original", "official"}):
            self.error("$.evidence", "research phase requires an original or official source")
        if "independent" not in roles:
            self.error("$.evidence", "research phase requires an independent source")
        if not self.claims or not any(item.get("material") for item in self.claims.values()):
            self.error("$.claims", "research phase requires at least one material claim")
        if search.get("counter_search_done") is not True:
            self.error("$.search.counter_search_done", "research phase requires counter-search")
        if not isinstance(search.get("no_material_change_batches"), int) or search.get("no_material_change_batches", 0) < 2:
            self.error("$.search.no_material_change_batches", "research phase requires two converged batches")
        if search.get("stop_reason") != "converged":
            self.error("$.search.stop_reason", "research phase can complete only with converged")
        for index, gap in enumerate(root.get("gaps", [])):
            if gap.get("materiality") == "critical" and gap.get("status") == "open":
                self.error(f"$.gaps[{index}]", "open critical gap blocks research completion")

    def validate_final_ready(self, root: dict[str, Any]) -> None:
        workflow = root.get("workflow", {})
        if workflow.get("analysis_status") != "complete":
            self.error("$.workflow.analysis_status", "final phase requires complete")

        viewpoints = self.array(root.get("viewpoints"), "$.viewpoints")
        if not viewpoints:
            self.error("$.viewpoints", "final phase requires at least one viewpoint")
        for index, raw in enumerate(viewpoints):
            path = f"$.viewpoints[{index}]"
            item = self.object(raw, path)
            self.text(item.get("id"), f"{path}.id")
            for key in ("holder", "conclusion", "status"):
                self.text(item.get(key), f"{path}.{key}")
            steps = self.array(item.get("causal_steps"), f"{path}.causal_steps")
            if not steps:
                self.error(f"{path}.causal_steps", "must not be empty")
            for step_index, raw_step in enumerate(steps):
                step = self.object(raw_step, f"{path}.causal_steps[{step_index}]")
                for key in ("from", "mechanism", "to"):
                    self.text(step.get(key), f"{path}.causal_steps[{step_index}].{key}")
            self.string_list(item.get("conditions"), f"{path}.conditions", nonempty=True)
            self.refs(item.get("evidence_ids"), self.evidence, f"{path}.evidence_ids", nonempty=True)
            self.refs(item.get("counterevidence_ids"), self.evidence, f"{path}.counterevidence_ids")

        analysis = self.object(root.get("analysis"), "$.analysis")
        nature = self.object(analysis.get("nature"), "$.analysis.nature")
        self.text(nature.get("statement"), "$.analysis.nature.statement")
        if nature.get("status") not in CLAIM_STATUSES - {"unknown"}:
            self.error("$.analysis.nature.status", "must be a non-unknown claim status")
        self.refs(nature.get("claim_ids"), self.claims, "$.analysis.nature.claim_ids", nonempty=True)

        chains = self.array(analysis.get("causal_chains"), "$.analysis.causal_chains")
        if not chains:
            self.error("$.analysis.causal_chains", "final phase requires a causal chain")
        for index, raw in enumerate(chains):
            path = f"$.analysis.causal_chains[{index}]"
            item = self.object(raw, path)
            for key in ("id", "cause", "outcome", "status"):
                self.text(item.get(key), f"{path}.{key}")
            self.string_list(item.get("mechanism_steps"), f"{path}.mechanism_steps", nonempty=True)
            self.string_list(item.get("conditions"), f"{path}.conditions", nonempty=True)
            self.refs(item.get("evidence_ids"), self.evidence, f"{path}.evidence_ids", nonempty=True)
            self.refs(item.get("counterevidence_ids"), self.evidence, f"{path}.counterevidence_ids")

        impacts = self.array(analysis.get("impacts"), "$.analysis.impacts")
        levels: set[str] = set()
        for index, raw in enumerate(impacts):
            path = f"$.analysis.impacts[{index}]"
            item = self.object(raw, path)
            level = self.text(item.get("level"), f"{path}.level")
            status = self.text(item.get("status"), f"{path}.status")
            if level not in IMPACT_LEVELS:
                self.error(f"{path}.level", f"unknown level {level!r}")
            if status not in IMPACT_STATUSES:
                self.error(f"{path}.status", f"unknown status {status!r}")
            levels.add(level)
            for key in ("subject", "direction", "mechanism", "horizon"):
                self.text(item.get(key), f"{path}.{key}")
            refs = self.refs(item.get("evidence_ids"), self.evidence, f"{path}.evidence_ids")
            signals = self.string_list(item.get("signals"), f"{path}.signals")
            if status != "not_applicable" and not refs:
                self.error(f"{path}.evidence_ids", "applicable impact must have an evidence anchor")
            if status in {"inferred", "uncertain"} and not signals:
                self.error(f"{path}.signals", "future or uncertain impact requires observable signals")
            if level == "direct" and status == "not_applicable":
                self.error(path, "direct impact cannot be not_applicable")
        if not IMPACT_LEVELS.issubset(levels):
            self.error("$.analysis.impacts", "must cover direct, adjacent, and system")

        completion = self.object(root.get("completion"), "$.completion")
        if completion.get("status") != "complete":
            self.error("$.completion.status", "final phase requires complete")
        self.text(completion.get("reason"), "$.completion.reason")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("--phase", choices=("structure", "research", "final"), default="structure")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        data = json.loads(args.packet.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"ERROR: packet not found: {args.packet}", file=sys.stderr)
        return 2
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read packet: {exc}", file=sys.stderr)
        return 2

    validator = PacketValidator(data, args.phase)
    validator.validate()
    for error in validator.errors:
        print(f"ERROR: {error}")
    if validator.errors:
        print(f"INVALID: {len(validator.errors)} error(s)", file=sys.stderr)
        return 1
    print(f"VALID: phase={args.phase}, claims={len(validator.claims)}, evidence={len(validator.evidence)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
