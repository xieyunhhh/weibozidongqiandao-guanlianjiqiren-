# -*- coding: utf-8 -*-
"""
三端机器人统一入口（单文件合并版）
=====================================
在一个进程内用三个独立线程同时运行：
  · 飞书机器人（run.py，lark 长连接，运营主入口）
  · 微信机器人（wxbot.py，wxauto4 轮询 + PC 微信 UI 自动化）
  · QQ 机器人  （qqbot.py，WebSocket 长连接）
三者共用 D:\\weibo_claw_bot 的代码、配置与飞书多维表格卡密库，管理统一在飞书。

运行环境（合并环境，需装齐三方依赖）：
  wxauto4(微信) + lark_oapi(飞书) + aiohttp / requests(QQ)
  建议用 Python 3.12 的 venv_wx（已装 lark_oapi / aiohttp / wxauto4）。

启动方式：
  python bot_all.py
"""
import os
import sys
import threading
import traceback

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
os.chdir(BASE)

# 依次 import 机器人模块（均有 if __name__ 保护，import 不会自行启动）
import run      # noqa: E402
import qqbot    # noqa: E402


def _run_feishu() -> None:
    try:
        run.main()
    except Exception as e:
        print(f"[bot_all] 飞书线程异常退出: {e}\n{traceback.format_exc()}")


def _run_qq() -> None:
    try:
        qqbot.main_entry()
    except Exception as e:
        print(f"[bot_all] QQ线程异常退出: {e}\n{traceback.format_exc()}")


def main() -> None:
    print("[bot_all] 启动三端统一机器人（飞书 + 微信 + QQ）...")
    threads = [
        threading.Thread(target=_run_feishu, name="feishu", daemon=True),
        threading.Thread(target=_run_qq, name="qq", daemon=True),
    ]
    for t in threads:
        t.start()
        print(f"[bot_all] 已启动线程: {t.name}")
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("[bot_all] 收到退出信号，正在结束。")


if __name__ == "__main__":
    main()
