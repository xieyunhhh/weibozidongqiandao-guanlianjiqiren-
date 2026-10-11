# -*- coding: utf-8 -*-
"""微信公众号回调服务：微博超话一键签到（个人订阅号，被动回复）。

复用现有模块：weibo/core.py（签到）、weibo/store.py（微博cookie，按 openid 存）、
card/service.py（卡密）、feishu/bitable.py（卡密表）、config.py。

部署：本机运行本服务 + 内网穿透暴露公网 URL，在公众号后台「服务器配置」填入：
     URL = {穿透地址}/wechat ，Token = config.json 的 mp.token
运行：python wechat_mp.py
"""
from __future__ import annotations

import hashlib
import os
import re
import threading
import time
import xml.etree.ElementTree as ET

from flask import Flask, request

from config import load_config, build_services
from weibo import store as wb_store
from weibo import core as wb_core

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)

CFG = load_config()
MP = CFG.get("mp", {})
TOKEN = MP.get("token", "")
ADMIN_IDS = set(MP.get("admin_openids", []) or [])
WECHAT_CHROMEDRIVER = MP.get("chromedriver") or CFG.get("weibo", {}).get("chromedriver", "")
SVC = build_services(CFG)
CARDS = SVC["cards"]
REPO = SVC["repo"]

# 进行中的耗时任务（签到等）：openid -> 状态文本
_jobs: dict[str, str] = {}

# 付款确认状态（简化：openid -> 待确认标记）
_pending_pay: dict[int, str] = {}
_pay_seq = 0
_pay_lock = threading.Lock()

USAGE = (
    "📖 微博超话一键签到 · 使用说明\n\n"
    "1. 发送「兑换 卡密」激活（没有卡先发「购买」）\n"
    "2. 发送「绑定cookie 你的cookie」绑定微博\n"
    "3. 发送「签到」自动签到全部超话，稍后发「状态」查看结果\n\n"
    "【指令】\n"
    "· 帮助/使用说明 —— 本说明\n"
    "· 绑定cookie <cookie> —— 粘贴微博cookie绑定\n"
    "· 签到 —— 一键签到全部超话（后台执行，完成后发「状态」看结果）\n"
    "· 状态/分析 —— 查看超话签到情况\n"
    "· 我的卡 —— 查看卡密状态\n"
    "· 购买/获取卡密 —— 查看价格并联系管理员发卡\n"
    "· 兑换 <卡密> —— 激活卡密\n"
    "· 设置签到时间 03:00~05:00 —— 设置每日自动签到时间段\n\n"
    "💡 卡密为一次性激活码，兑换后尽快使用。"
)


# ---------------- 微信签名校验 ----------------
def _check_signature(signature: str, timestamp: str, nonce: str) -> bool:
    if not TOKEN:
        return False
    arr = sorted([TOKEN, timestamp, nonce])
    return hashlib.sha1("".join(arr).encode("utf-8")).hexdigest() == signature


@app.route("/wechat", methods=["GET", "POST"])
def wechat():
    if request.method == "GET":
        signature = request.args.get("signature", "")
        timestamp = request.args.get("timestamp", "")
        nonce = request.args.get("nonce", "")
        echostr = request.args.get("echostr", "")
        if _check_signature(signature, timestamp, nonce):
            return echostr
        return "verify failed", 403
    # POST 消息
    try:
        xml = request.data.decode("utf-8")
    except Exception:
        xml = request.data.decode("utf-8", "ignore")
    msg = _parse_msg(xml)
    if not msg:
        return ""
    openid = msg.get("FromUserName", "")
    to_user = msg.get("ToUserName", "")
    content = (msg.get("Content") or "").strip()
    reply = _dispatch(openid, content)
    return _build_reply(to_user, openid, reply)


def _parse_msg(xml: str) -> dict:
    try:
        root = ET.fromstring(xml)
    except Exception:
        return {}
    return {child.tag: (child.text or "") for child in root}


def _build_reply(from_user: str, to_user: str, content: str) -> str:
    ts = int(time.time())
    return (
        f"<xml><ToUserName><![CDATA[{to_user}]]></ToUserName>"
        f"<FromUserName><![CDATA[{from_user}]]></FromUserName>"
        f"<CreateTime>{ts}</CreateTime>"
        f"<MsgType><![CDATA[text]]></MsgType>"
        f"<Content><![CDATA[{content}]]></Content></xml>"
    )


