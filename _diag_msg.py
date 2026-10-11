# -*- coding: utf-8 -*-
"""诊断 GetAllMessage 消息对象结构（带进度和异常）。"""
import sys, traceback
sys.path.insert(0, "D:/weibo_claw_bot")
from wxauto4 import WeChat

wx = WeChat()
print("1 已连接")
try:
    wx.ChatWith("文件传输助手")
    print("2 ChatWith 成功")
except Exception as e:
    print("ChatWith err:", e)
    traceback.print_exc()
    sys.exit(1)
try:
    msgs = wx.GetAllMessage()
    print("3 GetAllMessage 条数:", len(msgs))
    for m in msgs[-5:]:
        print("   type:", type(m))
        print("   attrs:", [a for a in dir(m) if not a.startswith('_')])
        vals = {}
        for a in dir(m):
            if a.startswith('_'): continue
            try:
                v = getattr(m, a)
                if isinstance(v, (str, int, bool, float, type(None), list, dict)):
                    vals[a] = v
            except Exception:
                pass
        print("   vals:", vals)
except Exception as e:
    print("GetAllMessage err:", e)
    traceback.print_exc()
