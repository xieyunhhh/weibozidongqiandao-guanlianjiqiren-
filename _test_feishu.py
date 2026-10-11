# -*- coding: utf-8 -*-
"""实测：微信环境(venv_wx)能否连飞书卡密表。"""
import sys
sys.path.insert(0, "D:/weibo_claw_bot")
from config import load_config, build_services

cfg = load_config()
feishu = cfg.get("feishu", {})
print("飞书配置: app_token=", feishu.get("app_token"), " table_id=", feishu.get("card_table_id"))

svc = build_services(cfg)
repo = svc["repo"]
cards = repo.all_cards()
print("✅ 飞书卡密表连接成功，共", len(cards), "条记录")
for c in cards[:6]:
    print("  -", c.get("code"), "| 状态:", c.get("status"), "| 计划:", c.get("plan"), "| 绑定:", c.get("user"))
