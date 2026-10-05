import json
from pathlib import Path


SCENARIOS_PATH = Path(__file__).with_name("scenarios.json")
REQUIRED_CHECKS = {
    "goal_retained",
    "constraints_retained",
    "terms_retained",
    "sources_on_every_answer",
}


def validate_scenario(scenario: dict[str, object]) -> list[str]:
    errors = []
    if len(scenario.get("turns", [])) != 12:
        errors.append("scenario must contain exactly 12 user turns")
    if not scenario.get("goal"):
        errors.append("goal is required")
    if not scenario.get("constraints"):
        errors.append("constraints are required")
    if not scenario.get("terms"):
        errors.append("terms are required")
    if set(scenario.get("expected_checks", [])) != REQUIRED_CHECKS:
        errors.append("all long-dialog checks are required")
    return errors


def evaluate(path: Path = SCENARIOS_PATH) -> tuple[int, int]:
    scenarios = json.loads(path.read_text(encoding="utf-8"))
    passed = sum(not validate_scenario(scenario) for scenario in scenarios)
    return passed, len(scenarios)


if __name__ == "__main__":
    passed, total = evaluate()
    print(f"Long-dialog scenarios: {passed}/{total}")
