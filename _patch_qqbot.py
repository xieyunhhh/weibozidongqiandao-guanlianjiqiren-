# -*- coding: utf-8 -*-
"""一次性 patch：qqbot.py 状态分析/签到显示完整超话列表 + 长文本分片发送。"""
import io

p = r"D:\weibo_claw_bot\qqbot.py"
with open(p, encoding="utf-8") as f:
    s = f.read()
with open(p + ".bak", "w", encoding="utf-8") as f:
    f.write(s)

# ---------- 1. 替换 _checkin + _status（含新增 _format_checkin_result） ----------
start_anchor = "def _checkin(openid: str) -> str:"
end_anchor = 'PAY_QR_PATH = os.path.join(BASE, "storage", "pay_qrcode.png")'
i = s.index(start_anchor)
j = s.index(end_anchor, i)
new_block = '''def _format_checkin_result(result: dict) -> str:
    """把签到结果格式化为「统计 + 完整超话列表」文本。"""
    head = (
        f"✅ 签到完成（完成率 {result.get('completion_rate', 0):.1f}%）\\n"
        f"总超话：{result.get('total', 0)}｜新签：{result.get('new', 0)}｜"
        f"已签：{result.get('already', 0)}｜失败：{result.get('failed', 0)}\\n"
    )
    details = result.get("details") or []
    if not details:
        return head + "\\n（暂无可展示的超话）"
    lines = [head, "\\n【签到结果】"]
    for i2, d in enumerate(details, 1):
        lines.append(f"{i2}. {d.get('name', '?')} · {d.get('status', '?')} · {d.get('level', '')}")
    return "\\n".join(lines)


def _checkin(openid: str) -> str:
    if not CARDS.is_entitled(openid):
        return "你还没有有效卡密。发送「购买」获取，或联系管理员发卡。"
    cookies = wb_store.load_cookies(openid)
    if not cookies:
        return "你还没有绑定微博。发送「绑定cookie 你的cookie」绑定。"
    if openid in _jobs:
        return "你有一个签到正在后台执行，请稍后发「状态」查看。"
    _jobs[openid] = "正在签到…"

    def _run():
        try:
            result = wb_core.auto_checkin(cookies, delay=0.3)
            _jobs[openid] = _format_checkin_result(result)
        except Exception as exc:
            _jobs[openid] = f"签到出错：{exc}"

    threading.Thread(target=_run, daemon=True).start()
    return "⏳ 已开始一键签到（后台执行，需几十秒）。完成后发送「状态」查看结果。"


def _status(openid: str) -> str:
    if openid in _jobs:
        return _jobs[openid]
    if not CARDS.is_entitled(openid):
        return "你还没有有效卡密。发送「购买」获取。"
    cookies = wb_store.load_cookies(openid)
    if not cookies:
        return "你还没有绑定微博。发送「绑定cookie 你的cookie」绑定。"
    try:
        result = wb_core.analyze_status(cookies)
        st = result.get("stats", {})
        head = (
            f"📊 超话状态分析\\n"
            f"总超话：{st.get('total', 0)}｜已签到：{st.get('checked_in', 0)}｜"
            f"可签到：{st.get('can_checkin', 0)}\\n"
            f"完成率：{result.get('completion_rate', 0) * 100:.1f}%\\n"
        )
        topics = result.get("topics") or []
        if not topics:
            return head + "\\n（暂无可展示的超话）"
        lines = [head, "\\n【超话列表】"]
        for i2, t in enumerate(topics, 1):
            lines.append(f"{i2}. {t.get('name', '?')} · {t.get('status', '?')} · {t.get('level', '')}")
        return "\\n".join(lines)


'''
s = s[:i] + new_block + s[j:]
print("已替换 _checkin/_status 块")

# ---------- 2. 新增 _split_text 分片函数（插在 qq_send 函数定义后） ----------
anchor_qq = "async def qq_send(openid: str, text: str, msg_id: str = \"\") -> None:"
iq = s.index(anchor_qq)
# 找 qq_send 函数结束：下一个 "\n\n# ---------- 状态与任务 ----------" 
end_q = s.index("# ---------- 状态与任务 ----------", iq)
split_fn = '''def _split_text(text: str, limit: int = 1800) -> list:
    """按行把长文本切分为多段，每段不超过 limit 字符（QQ 单条消息有长度上限）。"""
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
s = s[:end_q] + split_fn + s[end_q:]
print("已插入 _split_text")

# ---------- 3. 单聊发送分片 ----------
old_send1 = "        else:\n            await qq_send(openid, out, msg_id=msg_id)"
new_send1 = ("        else:\n"
             "            segs = _split_text(out)\n"
             "            for i, seg in enumerate(segs):\n"
             "                await qq_send(openid, seg, msg_id=msg_id if i == 0 else \"\")")
assert s.count(old_send1) == 1, f"单聊发送锚点不唯一: {s.count(old_send1)}"
s = s.replace(old_send1, new_send1)
print("已改单聊发送分片")

# ---------- 4. 群聊发送分片 ----------
old_send2 = "        else:\n            await qq_send_group(group_openid, out, msg_id=msg_id)"
new_send2 = ("        else:\n"
             "            segs = _split_text(out)\n"
             "            for i, seg in enumerate(segs):\n"
             "                await qq_send_group(group_openid, seg, msg_id=msg_id if i == 0 else \"\")")
assert s.count(old_send2) == 1, f"群聊发送锚点不唯一: {s.count(old_send2)}"
s = s.replace(old_send2, new_send2)
print("已改群聊发送分片")

with open(p, "w", encoding="utf-8") as f:
    f.write(s)
print("写入完成")
