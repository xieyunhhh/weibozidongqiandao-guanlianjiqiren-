# -*- coding: utf-8 -*-
"""临时测试：验证 wxauto 能否连接当前运行的微信 PC 客户端。"""
import sys
sys.path.insert(0, "D:/weibo_claw_bot")

from wxauto import WeChat

try:
    wx = WeChat()
    print("[OK] 已连接微信客户端")
    try:
        lst = wx.GetSessionList()
        print(f"[OK] 会话列表数量: {len(lst)}")
        for s in lst[:5]:
            print("  -", s)
    except Exception as e:
        print(f"[WARN] 获取会话列表失败: {e}")
except Exception as e:
    print(f"[FAIL] 连接微信失败: {type(e).__name__}: {e}")
