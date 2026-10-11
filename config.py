# -*- coding: utf-8 -*-
"""配置加载：读取 config.json（不存在则提示用 config.example.json 复制）。"""
from __future__ import annotations

import json
import os
from typing import Any

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


def load_config(path: str = CONFIG_PATH) -> dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"缺少配置文件 {path}。请复制 config.example.json 为 config.json 并填写真实值。"
        )
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg


def _real(v: Any) -> Any:
    """把占位符/空字符串归一化为空值，避免把占位符当真实配置。"""
    if not isinstance(v, str):
        return v
    v = v.strip()
    if not v or "*" in v or "PLACEHOLDER" in v.upper():
        return ""
    return v


def build_services(cfg: dict[str, Any]):
    """根据配置组装各服务对象（供 bot 与测试复用）。"""
    from card import CardService
    from feishu import CardRepository, CustomerRepository

    feishu_cfg = cfg.get("feishu", {})
    repo = CardRepository(
        app_id=_real(feishu_cfg.get("app_id", "")),
        app_secret=_real(feishu_cfg.get("app_secret", "")),
        app_token=_real(feishu_cfg.get("app_token", "")),
        card_table_id=_real(feishu_cfg.get("card_table_id", "")),
    )
    customers = CustomerRepository(
        app_id=_real(feishu_cfg.get("app_id", "")),
        app_secret=_real(feishu_cfg.get("app_secret", "")),
        app_token=_real(feishu_cfg.get("app_token", "")),
        table_id=_real(feishu_cfg.get("customer_table_id", "")),
    )
    cards = CardService(repo, cfg.get("admin", {}).get("card_plans", {}))
    return {"repo": repo, "cards": cards, "customers": customers}
