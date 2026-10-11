# -*- coding: utf-8 -*-
"""临时测试：验证 wxauto4 能否连接当前微信 4.1.x。"""
import sys, traceback

# 尝试两种导入方式
wx_mod = None
try:
    from wxauto4 import WeChat
    wx_mod = "wxauto4"
except Exception:
    try:
        from wxauto import WeChat
        wx_mod = "wxauto"
    except Exception as e:
        print("两种导入都失败:", e)
        sys.exit(1)

print(f"[INFO] 使用模块: {wx_mod}, WeChat = {WeChat}")

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
    print(f"[FAIL] 连接微信失败:")
    traceback.print_exc()
