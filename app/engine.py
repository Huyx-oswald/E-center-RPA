"""执行引擎：把流程步骤翻译成 Playwright 操作。

步骤类型：
  {"type":"goto","url":...}
  {"type":"click","selector":...}
  {"type":"fill","selector":...,"value":...}
  {"type":"wait","selector"?:...|"ms"?:...}
  {"type":"extract","selector":...,"name":...}
  {"type":"screenshot"}
"""

import os

from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = os.path.abspath(
    os.environ.get("LANYIN_SHOTS", os.path.join(os.path.dirname(__file__), "..", "data", "screenshots"))
)


def _describe(step: dict) -> str:
    t = step.get("type")
    if t == "goto":
        return f"goto {step.get('url')}"
    if t in ("click", "fill"):
        return f"{t} {step.get('selector')}"
    if t == "extract":
        return f"extract {step.get('name') or step.get('selector')}"
    return t or "?"


def run_flow(steps: list, run_id: int, on_log) -> tuple[dict, str | None]:
    """顺序执行步骤，返回 (extract 结果, 最后一张截图文件名)。异常向上抛，由调用方记录。"""
    result: dict = {}
    screenshot_name: str | None = None
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            for i, step in enumerate(steps):
                t = step.get("type")
                if t == "goto":
                    page.goto(step["url"], wait_until="domcontentloaded")
                elif t == "click":
                    page.click(step["selector"])
                elif t == "fill":
                    page.fill(step["selector"], str(step.get("value", "")))
                elif t == "wait":
                    if step.get("selector"):
                        page.wait_for_selector(step["selector"])
                    else:
                        page.wait_for_timeout(int(step.get("ms", 1000)))
                elif t == "extract":
                    text = page.inner_text(step["selector"])
                    result[step.get("name") or f"value{i}"] = text
                    on_log(f"[{i}] extract -> {text!r}")
                    continue
                elif t == "screenshot":
                    screenshot_name = f"{run_id}_{i}.png"
                    page.screenshot(path=os.path.join(SCREENSHOT_DIR, screenshot_name))
                else:
                    raise ValueError(f"未知步骤类型: {t!r}")
                on_log(f"[{i}] {_describe(step)}")
        finally:
            browser.close()
    return result, screenshot_name
