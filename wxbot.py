# -*- coding: utf-8 -*-
"""微信个人号机器人（wxauto4 + 微信 PC 客户端 UI 自动化）。

客户添加机器人微信号为好友后，直接发文字指令即可使用：
绑定微博（支持二维码扫码登录）、一键签到、卡密兑换、购买、我的卡、设置签到时间等。
复用 D:\\weibo_claw_bot 现有模块：weibo/core.py（签到）、weibo/login.py（二维码登录）、
weibo/store.py（微博cookie）、card/service.py（卡密）、feishu/bitable.py（卡密表）、config.py。

运行环境：Python 3.12（venv_wx），需微信 PC 客户端（4.1.8.107 兼容版）已登录并保持打开。
启动：venv_wx\\Scripts\\python.exe wxbot.py
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import threading
import time
import traceback
import uuid
from collections import deque

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from wxauto4 import WeChat  # noqa: E402
from config import load_config, build_services  # noqa: E402
from weibo import store as wb_store  # noqa: E402
from weibo import core as wb_core  # noqa: E402
from weibo import login as wb_login  # noqa: E402
from card import pending  # noqa: E402

CFG = load_config()
SVC = build_services(CFG)
CARDS = SVC["cards"]
REPO = SVC["repo"]
CUSTOMERS = SVC.get("customers")


def _reg_customer(channel: str, key: str, **kw) -> None:
    """登记/更新微信客户到飞书客户台账（尽力而为）。"""
    if not CUSTOMERS or not key:
        return
    try:
        CUSTOMERS.register("微信", channel, key, **kw)
    except Exception:
        pass


WECHAT_DRIVER = CFG.get("weibo", {}).get("chromedriver") or ""

wx: WeChat | None = None

# 进行中的耗时任务（签到）：nickname -> 状态文本
_jobs: dict[str, str] = {}
# 二维码登录任务：nickname -> {qr_id, result, msg}
_qr_jobs: dict[str, dict] = {}

USAGE = (
    "📖 微博超话一键签到 · 使用说明\n\n"
    "1. 发送「兑换 卡密」激活（没有卡先发「购买」）\n"
    "2. 发送「绑定」扫码登录微博（或发「绑定cookie 你的cookie」粘贴cookie）\n"
    "3. 发送「签到」自动签到全部超话，稍后发「状态」查看结果\n\n"
    "【指令】\n"
    "· 帮助/使用说明 —— 本说明\n"
    "· 绑定 —— 获取微博登录二维码，用微博APP扫码登录\n"
    "· 绑定cookie <cookie> —— 粘贴微博cookie绑定（兜底）\n"
    "· 签到 —— 一键签到全部超话（后台执行，完成后发「状态」看结果）\n"
    "· 状态/分析 —— 查看超话签到情况\n"
    "· 我的卡 —— 查看卡密状态\n"
    "· 购买/获取卡密 —— 查看价格并联系管理员发卡\n"
    "· 兑换 <卡密> —— 激活卡密\n"
    "· 设置签到时间 03:00~05:00 —— 设置每日自动签到时间段\n\n"
    "💡 卡密为一次性激活码，兑换后尽快使用。"
)


# ---------------- 消息回调与回复 ----------------
def _reply(nick: str, text: str) -> None:
    if not text:
        return
    try:
        r = wx.SendMsg(text, who=nick)
        ok = bool(getattr(r, "is_success", False))
        print(f"[send->{nick}] ok={ok}")
    except Exception as e:
        print(f"[send->{nick}] err: {e}\n{traceback.format_exc()}")


def process_msg(name: str, content: str) -> None:
    content = (content or "").strip()
    if not content:
        return
    _recent_msgs.append(f"{time.strftime('%H:%M')} {name}: {content[:60]}")
    print(f"[recv {name}] {content[:60]}")
    try:
        out = _handle(name, content)
    except Exception as e:
        print(f"[handle {name}] err: {e}\n{traceback.format_exc()}")
        out = "系统繁忙，请稍后重试。"
    if out:
        _reply(name, out)


# ---------------- 指令分发 ----------------
def _handle(nick: str, text: str) -> str:
    if not text:
        return "请输入指令，发送「帮助」查看。"
    lowered = text.lower()
    first, _, rest = text.partition(" ")

    if lowered in ("帮助", "使用说明", "help", "start", "菜单"):
        return USAGE
    if first in ("绑定微博", "绑定", "二维码登录", "扫码登录", "登录"):
        return _cmd_qr_bind(nick)
    if first in ("绑定cookie", "cookie"):
        return _bind_cookie(nick, rest)
    if first in ("签到", "一键签到"):
        return _checkin(nick)
    if first in ("状态", "分析", "查看状态", "签到结果"):
        return _status(nick)
    if first in ("我的卡", "卡", "卡密状态"):
        return CARDS.entitlement_text(nick)
    if first in ("购买", "获取卡密", "买卡", "充值"):
        return _buy()
    if first in ("付款完成", "已付款", "付款成功"):
        return _paid(nick)
    if first in ("兑换", "激活", "兑换卡密"):
        return _redeem(nick, rest)
    if first in ("设置签到时间", "签到时间", "定时签到"):
        return _set_schedule(nick, rest)
    if first in ("取消", "停止"):
        _jobs.pop(nick, None)
        return "已停止进行中的任务。"

    return "无法识别指令，发送「帮助」查看可用命令。"


# ---------------- 功能实现 ----------------
def _cmd_qr_bind(nick: str) -> str:
    """发起微博二维码登录：生成二维码图发给用户，后台等待扫码成功后自动绑定。"""
    if nick in _qr_jobs:
        return "二维码登录进行中，请先用微博APP扫描已发送的二维码。"
    qr_save = os.path.join(BASE, "storage", f"qr_{int(time.time() * 1000)}.png")
    try:
        qr_src, qr_id = wb_login.start_qr_login(chromedriver_path=WECHAT_DRIVER, callback=lambda t: None)
        png = wb_login.qr_src_to_file(qr_src, qr_save)
        try:
            wx.SendFiles(png, who=nick)
            print(f"[send qr img->{nick}] ok")
        except Exception as e:
            print(f"[send qr img->{nick}] err: {e}")
        job = {"qr_id": qr_id, "result": None, "msg": None}
        _qr_jobs[nick] = job
        threading.Thread(target=_qr_wait, args=(nick, qr_id, job), daemon=True).start()
        return "📷 二维码已发送，请用「微博APP」扫描并确认登录。登录成功将自动绑定，无需再发cookie。"
    except Exception as exc:
        return f"二维码登录启动失败：{exc}"


def _qr_wait(nick: str, qr_id: str, job: dict) -> None:
    try:
        cookies = wb_login.wait_qr_scan(qr_id, timeout_sec=300, callback=lambda t: None)
        wb_store.save_cookies(nick, cookies)
        _reg_customer("单聊", nick, weibo_bound="已绑定")
        job["result"] = "ok"
        job["msg"] = "✅ 微博扫码登录成功，已自动绑定！发送「签到」即可一键签到。"
    except Exception as e:
        job["result"] = "fail"
        job["msg"] = f"⏰ 扫码登录失败/超时：{e}，可重新发送「绑定」获取新二维码。"


def _bind_cookie(nick: str, cookie_str: str) -> str:
    cookie_str = cookie_str.strip()
    if not cookie_str:
        return "格式：绑定cookie k1=v1; k2=v2\n（浏览器登录 weibo.com 后 F12 复制 Cookie 值）"
    try:
        cookies = wb_core.cookie_string_to_dict(cookie_str)
        if not cookies.get("SUB"):
            return "cookie 缺少 SUB 字段，请确认复制完整。"
        if wb_core.is_logged_in(cookies):
            wb_store.save_cookies(nick, cookies)
            _reg_customer("单聊", nick, weibo_bound="已绑定")
            return "✅ 微博绑定成功！发送「签到」即可一键签到。"
        wb_store.save_cookies(nick, cookies)
        _reg_customer("单聊", nick, weibo_bound="已绑定")
        return "✅ 已保存 cookie（登录态待核验）。发送「签到」试试，若失败请重新绑定。"
    except Exception as exc:
        return f"绑定失败：{exc}"


def _checkin(nick: str) -> str:
    if not CARDS.is_entitled(nick):
        return "你还没有有效卡密。发送「购买」获取，或联系管理员发卡。"
    cookies = wb_store.load_cookies(nick)
    if not cookies:
        return "你还没有绑定微博。发送「绑定」扫码登录，或「绑定cookie 你的cookie」绑定。"
    if nick in _jobs:
        return "你有一个签到正在后台执行，请稍后发「状态」查看。"
    _jobs[nick] = "正在签到…"

    def _run():
        try:
            result = wb_core.auto_checkin(cookies, delay=0.3)
            _jobs[nick] = (
                f"签到完成（完成率 {result['completion_rate']:.1f}%）\n"
                f"总超话：{result['total']}｜新签：{result['new']}｜已签：{result['already']}｜失败：{result['failed']}"
            )
        except Exception as exc:
            _jobs[nick] = f"签到出错：{exc}"

    threading.Thread(target=_run, daemon=True).start()
    return "⏳ 已开始一键签到（后台执行，需几十秒）。完成后发送「状态」查看结果。"


def _status(nick: str) -> str:
    if nick in _jobs:
        return _jobs[nick]
    if not CARDS.is_entitled(nick):
        return "你还没有有效卡密。发送「购买」获取。"
    cookies = wb_store.load_cookies(nick)
    if not cookies:
        return "你还没有绑定微博。发送「绑定」扫码登录。"
    try:
        result = wb_core.analyze_status(cookies)
        st = result.get("stats", {})
        return (
            f"超话状态分析\n总超话：{st.get('total', 0)}\n"
            f"已签到：{st.get('checked_in', 0)}\n"
            f"可签到：{st.get('can_checkin', 0)}\n"
            f"完成率：{result.get('completion_rate', 0) * 100:.1f}%"
        )
    except Exception as exc:
        return f"分析出错：{exc}"


def _buy() -> str:
    plans = CFG.get("admin", {}).get("card_plans", {})
    lines = []
    for k, p in plans.items():
        if p.get("permanent"):
            continue
        lines.append(f"· {p['name']} ¥{p['price_cents'] / 100:.0f}（{p['desc']}）")
    return (
        "可购买卡类型：\n" + "\n".join(lines) + "\n\n"
        "购买方式：\n"
        "1. 联系管理员付款\n"
        "2. 付款后发「付款完成」通知管理员核实\n"
        "3. 管理员核对后为你发放卡密"
    )


def _paid(nick: str) -> str:
    try:
        seq = pending.add_payment(pending.PLATFORM_WX, nick)
    except Exception as exc:
        return f"提交付款确认失败：{exc}"
    _reg_customer("单聊", nick, note=f"提交付款确认（编号 {seq}）")
    return f"已把你的付款确认（编号 {seq}）推送给管理员（飞书），请等待核实后发卡。"


def _redeem(nick: str, code: str) -> str:
    code = code.strip()
    if not code:
        return "格式：兑换 <9位卡密>（字母+数字）"
    ok, reason = CARDS.validate_code(code)
    if not ok:
        return f"兑换失败：{reason}"
    try:
        CARDS.activate(code, nick)
    except Exception as exc:
        return f"兑换失败：{exc}"
    _reg_customer("单聊", nick,
                  weibo_bound="已绑定" if wb_store.load_cookies(nick) else None,
                  card_type=(REPO.get_card(code) or {}).get("type", ""),
                  expire_at=(REPO.get_card(code) or {}).get("expire_at", "") or None)
    return f"🎉 兑换成功！\n卡密：{code.upper()}\n{CARDS.entitlement_text(nick)}"


def _set_schedule(nick: str, text: str) -> str:
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
    _jobs[f"__schedule_{nick}"] = norm
    return f"✅ 已设置每日签到时间段：{norm}。每天会在该时段内自动签到（可再发本指令随时修改）。"


# ---------------- 飞书远程操控微信（本地任务队列 IPC） ----------------
# 飞书机器人（bot/commands.py）把管理指令写入 storage/wx_tasks/<id>.json，
# 本机器人每次轮询时读取执行，结果写回 storage/wx_results/<id>.json 供飞书读取回复。
_WX_TASKS_DIR = os.path.join(BASE, "storage", "wx_tasks")
_WX_RESULTS_DIR = os.path.join(BASE, "storage", "wx_results")
_recent_log: deque = deque(maxlen=50)   # 最近操作日志（供飞书查看状态）
_recent_msgs: deque = deque(maxlen=30)  # 最近收到的微信消息（供飞书查看）


def _log(msg: str) -> None:
    print(msg, flush=True)
    _recent_log.append(f"[{time.strftime('%H:%M:%S')}] {msg}")


def _run_wx_admin_task(task: dict) -> tuple[bool, str]:
    """执行一条来自飞书的管理指令，返回 (是否成功, 回复文本)。"""
    action = task.get("action", "")
    p = task.get("params", {}) or {}
    if action == "status":
        lines = "\n".join(list(_recent_log)[-15:])
        return True, f"✅ 微信机器人运行中（连续扫描）\n最近动态：\n{lines}" if lines else "✅ 微信机器人运行中（连续扫描），暂无动态。"
    if action == "view":
        nick = p.get("nick", "").strip()
        if not nick:
            return False, "格式：微信 查看 <微信昵称>"
        bound = bool(wb_store.load_cookies(nick))
        try:
            ent = CARDS.entitlement_text(nick)
        except Exception as e:
            ent = f"（查询卡密异常：{e}）"
        return True, f"微信用户：{nick}\n微博绑定：{'✅是' if bound else '❌否'}\n卡密信息：\n{ent}"
    if action == "checkin":
        nick = p.get("nick", "").strip()
        if not nick:
            return False, "格式：微信 签到 <微信昵称>"
        return True, _checkin(nick)
    if action == "issue_card":
        nick = p.get("nick", "").strip()
        if not nick:
            return False, "格式：微信 发卡 <微信昵称> [卡密]"
        code = p.get("code", "").strip()
        if code:
            ok, reason = CARDS.validate_code(code)
            if not ok:
                return False, f"卡密无效：{reason}"
            try:
                CARDS.activate(code, nick)
            except Exception as e:
                return False, f"发卡失败：{e}"
            _reg_customer("单聊", nick,
                          card_type=(REPO.get_card(code) or {}).get("type", "月卡"),
                          expire_at=(REPO.get_card(code) or {}).get("expire_at", "") or None,
                          note="管理员飞书远程发卡")
            _reply(nick, f"🎉 您的月卡已到账！卡密：{code}")
            return True, f"✅ 已向微信用户 {nick} 发放卡密 {code} 并通知。"
        try:
            cards_all = REPO.all_cards()
        except Exception as e:
            return False, f"读取卡密库存失败：{e}"
        free = next((c for c in cards_all if (c.get("status") or "") == "未激活"), None)
        if not free:
            return False, "卡密库存不足，请先在飞书「发卡 month N」补充。"
        try:
            CARDS.activate(free["code"], nick)
        except Exception as e:
            return False, f"发卡失败：{e}"
        _reg_customer("单聊", nick,
                      card_type=free.get("type", "月卡"),
                      expire_at=free.get("expire_at", "") or None,
                      note="管理员飞书远程发卡")
        _reply(nick, f"🎉 您的月卡已到账！卡密：{free['code']}")
        return True, f"✅ 已向微信用户 {nick} 发放月卡 {free['code']} 并通知。"
    if action == "messages":
        lines = list(_recent_msgs)
        if not lines:
            return True, "暂未收到新消息。"
        return True, "微信端最近消息：\n" + "\n".join(lines[-20:])
    if action == "notify":
        nick = p.get("nick", "").strip()
        text = (p.get("text", "") or "").strip()
        if not nick or not text:
            return False, "缺少微信昵称或通知内容。"
        _reply(nick, text)
        return True, f"已通知微信用户 {nick}"
    return False, f"未知操作：{action}"


def _drain_wx_tasks() -> None:
    """扫描并执行飞书下发的管理任务（在轮询单线程内执行，天然串行安全）。"""
    try:
        for tf in glob.glob(os.path.join(_WX_TASKS_DIR, "*.json")):
            try:
                with open(tf, "r", encoding="utf-8") as f:
                    task = json.load(f)
                rid = task.get("id", os.path.basename(tf)[:-5])
                try:
                    ok, text = _run_wx_admin_task(task)
                except Exception as e:
                    ok, text = False, f"执行出错：{e}\n{traceback.format_exc()}"
                os.makedirs(_WX_RESULTS_DIR, exist_ok=True)
                with open(os.path.join(_WX_RESULTS_DIR, f"{rid}.json"), "w", encoding="utf-8") as f:
                    json.dump({"id": rid, "ok": ok, "text": text, "done_at": time.strftime("%Y-%m-%d %H:%M:%S")},
                              f, ensure_ascii=False, indent=2)
                _log(f"[wx-admin] 执行 {task.get('action')} -> {rid}")
            except Exception as e:
                _log(f"[wx-admin] 任务处理失败 {tf}: {e}\n{traceback.format_exc()}")
            finally:
                try:
                    os.remove(tf)
                except Exception:
                    pass
    except Exception as e:
        _log(f"[wx-admin] 扫描任务失败: {e}")


# ---------------- 主流程 ----------------
# ---------------- 轮询模式 ----------------
_processed: set[str] = set()
_last_sig: dict[str, tuple] = {}

# 群聊里命中这些关键词才回复（避免刷屏打扰）
_KEYWORDS = ("帮助", "使用说明", "绑定", "签到", "打卡", "兑换", "卡密", "购买", "套餐", "价格", "时间段", "确认收款", "剩余")


def _is_keyword(content: str) -> bool:
    low = content.lower()
    return any(k.lower() in low for k in _KEYWORDS)


def poll_once() -> None:
    _drain_wx_tasks()  # 先处理飞书下发的管理任务
    try:
        sessions = wx.GetSession()
    except Exception as e:
        print(f"[poll sessions err] {e}")
        return
    for s in sessions:
        name = getattr(s, "name", None)
        if not name:
            continue
        sig = (getattr(s, "time", ""), getattr(s, "content", ""))
        unread = bool(getattr(s, "isnew", False)) or (getattr(s, "new_count", 0) or 0) > 0
        if _last_sig.get(name) == sig and not unread:
            continue  # 该会话无新消息
        try:
            wx.ChatWith(name)
        except Exception as e:
            print(f"[chatwith {name}] err {e}")
            continue
        try:
            msgs = wx.GetAllMessage()
        except Exception as e:
            print(f"[getmsg {name}] err {e}")
            continue
        for m in msgs:
            if getattr(m, "type", "") != "text":
                continue
            sender = getattr(m, "sender", "")
            if sender == "self":
                continue  # 自己发的不处理
            ci = getattr(m, "chat_info", {}) or {}
            ct = ci.get("chat_type")
            content = (getattr(m, "content", "") or "").strip()
            if ct == "friend":
                pass  # 单聊：全部处理
            elif ct == "group":
                if not _is_keyword(content):
                    continue  # 群聊：只命中关键词才回复
            else:
                continue  # 服务号等跳过
            # 用内容+发送者指纹去重（微信消息 id 在重开窗口后会变，hash_text 更稳定）
            mid = getattr(m, "hash_text", "") or getattr(m, "id", "") or getattr(m, "hash", "")
            if not mid or mid in _processed:
                continue
            _processed.add(mid)
            process_msg(name, content)
        _last_sig[name] = sig
    # 控制已处理集合大小
    if len(_processed) > 5000:
        _processed.clear()
    # 处理二维码登录结果（后台线程写入 result，主线程发通知）
    for nick, job in list(_qr_jobs.items()):
        if job["result"] is not None:
            _reply(nick, job["msg"])
            del _qr_jobs[nick]


def main() -> None:
    global wx
    wx = WeChat()
    myinfo = wx.GetMyInfo()
    print(f"[wx] 机器人登录：{myinfo}")
    # 预取历史：把所有会话已存在的单聊消息标记为已处理，之后只处理新消息
    try:
        sessions = wx.GetSession()
        for s in sessions:
            name = getattr(s, "name", None)
            if not name:
                continue
            try:
                wx.ChatWith(name)
                for m in wx.GetAllMessage():
                    if getattr(m, "type", "") != "text":
                        continue
                    sender = getattr(m, "sender", "")
                    if sender == "self":
                        continue
                    ci = getattr(m, "chat_info", {}) or {}
                    if ci.get("chat_type") != "friend":
                        continue
                    mid = getattr(m, "hash_text", "") or getattr(m, "id", "") or getattr(m, "hash", "")
                    if mid:
                        _processed.add(mid)
                _last_sig[name] = (getattr(s, "time", ""), getattr(s, "content", ""))
            except Exception as e:
                print(f"[prefetch {name}] err {e}")
        print(f"[wx] 历史消息已标记，共 {len(_processed)} 条，之后只处理新消息")
    except Exception as e:
        print(f"[wx] 预取历史失败: {e}")
    print("[wx] 启动轮询模式（连续扫描无间隔，单聊全处理/群聊关键词回复）")
    while True:
        try:
            poll_once()
        except Exception as e:
            print(f"[poll crash] {e}\n{traceback.format_exc()}")
            time.sleep(1)  # 防止异常后极速重试导致死循环


if __name__ == "__main__":
    main()
