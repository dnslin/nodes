"""Headed Chromium configuration shared by desktop Linux and Docker."""

import os
import platform
import shutil
from pathlib import Path

from DrissionPage import ChromiumOptions


def browser_options(hidden=False, browser_path="", extension_path=""):
    """Use a real browser window; Linux servers supply DISPLAY through Xvfb."""
    if platform.system() == "Linux" and not os.environ.get("DISPLAY"):
        raise RuntimeError(
            "Linux 未设置 DISPLAY，请通过 ./start.sh 启动，或安装 Xvfb 后用 xvfb-run 运行。"
        )

    extension = Path(extension_path or Path(__file__).parent / "turnstilePatch").resolve()
    if not (extension / "manifest.json").is_file():
        raise FileNotFoundError(f"找不到 Turnstile 扩展 manifest.json: {extension}")

    if not browser_path and platform.system() == "Linux":
        browser_path = next(
            (
                path
                for name in (
                    "chromium",
                    "chromium-browser",
                    "google-chrome",
                    "google-chrome-stable",
                )
                if (path := shutil.which(name))
            ),
            "",
        )
        if not browser_path:
            raise RuntimeError("找不到 Chromium / Chrome，请安装 chromium 或配置 BROWSER_PATH。")

    options = ChromiumOptions()
    options.auto_port()
    options.headless(False)
    if browser_path:
        options.set_browser_path(browser_path)
    for flag in (
        "--no-first-run",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-background-networking",
        "--mute-audio",
        "--disable-gpu",
        "--window-size=1280,900",
    ):
        options.set_argument(flag)
    if hidden:
        options.set_argument("--window-position=-32000,-32000")
    options.add_extension(str(extension))
    return options
