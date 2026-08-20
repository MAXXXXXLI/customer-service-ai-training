from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    bank = json.loads((ROOT / "knowledge_base" / "comprehensive_exam_bank.json").read_text(encoding="utf-8"))
    modules = bank["modules"]
    assert len(modules) == 10
    assert sum(len(item["fill_blanks"]) for item in modules) == 60
    assert sum(len(item["choices"]) for item in modules) == 80
    scenarios = [scenario for item in modules for scenario in item["scenarios"]]
    assert len(scenarios) == 30
    assert all(len(item["answers"]) >= 1 for module in modules for item in [*module["fill_blanks"], *module["choices"]])
    assert all(scenario["opening"] and scenario["must_test"] and scenario["critical_failures"] and scenario["reference_answer"] for scenario in scenarios)
    assert all(scenario["id"].startswith("SCN-CEX-") for scenario in scenarios)
    static = json.loads((ROOT / "local_app" / "static" / "data" / "comprehensive_exam_bank.json").read_text(encoding="utf-8"))
    assert static == bank
    print(json.dumps({"status": "passed", "modules": len(modules), "fill_blanks": 60, "choices": 80, "ai_scenarios": len(scenarios)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
