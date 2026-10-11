# -*- coding: utf-8 -*-
"""临时测试：wxautox4 (Plus) 连接当前微信 4.1.x。"""
import sys, traceback

wx_mod = None
for modname in ("wxautox4", "wxauto"):
    try:
        m = __import__(modname)
        WeChat = getattr(m, "WeChat", None)
        if WeChat:
            wx_mod = modname
            print(f"[INFO] 使用模块: {modname}")
            break
    except Exception as e:
        print(f"[WARN] import {modname} 失败: {e}")

if not wx_mod:
    print("[FAIL] 无法导入 WeChat")
    sys.exit(1)

try:
    wx = WeChat()
    print("[OK] 已连接微信客户端")
    try:
        lst = wx.GetSessionList()
        print(f"[OK] 会话列表数量: {len(lst)}")
        for s in lst[:5]:
            print("  -", s)
    except Exception as e:
        print(f"[WARN] 获取会话列表失败: {type(e).__name__}: {e}")
except Exception as e:
    print("[FAIL] 连接微信失败:")
    traceback.print_exc()
