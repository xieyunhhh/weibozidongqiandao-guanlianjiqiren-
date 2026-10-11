# -*- coding: utf-8 -*-
"""诊断：查看 GetSession 返回的 SessionElement 结构。"""
import sys
sys.path.insert(0, "D:/weibo_claw_bot")
from wxauto4 import WeChat

wx = WeChat()
sessions = wx.GetSession()
print("会话数:", len(sessions))
for i, s in enumerate(sessions):
    print(f"--- 会话[{i}] ---")
    print("type:", type(s))
    attrs = [a for a in dir(s) if not a.startswith('_')]
    print("attrs:", attrs)
    for a in attrs:
        try:
            print(f"  {a} = {getattr(s, a)!r}")
        except Exception as e:
            print(f"  {a} ERR {e}")
    if i >= 4:
        break
