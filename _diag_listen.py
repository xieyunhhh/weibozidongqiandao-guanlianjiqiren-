# -*- coding: utf-8 -*-
"""诊断监听机制：监听文件传输助手，自己给自己发消息，看回调是否触发。"""
import sys, time
sys.path.insert(0, "D:/weibo_claw_bot")
from wxauto4 import WeChat

wx = WeChat()
got = []

def cb(msg, chat):
    try:
        who = getattr(chat, "who", "?")
        typ = getattr(msg, "type", "?")
        content = getattr(msg, "content", "")
        sender = getattr(msg, "sender", "")
        got.append(1)
        print(f"CALLBACK who={who!r} type={typ!r} sender={sender!r} content={content!r}")
    except Exception as e:
        print("cb err", e)

try:
    r = wx.AddListenChat(nickname="文件传输助手", callback=cb)
    print("AddListenChat ->", getattr(r, "message", r))
except Exception as e:
    print("AddListenChat err", e)

wx.StartListening()
print("开始监听…")
try:
    r = wx.SendMsg("测试监听12345", who="文件传输助手")
    print("SendMsg ok=", getattr(r, "is_success", lambda: None)())
except Exception as e:
    print("SendMsg err", e)

time.sleep(20)
print("收到回调条数:", len(got))
wx.StopListening()
print("已停止监听")
