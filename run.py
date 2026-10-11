# -*- coding: utf-8 -*-
"""微博超话签到 · 飞书机器人 —— 主程序。

启动流程：
1. 读取 config.json，组装服务（卡密 / 飞书多维表格）。
2. 用 lark-oapi 长连接（WebSocket）接收飞书消息（需开放平台已开启“机器人”能力、
   订阅 im.message.receive_v1 且订阅方式选“使用长连接接收事件”）。
3. 解析文本指令 → 分发处理（绑定微博 / 签到 / 兑换卡密 / 购买 / 管理员）。
4. 后台定时任务：每日自动签到 + 主动发送使用说明 + 每日自动生成卡密。

用法：
    python run.py
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import threading

import lark_oapi as lark

from config import load_config, build_services
from feishu.bot_client import FeishuBotClient
from bot import BotContext, KnownUsers, handle_message
from bot import proactive


def _extract_text(event, chat_type: str) -> str:
    """从消息事件里取纯文本；群聊时去掉 @机器人的提及片段。"""
    try:
        content = json.loads(event.message.content)
        text = content.get("text", "") or ""
    except Exception:
        return ""
    if chat_type == "group":
        text = re.sub(r"@_user_\d+\s*", "", text)
    return text.strip()


def main() -> None:
    cfg = load_config()
    feishu_cfg = cfg.get("feishu", {})
    app_id = feishu_cfg.get("app_id", "")
    app_secret = feishu_cfg.get("app_secret", "")
    if not (app_id and app_secret):
        print("请在 config.json 的 feishu 段填写 app_id / app_secret。")
        sys.exit(1)

    services = build_services(cfg)
    client = FeishuBotClient(app_id, app_secret)
    known = KnownUsers()
    ctx = BotContext(client, cfg, services, known)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def on_message(data: lark.im.v1.P2ImMessageReceiveV1) -> None:
        try:
            event = data.event
            if event.message.message_type != "text":
                return
            chat_type = event.message.chat_type or "p2p"
            text = _extract_text(event, chat_type)
            if not text:
                return
            user_id = event.sender.sender_id.open_id
            ctx.log(f"收到消息 open_id={user_id} chat={chat_type} text={text}")
            asyncio.run_coroutine_threadsafe(handle_message(ctx, user_id, text), loop)
        except Exception as exc:
            ctx.log(f"事件处理异常: {exc}")

    # 后台定时任务（每日签到 / 主动使用说明 / 每日自动生成卡密）
    loop.create_task(proactive.run_scheduler(ctx))

    # 长连接接收事件（阻塞于独立线程，避免阻塞事件循环）
    handler = client.event_handler(on_message)
    ws_thread = threading.Thread(target=client.start_ws, args=(handler,), daemon=True)
    ws_thread.start()

    ctx.log("飞书机器人已启动，开始监听消息…（首次收到消息后，其 open_id 会出现在日志）")
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        print("\n已退出。")


if __name__ == "__main__":
    main()
