#!/usr/bin/env python3
"""Validate the unified JSON manifest produced by design-test-cases."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


LAYERS = {"L1", "L2", "L3"}
CATEGORIES = {"positive", "negative", "risk"}
READINESS = {"ready", "conditional", "blocked"}
GATE_STATUSES = {"draft", "approved", "blocked"}
DISPOSITIONS = {"cases", "not_applicable"}
RESPONSIBILITIES = {"primary", "reinforcement"}
PRIORITIES = {"critical", "high", "normal"}
LIFECYCLE_STATUSES = {
    "draft",
    "reviewed",
    "automated",
    "regression_active",
    "quarantined",
    "retired",
}
RUN_PROFILES = {"local", "pr", "scheduled", "release", "post_deploy", "exploration"}
TERMINAL_TYPES = {"success", "rejected", "failed", "recovered"}
OBLIGATION_TYPES = {
    "requirement",
    "rule",
    "state",
    "flow",
    "permission",
    "dependency",
    "interaction",
    "risk",
}
OBLIGATION_STATUSES = {"designed", "conditional", "blocked", "accepted", "not_applicable"}
STOP_DECISIONS = {"continue", "conditional_complete", "complete", "blocked"}
L3_MODES = {"regression", "exploration"}


class Validator:
    def __init__(self, data: Any) -> None:
        self.data = data
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.flow_element_owner: dict[str, dict[str, str]] = {
            "node_ids": {},
            "edge_ids": {},
            "terminal_ids": {},
            "side_effect_ids": {},
        }
        self.covered_flow_elements: dict[str, set[str]] = {
            "node_ids": set(),
            "edge_ids": set(),
            "terminal_ids": set(),
            "side_effect_ids": set(),
        }

    def error(self, path: str, message: str) -> None:
        self.errors.append(f"{path}: {message}")

    def warn(self, path: str, message: str) -> None:
        self.warnings.append(f"{path}: {message}")

    def require_dict(self, value: Any, path: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            self.error(path, "必须是 object")
            return {}
        return value

    def require_list(self, value: Any, path: str, *, nonempty: bool = False) -> list[Any]:
        if not isinstance(value, list):
            self.error(path, "必须是 array")
            return []
        if nonempty and not value:
            self.error(path, "不能为空")
        return value

    def require_string(self, value: Any, path: str, *, nonempty: bool = True) -> str:
        if not isinstance(value, str):
            self.error(path, "必须是 string")
            return ""
        if nonempty and not value.strip():
            self.error(path, "不能为空")
        return value

    def require_string_list(self, value: Any, path: str, *, nonempty: bool = False) -> list[str]:
        values = self.require_list(value, path, nonempty=nonempty)
        for index, item in enumerate(values):
            self.require_string(item, f"{path}[{index}]")
        return [item for item in values if isinstance(item, str)]

    def require_enum(self, value: Any, allowed: set[str], path: str) -> str:
        item = self.require_string(value, path)
        if item and item not in allowed:
            self.error(path, f"必须是 {sorted(allowed)} 之一，实际为 {item!r}")
        return item

    def required_keys(self, obj: dict[str, Any], path: str, keys: set[str]) -> None:
        for key in sorted(keys - set(obj)):
            self.error(f"{path}.{key}", "缺少必填字段")

    def unique_ids(self, items: list[Any], id_key: str, path: str) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for index, raw in enumerate(items):
            item_path = f"{path}[{index}]"
            item = self.require_dict(raw, item_path)
            item_id = self.require_string(item.get(id_key), f"{item_path}.{id_key}")
            if not item_id:
                continue
            if item_id in result:
                self.error(f"{item_path}.{id_key}", f"ID {item_id!r} 重复")
            else:
                result[item_id] = item
        return result

    def validate(self) -> None:
        root = self.require_dict(self.data, "$")
        if not root:
            return
        required = {
            "schema_version",
            "requirement",
            "design_gate",
            "strategy",
            "flow_models",
            "propositions",
            "coverage_obligations",
            "cases",
            "coverage_summary",
        }
        self.required_keys(root, "$", required)
        if root.get("schema_version") != "1.0":
            self.error("$.schema_version", "当前必须为 '1.0'")

        self.validate_requirement(root.get("requirement"))
        self.validate_design_gate(root.get("design_gate"))

        flows = self.require_list(root.get("flow_models"), "$.flow_models")
        propositions = self.require_list(root.get("propositions"), "$.propositions", nonempty=True)
        obligations = self.require_list(
            root.get("coverage_obligations"), "$.coverage_obligations", nonempty=True
        )
        cases = self.require_list(root.get("cases"), "$.cases", nonempty=True)

        flow_map = self.unique_ids(flows, "flow_id", "$.flow_models")
        proposition_map = self.unique_ids(propositions, "proposition_id", "$.propositions")
        obligation_map = self.unique_ids(obligations, "obligation_id", "$.coverage_obligations")
        case_map = self.unique_ids(cases, "case_id", "$.cases")

        self.validate_strategy(root.get("strategy"), cases)
        self.validate_flows(flows)
        self.validate_propositions(propositions)
        self.validate_obligations(obligations, proposition_map, case_map)
        self.validate_cases(cases, flow_map, proposition_map, obligation_map)
        self.validate_cross_links(proposition_map, obligation_map, case_map)
        self.validate_flow_coverage()
        self.validate_coverage_summary(root.get("coverage_summary"), obligation_map)

    def validate_requirement(self, raw: Any) -> None:
        path = "$.requirement"
        obj = self.require_dict(raw, path)
        self.required_keys(
            obj,
            path,
            {"title", "version", "source_ids", "readiness", "known_facts", "assumptions", "critical_unknowns"},
        )
        self.require_string(obj.get("title"), f"{path}.title")
        self.require_string(obj.get("version"), f"{path}.version")
        self.require_string_list(obj.get("source_ids"), f"{path}.source_ids", nonempty=True)
        self.require_enum(obj.get("readiness"), READINESS, f"{path}.readiness")
        facts = self.require_list(obj.get("known_facts"), f"{path}.known_facts", nonempty=True)
        self.unique_ids(facts, "fact_id", f"{path}.known_facts")
        for index, raw_fact in enumerate(facts):
            fact = self.require_dict(raw_fact, f"{path}.known_facts[{index}]")
            self.require_string(fact.get("statement"), f"{path}.known_facts[{index}].statement")
            self.require_string_list(
                fact.get("source_ids"), f"{path}.known_facts[{index}].source_ids", nonempty=True
            )
        self.require_list(obj.get("assumptions"), f"{path}.assumptions")
        self.require_list(obj.get("critical_unknowns"), f"{path}.critical_unknowns")

    def validate_design_gate(self, raw: Any) -> None:
        path = "$.design_gate"
        obj = self.require_dict(raw, path)
        self.required_keys(
            obj,
            path,
            {"status", "approval_required_before_implementation", "blocking_reasons", "approved_by"},
        )
        self.require_enum(obj.get("status"), GATE_STATUSES, f"{path}.status")
        if obj.get("approval_required_before_implementation") is not True:
            self.error(f"{path}.approval_required_before_implementation", "必须为 true")
        self.require_string_list(obj.get("blocking_reasons"), f"{path}.blocking_reasons")
        approved_by = obj.get("approved_by")
        if approved_by is not None:
            self.require_string(approved_by, f"{path}.approved_by")
        if obj.get("status") == "approved" and not approved_by:
            self.error(f"{path}.approved_by", "status 为 approved 时必须记录审批人")

    def validate_strategy(self, raw: Any, cases: list[Any]) -> None:
        path = "$.strategy"
        obj = self.require_dict(raw, path)
        self.required_keys(
            obj,
            path,
            {"protected_values", "scope_in", "scope_out", "layers", "categories", "run_profiles"},
        )
        self.require_string_list(obj.get("protected_values"), f"{path}.protected_values", nonempty=True)
        self.require_string_list(obj.get("scope_in"), f"{path}.scope_in", nonempty=True)
        self.require_string_list(obj.get("scope_out"), f"{path}.scope_out")
        self.validate_dispositions(obj.get("layers"), LAYERS, f"{path}.layers", cases, "layer")
        self.validate_dispositions(
            obj.get("categories"), CATEGORIES, f"{path}.categories", cases, "category"
        )
        profiles = self.require_string_list(obj.get("run_profiles"), f"{path}.run_profiles", nonempty=True)
        for index, profile in enumerate(profiles):
            if profile not in RUN_PROFILES:
                self.error(f"{path}.run_profiles[{index}]", f"未知运行档位 {profile!r}")

    def validate_dispositions(
        self,
        raw: Any,
        expected: set[str],
        path: str,
        cases: list[Any],
        case_key: str,
    ) -> None:
        obj = self.require_dict(raw, path)
        for key in sorted(expected):
            if key not in obj:
                self.error(f"{path}.{key}", "缺少处置")
                continue
            item = self.require_dict(obj[key], f"{path}.{key}")
            disposition = self.require_enum(
                item.get("disposition"), DISPOSITIONS, f"{path}.{key}.disposition"
            )
            rationale = self.require_string(item.get("rationale"), f"{path}.{key}.rationale")
            matching = [case for case in cases if isinstance(case, dict) and case.get(case_key) == key]
            if disposition == "cases" and not matching:
                self.error(f"{path}.{key}", "声明 cases 但没有对应测试用例")
            if disposition == "not_applicable" and matching:
                self.error(f"{path}.{key}", "声明 not_applicable 但存在对应测试用例")
            if disposition == "not_applicable" and len(rationale.strip()) < 8:
                self.warn(f"{path}.{key}.rationale", "不适用理由过短，可能无法审查")

    def validate_flows(self, flows: list[Any]) -> None:
        for index, raw in enumerate(flows):
            path = f"$.flow_models[{index}]"
            obj = self.require_dict(raw, path)
            self.required_keys(
                obj,
                path,
                {"flow_id", "name", "entry", "nodes", "edges", "terminal_states", "critical_side_effects"},
            )
            flow_id = self.require_string(obj.get("flow_id"), f"{path}.flow_id")
            self.require_string(obj.get("name"), f"{path}.name")
            self.require_string(obj.get("entry"), f"{path}.entry")
            nodes = self.require_list(obj.get("nodes"), f"{path}.nodes", nonempty=True)
            node_map = self.unique_ids(nodes, "node_id", f"{path}.nodes")
            for node_index, raw_node in enumerate(nodes):
                node_path = f"{path}.nodes[{node_index}]"
                node = self.require_dict(raw_node, node_path)
                self.required_keys(node, node_path, {"node_id", "state"})
                self.require_string(node.get("state"), f"{node_path}.state")
                self.register_flow_element("node_ids", node.get("node_id"), flow_id, f"{node_path}.node_id")
            edges = self.require_list(obj.get("edges"), f"{path}.edges", nonempty=True)
            self.unique_ids(edges, "edge_id", f"{path}.edges")
            for edge_index, raw_edge in enumerate(edges):
                edge_path = f"{path}.edges[{edge_index}]"
                edge = self.require_dict(raw_edge, edge_path)
                self.required_keys(edge, edge_path, {"edge_id", "from", "action", "guard", "to"})
                for key in ("from", "action", "guard", "to"):
                    self.require_string(edge.get(key), f"{edge_path}.{key}")
                self.register_flow_element("edge_ids", edge.get("edge_id"), flow_id, f"{edge_path}.edge_id")
                for key in ("from", "to"):
                    node_ref = edge.get(key)
                    if isinstance(node_ref, str) and node_ref not in node_map:
                        self.error(f"{edge_path}.{key}", f"引用不存在的当前流程节点 {node_ref!r}")
            terminals = self.require_list(
                obj.get("terminal_states"), f"{path}.terminal_states", nonempty=True
            )
            self.unique_ids(terminals, "terminal_id", f"{path}.terminal_states")
            for terminal_index, raw_terminal in enumerate(terminals):
                terminal_path = f"{path}.terminal_states[{terminal_index}]"
                terminal = self.require_dict(raw_terminal, terminal_path)
                self.required_keys(terminal, terminal_path, {"terminal_id", "state", "type"})
                self.require_string(terminal.get("state"), f"{terminal_path}.state")
                self.require_enum(terminal.get("type"), TERMINAL_TYPES, f"{terminal_path}.type")
                self.register_flow_element(
                    "terminal_ids", terminal.get("terminal_id"), flow_id, f"{terminal_path}.terminal_id"
                )
            effects = self.require_list(obj.get("critical_side_effects"), f"{path}.critical_side_effects")
            self.unique_ids(effects, "side_effect_id", f"{path}.critical_side_effects")
            for effect_index, raw_effect in enumerate(effects):
                effect_path = f"{path}.critical_side_effects[{effect_index}]"
                effect = self.require_dict(raw_effect, effect_path)
                self.required_keys(effect, effect_path, {"side_effect_id", "description"})
                self.require_string(effect.get("description"), f"{effect_path}.description")
                self.register_flow_element(
                    "side_effect_ids",
                    effect.get("side_effect_id"),
                    flow_id,
                    f"{effect_path}.side_effect_id",
                )

    def register_flow_element(self, kind: str, raw_id: Any, flow_id: str, path: str) -> None:
        element_id = self.require_string(raw_id, path)
        if not element_id:
            return
        existing = self.flow_element_owner[kind].get(element_id)
        if existing is not None:
            self.error(path, f"流程元素 ID {element_id!r} 已属于流程 {existing!r}")
            return
        self.flow_element_owner[kind][element_id] = flow_id

    def validate_propositions(self, propositions: list[Any]) -> None:
        for index, raw in enumerate(propositions):
            path = f"$.propositions[{index}]"
            obj = self.require_dict(raw, path)
            self.required_keys(
                obj,
                path,
                {"proposition_id", "source_ids", "context", "stimulus", "expected", "invariants", "risk_if_broken"},
            )
            self.require_string_list(obj.get("source_ids"), f"{path}.source_ids", nonempty=True)
            for key in ("context", "stimulus", "expected", "risk_if_broken"):
                self.require_string(obj.get(key), f"{path}.{key}")
            self.require_string_list(obj.get("invariants"), f"{path}.invariants")

    def validate_obligations(
        self,
        obligations: list[Any],
        proposition_map: dict[str, dict[str, Any]],
        case_map: dict[str, dict[str, Any]],
    ) -> None:
        for index, raw in enumerate(obligations):
            path = f"$.coverage_obligations[{index}]"
            obj = self.require_dict(raw, path)
            self.required_keys(
                obj,
                path,
                {
                    "obligation_id",
                    "source_ids",
                    "proposition_ids",
                    "type",
                    "description",
                    "protected_value",
                    "failure_mechanism",
                    "criticality",
                    "primary_layer",
                    "case_ids",
                    "status",
                    "residual_risk",
                },
            )
            self.require_string_list(obj.get("source_ids"), f"{path}.source_ids", nonempty=True)
            proposition_ids = self.require_string_list(
                obj.get("proposition_ids"), f"{path}.proposition_ids", nonempty=True
            )
            self.check_refs(proposition_ids, proposition_map, f"{path}.proposition_ids", "验证命题")
            self.require_enum(obj.get("type"), OBLIGATION_TYPES, f"{path}.type")
            for key in ("description", "protected_value", "failure_mechanism", "residual_risk"):
                self.require_string(obj.get(key), f"{path}.{key}", nonempty=(key != "residual_risk"))
            self.require_enum(obj.get("criticality"), PRIORITIES, f"{path}.criticality")
            self.require_enum(obj.get("primary_layer"), LAYERS, f"{path}.primary_layer")
            case_ids = self.require_string_list(obj.get("case_ids"), f"{path}.case_ids")
            self.check_refs(case_ids, case_map, f"{path}.case_ids", "测试用例")
            status = self.require_enum(obj.get("status"), OBLIGATION_STATUSES, f"{path}.status")
            if status == "designed" and not case_ids:
                self.error(f"{path}.case_ids", "status 为 designed 时不能为空")

    def validate_cases(
        self,
        cases: list[Any],
        flow_map: dict[str, dict[str, Any]],
        proposition_map: dict[str, dict[str, Any]],
        obligation_map: dict[str, dict[str, Any]],
    ) -> None:
        for index, raw in enumerate(cases):
            path = f"$.cases[{index}]"
            obj = self.require_dict(raw, path)
            self.required_keys(
                obj,
                path,
                {
                    "case_id",
                    "title",
                    "source_ids",
                    "proposition_ids",
                    "obligation_ids",
                    "layer",
                    "responsibility",
                    "category",
                    "priority",
                    "owner",
                    "lifecycle_status",
                    "intent",
                    "preconditions",
                    "stimulus",
                    "oracle",
                    "controls",
                    "cleanup",
                    "evidence",
                    "automation",
                    "layer_detail",
                },
            )
            self.require_string(obj.get("title"), f"{path}.title")
            self.require_string_list(obj.get("source_ids"), f"{path}.source_ids", nonempty=True)
            proposition_ids = self.require_string_list(
                obj.get("proposition_ids"), f"{path}.proposition_ids", nonempty=True
            )
            obligation_ids = self.require_string_list(
                obj.get("obligation_ids"), f"{path}.obligation_ids", nonempty=True
            )
            self.check_refs(proposition_ids, proposition_map, f"{path}.proposition_ids", "验证命题")
            self.check_refs(obligation_ids, obligation_map, f"{path}.obligation_ids", "覆盖义务")
            layer = self.require_enum(obj.get("layer"), LAYERS, f"{path}.layer")
            self.require_enum(obj.get("responsibility"), RESPONSIBILITIES, f"{path}.responsibility")
            self.require_enum(obj.get("category"), CATEGORIES, f"{path}.category")
            self.require_enum(obj.get("priority"), PRIORITIES, f"{path}.priority")
            self.require_string(obj.get("owner"), f"{path}.owner")
            self.require_enum(
                obj.get("lifecycle_status"), LIFECYCLE_STATUSES, f"{path}.lifecycle_status"
            )
            self.require_string(obj.get("intent"), f"{path}.intent")
            self.require_string_list(obj.get("preconditions"), f"{path}.preconditions", nonempty=True)
            self.require_string_list(obj.get("stimulus"), f"{path}.stimulus", nonempty=True)
            self.validate_oracle(obj.get("oracle"), f"{path}.oracle")
            self.validate_controls(obj.get("controls"), f"{path}.controls")
            self.require_string(obj.get("cleanup"), f"{path}.cleanup")
            self.require_string_list(obj.get("evidence"), f"{path}.evidence", nonempty=True)
            self.validate_automation(obj.get("automation"), f"{path}.automation")
            self.validate_layer_detail(obj.get("layer_detail"), layer, flow_map, f"{path}.layer_detail")

    def validate_oracle(self, raw: Any, path: str) -> None:
        obj = self.require_dict(raw, path)
        self.required_keys(obj, path, {"must", "must_not", "time_boundary"})
        self.require_string_list(obj.get("must"), f"{path}.must", nonempty=True)
        self.require_string_list(obj.get("must_not"), f"{path}.must_not")
        self.require_string(obj.get("time_boundary"), f"{path}.time_boundary")

    def validate_controls(self, raw: Any, path: str) -> None:
        obj = self.require_dict(raw, path)
        self.required_keys(obj, path, {"data", "dependencies", "time_randomness"})
        for key in ("data", "dependencies", "time_randomness"):
            self.require_string(obj.get(key), f"{path}.{key}")

    def validate_automation(self, raw: Any, path: str) -> None:
        obj = self.require_dict(raw, path)
        self.required_keys(obj, path, {"adapter", "entrypoint", "run_profiles", "deterministic"})
        self.require_string(obj.get("adapter"), f"{path}.adapter")
        self.require_string(obj.get("entrypoint"), f"{path}.entrypoint")
        profiles = self.require_string_list(obj.get("run_profiles"), f"{path}.run_profiles", nonempty=True)
        for index, profile in enumerate(profiles):
            if profile not in RUN_PROFILES:
                self.error(f"{path}.run_profiles[{index}]", f"未知运行档位 {profile!r}")
        if not isinstance(obj.get("deterministic"), bool):
            self.error(f"{path}.deterministic", "必须是 boolean")

    def validate_layer_detail(
        self,
        raw: Any,
        layer: str,
        flow_map: dict[str, dict[str, Any]],
        path: str,
    ) -> None:
        obj = self.require_dict(raw, path)
        if layer == "L1":
            self.required_keys(obj, path, {"unit_under_test", "rule_or_invariant", "test_doubles"})
            self.require_string(obj.get("unit_under_test"), f"{path}.unit_under_test")
            self.require_string(obj.get("rule_or_invariant"), f"{path}.rule_or_invariant")
            self.require_string_list(obj.get("test_doubles"), f"{path}.test_doubles")
        elif layer == "L2":
            self.required_keys(
                obj,
                path,
                {"flow_ids", "business_entry", "end_state", "side_effects", "covered_flow_elements"},
            )
            flow_ids = self.require_string_list(obj.get("flow_ids"), f"{path}.flow_ids", nonempty=True)
            self.check_refs(flow_ids, flow_map, f"{path}.flow_ids", "业务流程")
            self.require_string(obj.get("business_entry"), f"{path}.business_entry")
            self.require_string(obj.get("end_state"), f"{path}.end_state")
            self.require_string_list(obj.get("side_effects"), f"{path}.side_effects")
            covered = self.require_dict(obj.get("covered_flow_elements"), f"{path}.covered_flow_elements")
            self.required_keys(
                covered,
                f"{path}.covered_flow_elements",
                {"node_ids", "edge_ids", "terminal_ids", "side_effect_ids"},
            )
            for kind in ("node_ids", "edge_ids", "terminal_ids", "side_effect_ids"):
                ids = self.require_string_list(
                    covered.get(kind), f"{path}.covered_flow_elements.{kind}"
                )
                for item_index, element_id in enumerate(ids):
                    owner = self.flow_element_owner[kind].get(element_id)
                    element_path = f"{path}.covered_flow_elements.{kind}[{item_index}]"
                    if owner is None:
                        self.error(element_path, f"引用不存在的流程元素 {element_id!r}")
                    elif owner not in flow_ids:
                        self.error(
                            element_path,
                            f"流程元素 {element_id!r} 属于未被本用例引用的流程 {owner!r}",
                        )
                    else:
                        self.covered_flow_elements[kind].add(element_id)
        elif layer == "L3":
            required = {
                "role",
                "start_state",
                "core_action_via_ui",
                "tool",
                "mode",
                "locator_strategy",
                "observations",
            }
            self.required_keys(obj, path, required)
            self.require_string(obj.get("role"), f"{path}.role")
            self.require_string(obj.get("start_state"), f"{path}.start_state")
            if obj.get("core_action_via_ui") is not True:
                self.error(f"{path}.core_action_via_ui", "L3 核心动作必须通过真实 UI，值必须为 true")
            self.require_string(obj.get("tool"), f"{path}.tool")
            self.require_enum(obj.get("mode"), L3_MODES, f"{path}.mode")
            self.require_string(obj.get("locator_strategy"), f"{path}.locator_strategy")
            self.require_string_list(obj.get("observations"), f"{path}.observations", nonempty=True)

    def validate_cross_links(
        self,
        proposition_map: dict[str, dict[str, Any]],
        obligation_map: dict[str, dict[str, Any]],
        case_map: dict[str, dict[str, Any]],
    ) -> None:
        referenced_propositions = {
            proposition_id
            for obligation in obligation_map.values()
            for proposition_id in obligation.get("proposition_ids", [])
            if isinstance(proposition_id, str)
        }
        for proposition_id in proposition_map:
            if proposition_id not in referenced_propositions:
                self.error(
                    f"$.propositions[{proposition_id}]",
                    "验证命题未被任何覆盖义务承接",
                )

        for obligation_id, obligation in obligation_map.items():
            case_ids = obligation.get("case_ids", [])
            primary_layer = obligation.get("primary_layer")
            primary_cases: list[str] = []
            for case_id in case_ids if isinstance(case_ids, list) else []:
                case = case_map.get(case_id)
                if not case:
                    continue
                if obligation_id not in case.get("obligation_ids", []):
                    self.error(
                        f"$.coverage_obligations[{obligation_id}].case_ids",
                        f"用例 {case_id!r} 未反向引用该覆盖义务",
                    )
                if case.get("responsibility") == "primary":
                    primary_cases.append(case_id)
                    if case.get("layer") != primary_layer:
                        self.error(
                            f"$.cases[{case_id}].layer",
                            f"主责用例层级必须等于义务主责层 {primary_layer!r}",
                        )
            if obligation.get("status") == "designed" and not primary_cases:
                self.error(
                    f"$.coverage_obligations[{obligation_id}].case_ids",
                    "designed 义务至少需要一个位于主责层的 primary 用例",
                )

        for case_id, case in case_map.items():
            for obligation_id in case.get("obligation_ids", []):
                obligation = obligation_map.get(obligation_id)
                if obligation and case_id not in obligation.get("case_ids", []):
                    self.error(
                        f"$.cases[{case_id}].obligation_ids",
                        f"覆盖义务 {obligation_id!r} 未反向引用该用例",
                    )

    def validate_flow_coverage(self) -> None:
        for kind, owners in self.flow_element_owner.items():
            missing = sorted(set(owners) - self.covered_flow_elements[kind])
            for element_id in missing:
                self.error(
                    f"$.flow_models[{owners[element_id]}].{kind}",
                    f"流程元素 {element_id!r} 未被任何 L2 用例承接",
                )

    def validate_coverage_summary(
        self, raw: Any, obligation_map: dict[str, dict[str, Any]]
    ) -> None:
        path = "$.coverage_summary"
        obj = self.require_dict(raw, path)
        self.required_keys(
            obj,
            path,
            {
                "covered_obligation_ids",
                "conditional_obligation_ids",
                "blocked_obligation_ids",
                "uncovered_items",
                "stop_decision",
                "rationale",
            },
        )
        for key in ("covered_obligation_ids", "conditional_obligation_ids", "blocked_obligation_ids"):
            ids = self.require_string_list(obj.get(key), f"{path}.{key}")
            self.check_refs(ids, obligation_map, f"{path}.{key}", "覆盖义务")
            expected_status = {
                "covered_obligation_ids": "designed",
                "conditional_obligation_ids": "conditional",
                "blocked_obligation_ids": "blocked",
            }[key]
            for index, obligation_id in enumerate(ids):
                obligation = obligation_map.get(obligation_id)
                if obligation and obligation.get("status") != expected_status:
                    self.error(
                        f"{path}.{key}[{index}]",
                        f"义务状态应为 {expected_status!r}，实际为 {obligation.get('status')!r}",
                    )
        uncovered = self.require_list(obj.get("uncovered_items"), f"{path}.uncovered_items")
        for index, raw_item in enumerate(uncovered):
            item_path = f"{path}.uncovered_items[{index}]"
            item = self.require_dict(raw_item, item_path)
            self.required_keys(item, item_path, {"description", "reason", "owner"})
            for key in ("description", "reason", "owner"):
                self.require_string(item.get(key), f"{item_path}.{key}")
        self.require_enum(obj.get("stop_decision"), STOP_DECISIONS, f"{path}.stop_decision")
        self.require_string(obj.get("rationale"), f"{path}.rationale")

    def check_refs(
        self,
        refs: list[str],
        target: dict[str, dict[str, Any]],
        path: str,
        label: str,
    ) -> None:
        for index, ref in enumerate(refs):
            if ref not in target:
                self.error(f"{path}[{index}]", f"引用不存在的{label} ID {ref!r}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Path to test-cases.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        with args.manifest.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        print(f"ERROR: 文件不存在: {args.manifest}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"ERROR: JSON 无法解析: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"ERROR: 无法读取文件: {exc}", file=sys.stderr)
        return 2

    validator = Validator(data)
    validator.validate()

    for warning in validator.warnings:
        print(f"WARNING: {warning}")
    for error in validator.errors:
        print(f"ERROR: {error}")

    if validator.errors:
        print(
            f"INVALID: {len(validator.errors)} error(s), {len(validator.warnings)} warning(s)",
            file=sys.stderr,
        )
        return 1

    cases = data.get("cases", []) if isinstance(data, dict) else []
    obligations = data.get("coverage_obligations", []) if isinstance(data, dict) else []
    print(
        f"VALID: {len(cases)} case(s), {len(obligations)} obligation(s), "
        f"{len(validator.warnings)} warning(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
