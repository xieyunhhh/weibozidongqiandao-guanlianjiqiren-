# -*- coding: utf-8 -*-
"""临时脚本：生成N张永久卡并写入飞书卡密表。用完删除。"""
import secrets
import sys

sys.path.insert(0, "D:/weibo_claw_bot")
from config import load_config, build_services  # noqa: E402

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
N = 5


def main() -> None:
    cfg = load_config()
    repo = build_services(cfg)["repo"]
    existing = {c["code"].upper() for c in repo.all_cards()}
    codes = []
    while len(codes) < N:
        k = "".join(secrets.choice(ALPHABET) for _ in range(9))
        if k not in existing and k not in codes:
            codes.append(k)
    ok = 0
    for c in codes:
        rid = repo.add_card(c, "永久卡", 0)
        if rid:
            ok += 1
    print(f"永久卡: 成功 {ok}/{len(codes)}")
    print("卡密:", codes)


if __name__ == "__main__":
    main()
