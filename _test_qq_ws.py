# -*- coding: utf-8 -*-
"""最小 QQ api-v2 WebSocket 连接测试：验证能否订阅 C2C 单聊消息事件。"""
import asyncio
import json

import aiohttp

ACCESS = "MTJ1A8ydSoLrCQLeAznLmx6IIDHwyJvMCPCF7z0pqnrbJ5JUgdf1bvC2wbH2hhJypjVwichG06QtUg"
# GROUP_AND_C2C_EVENT = 1 << 25 = 33554432（含 C2C 单聊 + 群聊消息）
INTENTS_C2C = 1 << 25


async def main():
    async with aiohttp.ClientSession() as sess:
        print("[qq] 连接 wss://api.bot.qq.com/websocket/ ...")
        async with sess.ws_connect("wss://api.bot.qq.com/websocket/", timeout=30) as ws:
            identify = {"op": 2, "d": {
                "token": f"QQBot {ACCESS}",
                "intents": INTENTS_C2C,
                "shard": [0, 1],
                "properties": {"$os": "windows", "$browser": "my_library"},
            }}
            await ws.send_str(json.dumps(identify))
            print("[qq] 已发送 Identify（intents=GROUP_AND_C2C）")
            # 读 20 秒内所有消息
            for _ in range(20):
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                except asyncio.TimeoutError:
                    print("[qq] 5秒无消息（可能是心跳等待）")
                    continue
                if msg.type == aiohttp.WSMsgType.TEXT:
                    print("[qq] RECV:", msg.data[:400])
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    print("[qq] 连接关闭")
                    break
                else:
                    print("[qq] 其他消息类型:", msg.type)


asyncio.run(main())
