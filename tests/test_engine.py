"""引擎自检：跑一段真实流程，断言 extract 结果。直接 `python3 tests/test_engine.py` 即可。"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.engine import run_flow  # noqa: E402

PAGE = "file://" + os.path.abspath(os.path.join(os.path.dirname(__file__), "page.html"))


def main() -> None:
    steps = [
        {"type": "goto", "url": PAGE},
        {"type": "fill", "selector": "#name", "value": "lanyin"},
        {"type": "click", "selector": "#go"},
        {"type": "extract", "selector": "#out", "name": "greeting"},
        {"type": "screenshot"},
    ]
    logs = []
    result, screenshot = run_flow(steps, run_id=0, on_log=logs.append)

    print("logs:", logs)
    print("result:", result)
    assert result.get("greeting") == "hello lanyin", result
    assert screenshot and os.path.exists(os.path.join(os.path.dirname(__file__), "..", "data", "screenshots", screenshot))
    print("OK: engine self-check passed")


if __name__ == "__main__":
    main()
