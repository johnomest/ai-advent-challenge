import json
from pathlib import Path


CASES_PATH = Path(__file__).with_name("evaluation_cases.json")


def validate_case(case: dict[str, object]) -> str:
    chunk = str(case["chunk"])
    quote = str(case["quote"])
    return "accept" if quote and quote in chunk else "refuse"


def evaluate(path: Path = CASES_PATH) -> tuple[int, int]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    passed = sum(validate_case(case) == case["expected"] for case in cases)
    return passed, len(cases)


if __name__ == "__main__":
    passed, total = evaluate()
    print(f"Grounding validation: {passed}/{total}")