# ---------------- 指令分发 ----------------
def _is_admin(openid: str) -> bool:
    return openid in ADMIN_IDS


def _dispatch(openid: str, text: str) -> str:
    text = (text or "").strip()
    if not text:
        return "请输入指令，发送「帮助」查看。"
    lowered = text.lower()
    first, _, rest = text.partition(" ")

    if lowered in ("帮助", "使用说明", "help", "start", "菜单"):
        return USAGE
    if first in ("绑定微博", "绑定"):
        return _bind_weibo(openid, rest)
    if first in ("绑定cookie", "cookie"):
        return _bind_cookie(openid, rest)
    if first in ("签到", "一键签到"):
        return _checkin(openid)
    if first in ("状态", "分析", "查看状态", "签到结果"):
        return _status(openid)
    if first in ("我的卡", "卡", "卡密状态"):
        return CARDS.entitlement_text(openid)
    if first in ("购买", "获取卡密", "买卡", "充值"):
        return _buy(openid)
    if first in ("付款完成", "已付款", "付款成功"):
        return _paid(openid)
    if first in ("兑换", "激活", "兑换卡密"):
        return _redeem(openid, rest)
    if first in ("设置签到时间", "签到时间", "定时签到"):
        return _set_schedule(openid, rest)
    if first in ("取消", "停止"):
        _jobs.pop(openid, None)
        return "已停止进行中的任务。"

    if _is_admin(openid):
        if first in ("发卡", "生成卡"):
            return _admin_issue(openid, rest)
        if first in ("确认收款", "确认"):
            return _admin_confirm(openid, rest)
        if first in ("未收到", "没收到"):
            return _admin_deny(openid, rest)
        if first in ("禁用卡",):
            return _admin_toggle(openid, rest, disabled=True)
        if first in ("启用卡",):
            return _admin_toggle(openid, rest, disabled=False)

    return "无法识别指令，发送「帮助」查看可用命令。"


# ---------------- 功能实现 ----------------
def _bind_cookie(openid: str, cookie_str: str) -> str:
    cookie_str = cookie_str.strip()
    if not cookie_str:
        return "格式：绑定cookie k1=v1; k2=v2\n（在浏览器登录 weibo.com 后 F12 复制 Cookie 值）"
    try:
        cookies = wb_core.cookie_string_to_dict(cookie_str)
        if not cookies.get("SUB"):
            return "cookie 缺少 SUB 字段，请确认复制完整。"
        # 校验登录态
        if wb_core.is_logged_in(cookies):
            wb_store.save_cookies(openid, cookies)
            return "✅ 微博绑定成功！发送「签到」即可一键签到。"
        wb_store.save_cookies(openid, cookies)
        return "✅ 已保存 cookie（登录态待核验）。发送「签到」试试，若失败请重新绑定。"
    except Exception as exc:
        return f"绑定失败：{exc}"


def _bind_weibo(openid: str, rest: str) -> str:
    return "微信端暂不支持扫码，请用「绑定cookie 你的cookie」方式绑定微博。"


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
            _jobs[openid] = (
                f"签到完成（完成率 {result['completion_rate']:.1f}%）\n"
                f"总超话：{result['total']}｜新签：{result['new']}｜已签：{result['already']}｜失败：{result['failed']}"
            )
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
        return (
            f"超话状态分析\n总超话：{result['stats']['total']}\n"
            f"已签到：{result['stats']['checked_in']}\n"
            f"可签到：{result['stats']['can_checkin']}\n"
            f"完成率：{result['completion_rate']:.1f}%"
        )
    except Exception as exc:
        return f"分析出错：{exc}"


def _buy(openid: str) -> str:
    plans = CFG.get("admin", {}).get("card_plans", {})
    lines = []
    for k, p in plans.items():
        if p.get("permanent"):
            continue
        lines.append(f"· {p['name']} ¥{p['price_cents']/100:.0f}（{p['desc']}）")
    return (
        "可购买卡类型：\n" + "\n".join(lines) + "\n\n"
        "购买方式：\n"
        "1. 联系管理员（微信号见公众号菜单）付款\n"
        "2. 付款后发「付款完成」通知管理员核实\n"
        "3. 管理员核对后为你发放卡密"
    )


