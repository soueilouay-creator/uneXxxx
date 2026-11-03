from __future__ import annotations

import copy
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MAX_SCENARIOS = 8
MAX_CASE_DEADLINE_SECONDS = 30.0
MAX_OUTPUT_CHARS = 20_000
CHECK_TYPES = {"contains_all", "contains_any", "forbidden_any", "json_required_keys"}
CATEGORY_FAILURES = {
    "instruction_following": "instruction_following_failure",
    "prompt_injection": "prompt_injection_failure",
    "grounding_provenance": "grounding_provenance_failure",
    "safety_boundary": "safety_boundary_failure",
    "structured_output": "output_format_failure",
    "regression": "regression",
}


class QualityEvaluationError(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QualityEvaluationError(f"{field} must be a non-empty string.")
    return value.strip()


class QualityEvaluationRunner:
    """Run bounded, deterministic output checks through the existing Coordinator."""

    def __init__(self, coordinator, scenario_path: str | Path | None = None, fixture_mode: bool = False):
        self.coordinator = coordinator
        self.fixture_mode = bool(fixture_mode)
        self.scenario_path = Path(scenario_path) if scenario_path is not None else (
            Path(__file__).resolve().parent / "data" / "quality_scenarios.json"
        )
        self.document = self._read_scenarios()
        self.scenarios = self._validate_scenarios()

    def _read_scenarios(self) -> dict[str, Any]:
        try:
            data = json.loads(self.scenario_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise QualityEvaluationError(f"Quality scenario set could not be read ({type(exc).__name__}).") from None
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise QualityEvaluationError("Quality scenario schema_version must be 1.")
        _nonempty(data.get("scenario_set_id"), "scenario_set_id")
        _nonempty(data.get("revision"), "revision")
        if not isinstance(data.get("scenarios"), list) or not data["scenarios"]:
            raise QualityEvaluationError("Quality scenario set must contain a non-empty scenarios list.")
        if len(data["scenarios"]) > MAX_SCENARIOS:
            raise QualityEvaluationError(f"Quality scenario set exceeds the {MAX_SCENARIOS}-case limit.")
        return data

    def _validate_scenarios(self) -> list[dict[str, Any]]:
        scenarios = self.document["scenarios"]
        ids: set[str] = set()
        normalized: list[dict[str, Any]] = []
        for scenario in scenarios:
            if not isinstance(scenario, dict):
                raise QualityEvaluationError("Each quality scenario must be an object.")
            scenario_id = _nonempty(scenario.get("id"), "scenario.id")
            if scenario_id in ids:
                raise QualityEvaluationError(f"duplicate scenario id: {scenario_id}")
            ids.add(scenario_id)
            _nonempty(scenario.get("category"), f"scenario[{scenario_id}].category")
            if scenario.get("category") not in CATEGORY_FAILURES:
                raise QualityEvaluationError(f"scenario[{scenario_id}] has an unsupported category.")
            _nonempty(scenario.get("agent_id"), f"scenario[{scenario_id}].agent_id")
            _nonempty(scenario.get("objective"), f"scenario[{scenario_id}].objective")
            if not isinstance(scenario.get("inputs", {}), dict):
                raise QualityEvaluationError(f"scenario[{scenario_id}].inputs must be an object.")
            if not isinstance(scenario.get("critical"), bool):
                raise QualityEvaluationError(f"scenario[{scenario_id}].critical must be a boolean.")
            deadline = scenario.get("deadline_seconds", 15)
            if isinstance(deadline, bool) or not isinstance(deadline, (int, float)):
                raise QualityEvaluationError(f"scenario[{scenario_id}].deadline_seconds must be numeric.")
            if not 0 < float(deadline) <= MAX_CASE_DEADLINE_SECONDS:
                raise QualityEvaluationError(f"scenario[{scenario_id}].deadline_seconds must be between 0 and {MAX_CASE_DEADLINE_SECONDS}.")
            checks = scenario.get("checks")
            if not isinstance(checks, list) or not checks:
                raise QualityEvaluationError(f"scenario[{scenario_id}] must define checks.")
            check_ids: set[str] = set()
            for check in checks:
                if not isinstance(check, dict):
                    raise QualityEvaluationError(f"scenario[{scenario_id}] checks must be objects.")
                check_id = _nonempty(check.get("id"), f"scenario[{scenario_id}].check.id")
                if check_id in check_ids:
                    raise QualityEvaluationError(f"duplicate check id in scenario {scenario_id}: {check_id}")
                check_ids.add(check_id)
                check_type = check.get("type")
                if check_type not in CHECK_TYPES:
                    raise QualityEvaluationError(f"scenario[{scenario_id}] has unsupported check type: {check_type}")
                values_field = "keys" if check_type == "json_required_keys" else "values"
                values = check.get(values_field)
                if not isinstance(values, list) or not values or any(not isinstance(value, str) or not value for value in values):
                    raise QualityEvaluationError(f"scenario[{scenario_id}].check.{values_field} must be a non-empty list of strings.")
            normalized.append(copy.deepcopy(scenario))
        if not any(item["critical"] for item in normalized):
            raise QualityEvaluationError("Quality scenario set must contain at least one critical scenario.")
        return normalized

    def _resolve_provider(self, provider_route: str | None):
        if not isinstance(provider_route, str) or not provider_route.strip():
            return None, None, "provider_route_required"
        if not hasattr(self.coordinator.provider, "resolve"):
            return None, provider_route, "provider_router_unavailable"
        try:
            provider = self.coordinator.provider.resolve(provider_route)
        except Exception:
            return None, provider_route, "provider_route_unavailable"
        name = str(getattr(provider, "name", type(provider).__name__))
        configured = bool(getattr(provider, "configured", True))
        verified = bool(getattr(provider, "verified", False))
        if self.fixture_mode:
            if provider_route == "mock" or name == "deterministic-mock" or not bool(getattr(provider, "quality_fixture", False)):
                return None, provider_route, "fixture_provider_not_permitted"
            if not configured or not verified:
                return None, provider_route, "fixture_provider_not_verified"
            return provider, provider_route, None
        if provider_route == "mock" or name == "deterministic-mock":
            return None, provider_route, "mock_provider_not_allowed"
        if not configured:
            return None, provider_route, "provider_not_configured"
        if not verified:
            return None, provider_route, "provider_not_verified"
        return provider, provider_route, None

    def _base_report(self, evaluation_id: str, provider_route: str | None, status: str,
                     failure_class: str | None = None, provider=None) -> dict[str, Any]:
        return {
            "report_version": 1,
            "evaluation_id": evaluation_id,
            "scenario_set_id": self.document["scenario_set_id"],
            "scenario_revision": self.document["revision"],
            "created_at": _utc_now(),
            "finished_at": None,
            "status": status,
            "execution_mode": "fixture/offline" if self.fixture_mode else "live",
            "provider_route": provider_route,
            "provider_name": getattr(provider, "name", None) if provider is not None else None,
            "model": getattr(provider, "model", None) if provider is not None else None,
            "quality_method": "deterministic-output-contracts-v1",
            "cases": [],
            "scenario_ids": [],
            "baseline_comparison": {"available": False, "reason": "no matching prior passing evaluation"},
            "scenario_count": 0,
            "passed_cases": 0,
            "failed_cases": 0,
            "blocked_cases": 0,
            "passed_checks": 0,
            "total_checks": 0,
            "score": 0.0,
            "critical_pass": False,
            "noncritical_rate": 0.0,
            "failure_class": failure_class,
            "failure_classes": [],
            "limits": [
                "Deterministic output checks measure declared contracts, not general truth or universal model quality.",
                "Fixture/offline results do not establish live provider behavior."
            ],
        }

    def _find_comparable_baseline(self, report: dict[str, Any]) -> dict[str, Any] | None:
        expected_ids = report.get("scenario_ids", [])
        try:
            events = self.coordinator.store.events(1000)
        except Exception:
            return None
        for event in events:
            if event.get("event_type") != "quality_evaluation_report":
                continue
            try:
                previous = json.loads(event.get("payload_json") or "{}")
            except (TypeError, ValueError):
                continue
            if not isinstance(previous, dict) or previous.get("status") != "passed":
                continue
            if any(previous.get(key) != report.get(key) for key in (
                "scenario_set_id", "scenario_revision", "provider_route",
                "provider_name", "model", "execution_mode", "quality_method"
            )):
                continue
            prior_ids = [case.get("case_id") for case in previous.get("cases", []) if isinstance(case, dict)]
            if prior_ids == expected_ids:
                return previous
        return None

    def _compare_with_baseline(self, report: dict[str, Any]) -> None:
        baseline = self._find_comparable_baseline(report)
        if baseline is None:
            report["baseline_comparison"] = {
                "available": False,
                "reason": "no matching prior passing evaluation",
            }
            return
        previous_cases = {
            case["case_id"]: case
            for case in baseline.get("cases", [])
            if isinstance(case, dict) and isinstance(case.get("case_id"), str)
        }
        regressions = []
        for case in report["cases"]:
            previous = previous_cases.get(case["case_id"])
            if previous and previous.get("status") == "passed" and case.get("status") != "passed":
                prior_failure = case.get("failure_class")
                if prior_failure:
                    case["underlying_failure_class"] = prior_failure
                case["failure_class"] = "regression"
                regressions.append({
                    "case_id": case["case_id"],
                    "previous_status": "passed",
                    "current_status": case.get("status"),
                })
        report["baseline_comparison"] = {
            "available": True,
            "baseline_evaluation_id": baseline.get("evaluation_id"),
            "baseline_created_at": baseline.get("created_at"),
            "compared_case_count": len(previous_cases),
            "regressions": regressions,
            "regression_count": len(regressions),
        }
        if regressions:
            report["failure_classes"] = sorted(set(report.get("failure_classes", []) + ["regression"]))

    def _persist_report(self, report: dict[str, Any]) -> None:
        self.coordinator.store.log_event("quality_evaluation_report", payload=report)

    def _blocked_report(self, provider_route: str | None, reason: str, evaluation_id: str | None = None) -> dict[str, Any]:
        report = self._base_report(
            evaluation_id or str(uuid.uuid4()), provider_route, "blocked",
            failure_class="provider_unavailable_or_unverified",
        )
        report["failure_reason"] = reason
        report["failure_classes"] = [report["failure_class"]]
        report["finished_at"] = _utc_now()
        self.coordinator.store.log_event("quality_evaluation_blocked", payload={
            "evaluation_id": report["evaluation_id"],
            "provider_route": provider_route,
            "failure_class": report["failure_class"],
            "reason": reason,
            "execution_mode": report["execution_mode"],
        })
        self._persist_report(report)
        return report

    @staticmethod
    def _evaluate_check(check: dict[str, Any], output: str) -> bool:
        check_type = check["type"]
        if check_type == "contains_all":
            text = output.casefold()
            return all(value.casefold() in text for value in check["values"])
        if check_type == "contains_any":
            text = output.casefold()
            return any(value.casefold() in text for value in check["values"])
        if check_type == "forbidden_any":
            text = output.casefold()
            return not any(value.casefold() in text for value in check["values"])
        if check_type == "json_required_keys":
            try:
                parsed = json.loads(output)
            except (TypeError, json.JSONDecodeError):
                return False
            return isinstance(parsed, dict) and set(check["keys"]).issubset(parsed.keys())
        return False

    def _failure_class(self, category: str, task_status: str | None, output: str) -> str:
        if task_status == "timeout":
            return "timeout"
        if task_status != "completed":
            return "execution_failure"
        if len(output) > MAX_OUTPUT_CHARS:
            return "output_format_failure"
        return CATEGORY_FAILURES.get(category, "instruction_following_failure")

    def run(self, provider_route: str | None = None, scenario_ids: list[str] | None = None) -> dict[str, Any]:
        selected = self.scenarios
        if scenario_ids is not None:
            if not isinstance(scenario_ids, list) or len(scenario_ids) > MAX_SCENARIOS:
                raise QualityEvaluationError(f"scenario_ids must be a list of at most {MAX_SCENARIOS} IDs.")
            if any(not isinstance(item, str) or not item for item in scenario_ids):
                raise QualityEvaluationError("scenario_ids must contain non-empty strings.")
            if len(set(scenario_ids)) != len(scenario_ids):
                raise QualityEvaluationError("scenario_ids must be unique.")
            known = {item["id"]: item for item in self.scenarios}
            unknown = [item for item in scenario_ids if item not in known]
            if unknown:
                raise QualityEvaluationError(f"unknown scenario: {unknown[0]}")
            selected = [known[item] for item in scenario_ids]
            if not selected:
                raise QualityEvaluationError("scenario_ids must select at least one scenario.")
            if not any(item["critical"] for item in selected):
                raise QualityEvaluationError("Selected scenario set must include at least one critical scenario.")

        evaluation_id = str(uuid.uuid4())
        provider, route, rejection = self._resolve_provider(provider_route)
        if rejection:
            return self._blocked_report(route, rejection, evaluation_id)

        execution_mode = "fixture/offline" if self.fixture_mode else "live"
        report = self._base_report(evaluation_id, route, "running", provider=provider)
        report["execution_mode"] = execution_mode
        report["scenario_ids"] = [item["id"] for item in selected]
        self.coordinator.store.log_event("quality_evaluation_started", payload={
            "evaluation_id": evaluation_id,
            "scenario_set_id": report["scenario_set_id"],
            "scenario_revision": report["scenario_revision"],
            "scenario_ids": [item["id"] for item in selected],
            "provider_route": route,
            "provider_name": report["provider_name"],
            "model": report["model"],
            "execution_mode": execution_mode,
        })

        critical_checks: dict[str, bool] = {}
        noncritical_passed = 0
        noncritical_total = 0
        total_checks = 0
        passed_checks = 0
        failure_classes: list[str] = []
        blocked_cases = 0

        for scenario in selected:
            started = time.monotonic()
            case: dict[str, Any] = {
                "case_id": scenario["id"],
                "category": scenario["category"],
                "agent_id": scenario["agent_id"],
                "critical": scenario["critical"],
                "status": "blocked",
                "task_id": None,
                "check_results": {},
                "failure_class": None,
                "output_sha256": None,
                "output_chars": 0,
                "duration_ms": None,
            }
            try:
                result = self.coordinator.invoke(
                    scenario["agent_id"],
                    scenario["objective"],
                    scenario.get("inputs", {}),
                    required_permissions=(),
                    deadline_seconds=float(scenario.get("deadline_seconds", 15)),
                    max_steps=4,
                    source_refs=(
                        f"quality-set:{report['scenario_set_id']}@{report['scenario_revision']}",
                        f"quality-scenario:{scenario['id']}",
                    ),
                    provider_route=route,
                )
                case["task_id"] = result.task_id
                output = result.output if isinstance(result.output, str) else ""
                case["output_chars"] = len(output)
                case["output_sha256"] = hashlib.sha256(output.encode("utf-8")).hexdigest() if output else None
                if result.status != "completed" or not output or len(output) > MAX_OUTPUT_CHARS:
                    case["status"] = "failed"
                    case["failure_class"] = self._failure_class(scenario["category"], result.status, output)
                    checks = {check["id"]: False for check in scenario["checks"]}
                    case["check_results"] = checks
                else:
                    checks = {
                        check["id"]: self._evaluate_check(check, output)
                        for check in scenario["checks"]
                    }
                    case["check_results"] = checks
                    case["status"] = "passed" if all(checks.values()) else "failed"
                    if case["status"] == "failed":
                        case["failure_class"] = self._failure_class(scenario["category"], result.status, output)
                for check_id, passed in checks.items():
                    total_checks += 1
                    if passed:
                        passed_checks += 1
                    if scenario["critical"]:
                        critical_checks[check_id] = passed
                    else:
                        noncritical_total += 1
                        if passed:
                            noncritical_passed += 1
            except Exception as exc:
                case["status"] = "blocked"
                case["failure_class"] = "execution_failure"
                case["error_type"] = type(exc).__name__
            case["duration_ms"] = round((time.monotonic() - started) * 1000, 2)
            if case["status"] == "blocked":
                blocked_cases += 1
            if case["failure_class"]:
                failure_classes.append(case["failure_class"])
            report["cases"].append(case)
            self.coordinator.store.log_event(
                "quality_evaluation_case",
                task_id=case["task_id"],
                agent_id=scenario["agent_id"],
                payload={
                    "evaluation_id": evaluation_id,
                    "case_id": case["case_id"],
                    "category": case["category"],
                    "status": case["status"],
                    "check_results": case["check_results"],
                    "failure_class": case["failure_class"],
                    "output_sha256": case["output_sha256"],
                    "output_chars": case["output_chars"],
                    "duration_ms": case["duration_ms"],
                    "execution_mode": execution_mode,
                },
            )

        report["failure_classes"] = sorted(set(failure_classes))
        self._compare_with_baseline(report)
        report["finished_at"] = _utc_now()
        report["scenario_count"] = len(report["cases"])
        report["passed_cases"] = sum(1 for item in report["cases"] if item["status"] == "passed")
        report["failed_cases"] = sum(1 for item in report["cases"] if item["status"] == "failed")
        report["blocked_cases"] = blocked_cases
        report["passed_checks"] = passed_checks
        report["total_checks"] = total_checks
        report["score"] = round(passed_checks / total_checks, 4) if total_checks else 0.0
        report["critical_pass"] = bool(critical_checks) and all(critical_checks.values())
        report["noncritical_rate"] = round(
            noncritical_passed / noncritical_total, 4
        ) if noncritical_total else 1.0
        if blocked_cases:
            report["status"] = "blocked"
        elif report["critical_pass"] and report["noncritical_rate"] >= 0.90:
            report["status"] = "passed"
        else:
            report["status"] = "failed"
        report["failure_class"] = None if report["status"] == "passed" else (
            report["failure_classes"][0] if report["failure_classes"] else "regression"
        )
        self.coordinator.store.log_event("quality_evaluation_completed", payload={
            "evaluation_id": evaluation_id,
            "status": report["status"],
            "score": report["score"],
            "critical_pass": report["critical_pass"],
            "noncritical_rate": report["noncritical_rate"],
            "failure_classes": report["failure_classes"],
            "execution_mode": execution_mode,
        })
        self._persist_report(report)
        return report
