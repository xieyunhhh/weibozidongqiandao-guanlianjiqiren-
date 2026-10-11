# -*- coding: utf-8 -*-
"""一次性 patch：飞书 commands.py 状态分析/签到显示完整超话列表 + 长文本分片发送。"""
p = r"D:\weibo_claw_bot\bot\commands.py"
with open(p, encoding="utf-8") as f:
    s = f.read()
with open(p + ".bak", "w", encoding="utf-8") as f:
    f.write(s)

# ---------- 1. 加 _split_text（插在 UserTaskManager 类定义前） ----------
split_fn = '''def _split_text(text: str, limit: int = 1800) -> list:
    """按行把长文本切分为多段，每段不超过 limit 字符（飞书单条消息有长度上限）。"""
    if len(text) <= limit:
        return [text]
    parts: list = []
    cur = ""
    for line in text.split("\\n"):
        if cur and len(cur) + len(line) + 1 > limit:
            parts.append(cur)
            cur = ""
            while len(line) > limit:
                parts.append(line[:limit])
                line = line[limit:]
        cur = cur + "\\n" + line if cur else line
    if cur:
        parts.append(cur)
    return parts


'''
assert s.count("class UserTaskManager:") == 1
s = s.replace("class UserTaskManager:", split_fn + "class UserTaskManager:", 1)
print("已插入 _split_text")

# ---------- 2. 替换 _cmd_checkin + _cmd_analyze ----------
start_anchor = "async def _cmd_checkin(ctx: BotContext, user_id: str) -> None:"
end_anchor = "async def _cmd_cancel(ctx: BotContext, user_id: str) -> None:"
i = s.index(start_anchor)
j = s.index(end_anchor, i)
new_block = '''async def _cmd_checkin(ctx: BotContext, user_id: str) -> None:
    if not ctx.cards.is_entitled(user_id):
        await ctx.send(user_id, "你还没有有效卡密。发送「购买」获取，或联系管理员发卡。")
        return
    cookies = weibo.store.load_cookies(user_id)
    if not cookies:
        await ctx.send(user_id, "你还没有绑定微博。发送「绑定微博」或「绑定cookie」开始。")
        return

    rec = _tasks.get(user_id)
    if rec and rec["kind"] == "checkin" and not rec["task"].done():
        await ctx.send(user_id, "正在签到中，请稍候或发送「取消」。")
        return

    await ctx.send(user_id, "开始一键签到…")

    async def _worker():
        stop = {"flag": False}

        def should_stop() -> bool:
            return stop["flag"]

        try:
            result = await asyncio.to_thread(
                weibo.core.auto_checkin,
                cookies,
                delay=float(ctx.weibo_cfg.get("checkin_delay_sec", 0.3)),
                should_stop=should_stop,
            )
            head = (
                f"✅ 签到完成（完成率 {result['completion_rate']:.1f}%）\\n"
                f"总超话：{result['total']}｜新签：{result['new']}｜"
                f"已签：{result['already']}｜失败：{result['failed']}"
            )
            details = result.get("details") or []
            if not details:
                await ctx.send(user_id, head + "\\n（暂无可展示的超话）")
                return
            lines = [head, "\\n【签到结果】"]
            for i2, d in enumerate(details, 1):
                lines.append(f"{i2}. {d.get('name', '?')} · {d.get('status', '?')} · {d.get('level', '')}")
            for seg in _split_text("\\n".join(lines)):
                await ctx.send(user_id, seg)
        except Exception as exc:
            await ctx.send(user_id, f"签到出错：{exc}")
        finally:
            _tasks.clear(user_id)

    task = asyncio.create_task(_worker())
    _tasks.set(user_id, "checkin", task)


async def _cmd_analyze(ctx: BotContext, user_id: str) -> None:
    if not ctx.cards.is_entitled(user_id):
        await ctx.send(user_id, "你还没有有效卡密。发送「购买」获取，或联系管理员发卡。")
        return
    cookies = weibo.store.load_cookies(user_id)
    if not cookies:
        await ctx.send(user_id, "你还没有绑定微博。发送「绑定微博」开始。")
        return

    async def _worker():
        try:
            result = await asyncio.to_thread(weibo.core.analyze_status, cookies)
            st = result.get("stats", {})
            head = (
                f"📊 超话状态分析\\n"
                f"总超话：{st.get('total', 0)}｜已签到：{st.get('checked_in', 0)}｜"
                f"可签到：{st.get('can_checkin', 0)}\\n"
                f"完成率：{result.get('completion_rate', 0) * 100:.1f}%"
            )
            topics = result.get("topics") or []
            if not topics:
                await ctx.send(user_id, head + "\\n（暂无可展示的超话）")
                return
            lines = [head, "\\n【超话列表】"]
            for i2, t in enumerate(topics, 1):
                lines.append(f"{i2}. {t.get('name', '?')} · {t.get('status', '?')} · {t.get('level', '')}")
            for seg in _split_text("\\n".join(lines)):
                await ctx.send(user_id, seg)
        except Exception as exc:
            await ctx.send(user_id, f"分析出错：{exc}")
        finally:
            _tasks.clear(user_id)

    _tasks.set(user_id, "analyze", asyncio.create_task(_worker()))


'''
s = s[:i] + new_block + s[j:]
print("已替换 _cmd_checkin/_cmd_analyze")

with open(p, "w", encoding="utf-8") as f:
    f.write(s)
print("写入完成")