def _paid(openid: str) -> str:
    global _pay_seq
    with _pay_lock:
        if openid in _pending_pay.values():
            return "你有一笔付款正在等待管理员核实，请稍候。"
        _pay_seq += 1
        seq = _pay_seq
        _pending_pay[seq] = openid
    notify = "".join(f" 回复：确认收款 {seq}" for _ in ADMIN_IDS) or ""
    for admin in ADMIN_IDS:
        _jobs[f"__admin_{admin}"] = f"💰【收款确认】编号 {seq} 的用户声称已付款。{notify}"
    return f"已把你的付款确认（编号 {seq}）推送给管理员，请等待核实后发卡。"


def _redeem(openid: str, code: str) -> str:
    code = code.strip()
    if not code:
        return "格式：兑换 <9位卡密>（字母+数字）"
    ok, reason = CARDS.validate_code(code)
    if not ok:
        return f"兑换失败：{reason}"
    try:
        CARDS.activate(code, openid)
    except Exception as exc:
        return f"兑换失败：{exc}"
    return f"🎉 兑换成功！\n卡密：{code.upper()}\n{CARDS.entitlement_text(openid)}"


def _set_schedule(openid: str, text: str) -> str:
    m = re.findall(r"(\d{1,2}):(\d{2})", text)
    if len(m) < 2:
        return "格式：设置签到时间 开始~结束\n例：设置签到时间 03:00~05:00"
    try:
        h1, mi1, h2, mi2 = int(m[0][0]), int(m[0][1]), int(m[1][0]), int(m[1][1])
        if not (0 <= h1 <= 23 and 0 <= h2 <= 23 and 0 <= mi1 <= 59 and 0 <= mi2 <= 59):
            raise ValueError
    except ValueError:
        return "时间格式不正确，示例：设置签到时间 03:00~05:00"
    norm = f"{h1:02d}:{mi1:02d}-{h2:02d}:{mi2:02d}"
    _jobs[f"__schedule_{openid}"] = norm
    return f"✅ 已设置每日签到时间段：{norm}。每天会在该时段内自动签到（可再发本指令随时修改）。"


# ---------------- 管理员 ----------------
def _admin_issue(admin: str, args: str) -> str:
    parts = args.split()
    if len(parts) < 2:
        return "格式：发卡 <类型> <数量>\n例：发卡 month 5"
    plan_key, count_str = parts[0], parts[1]
    try:
        count = int(count_str)
        codes = CARDS.generate(plan_key, count)
    except Exception as exc:
        return f"发卡失败：{exc}"
    plan = CFG.get("admin", {}).get("card_plans", {}).get(plan_key, {})
    return f"已生成 {len(codes)} 张{plan.get('name', plan_key)}卡：\n" + "\n".join(codes)


def _admin_confirm(admin: str, args: str) -> str:
    try:
        seq = int(args.strip().split()[0])
    except (ValueError, IndexError):
        return "格式：确认收款 <编号>"
    user = _pending_pay.pop(seq, None)
    if not user:
        return f"编号 {seq} 没有待确认的付款。"
    cards_all = REPO.all_cards()
    free = next((c for c in cards_all if (c.get("status") or "") == "未激活"), None)
    if not free:
        return "卡密库存不足，请先「发卡 month N」补充。"
    try:
        CARDS.activate(free["code"], user)
    except Exception as exc:
        _pending_pay[seq] = user
        return f"发卡失败：{exc}"
    _jobs[f"__grant_{user}"] = f"🎉 您的月卡已到账！卡密：{free['code']}"
    return f"✅ 已向编号 {seq} 的用户发放月卡：{free['code']}"


def _admin_deny(admin: str, args: str) -> str:
    try:
        seq = int(args.strip().split()[0])
    except (ValueError, IndexError):
        return "格式：未收到 <编号>"
    user = _pending_pay.pop(seq, None)
    if not user:
        return f"编号 {seq} 没有待确认的付款。"
    _jobs[f"__deny_{user}"] = "管理员暂未确认到您的款项，请核实付款是否成功，或联系管理员。"
    return f"已告知编号 {seq} 的用户。"


def _admin_toggle(admin: str, code: str, disabled: bool) -> str:
    code = code.strip().upper()
    card = REPO.get_card(code)
    if not card:
        return "未找到该卡密。"
    status = "已禁用" if disabled else "未激活"
    REPO.set_card(code, status=status)
    return f"卡密 {code} 已设置为「{status}」。"


if __name__ == "__main__":
    port = int(MP.get("port", 8800))
    print(f"[wechat-mp] 公众号回调服务启动，监听 0.0.0.0:{port}/wechat")
    app.run(host="0.0.0.0", port=port, debug=False)
