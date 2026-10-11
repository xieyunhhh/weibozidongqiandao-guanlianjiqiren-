# -*- coding: utf-8 -*-
"""检查微信窗口当前可见子窗口标题。"""
import sys, traceback
sys.path.insert(0, "D:/weibo_claw_bot")
from wxauto4 import WeChat

try:
    wx = WeChat()
    print("[OK] 连接成功")
    try:
        subs = wx.GetAllSubWindow()
        print("子窗口数量:", len(subs))
        for sw in subs:
            try:
                print("  子窗口:", sw)
            except Exception as e:
                print("  子窗口打印err", e)
    except Exception as e:
        print("GetAllSubWindow err:", e)
        traceback.print_exc()
    try:
        print("myinfo:", wx.GetMyInfo())
    except Exception as e:
        print("GetMyInfo err:", e)
except Exception as e:
    print("[FAIL] 初始化失败:", e)
    traceback.print_exc()
