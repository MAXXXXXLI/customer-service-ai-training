"""Regression checks for phased client startup.

The public server serves a large course catalog and several exam banks.  They
must not hold the learning/practice/QA navigation hostage during initial load.
This source-level contract complements browser smoke tests by pinning the
dependency boundary in ``boot``.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "local_app" / "static" / "app.js"


def between(source: str, start: str, end: str) -> str:
    start_at = source.index(start)
    end_at = source.index(end, start_at)
    return source[start_at:end_at]


def main() -> None:
    source = APP.read_text(encoding="utf-8")
    boot = between(source, "async function boot()", '\ndocument.addEventListener("click"')
    core_wait = between(boot, "const [bootstrap, moduleData, health, pointWaveFaqExam] = await Promise.all([", "]);\n    state.scenarios")

    for required in ("bootstrapPromise", "moduleDataPromise", "healthPromise", "pointWaveFaqExamPromise"):
        assert required in core_wait, required
    for deferred in ("catalogDataPromise", "examBankPromise", "realExamBankPromise"):
        assert deferred not in core_wait, deferred
        assert boot.index(f"const {deferred}") < boot.index("await Promise.all(["), deferred

    assert "void catalogDataPromise.then" in boot
    assert "void examBankPromise.then" in boot
    assert "void realExamBankPromise.then" in boot
    assert "function refreshCurrentRouteAfterDeferredData()" in source
    assert "课程内容加载中…" in source
    assert "题库正在后台加载，请稍候…" in source

    print("progressive boot regression: PASS")


if __name__ == "__main__":
    main()
