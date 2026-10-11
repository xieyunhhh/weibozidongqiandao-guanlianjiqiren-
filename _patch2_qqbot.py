# -*- coding: utf-8 -*-
"""增量修复：补上 _status 缺失的 except 子句。"""
p = r"D:\weibo_claw_bot\qqbot.py"
with open(p, encoding="utf-8") as f:
    s = f.read()

old = '        return "\\n".join(lines)\n\n\nPAY_QR_PATH = os.path.join(BASE, "storage", "pay_qrcode.png")'
new = ('        return "\\n".join(lines)\n'
       '    except Exception as exc:\n'
       '        return f"分析出错：{exc}"\n'
       '\n\nPAY_QR_PATH = os.path.join(BASE, "storage", "pay_qrcode.png")')

cnt = s.count(old)
assert cnt == 1, f"锚点不唯一或不存在: {cnt}"
s = s.replace(old, new)
with open(p, "w", encoding="utf-8") as f:
    f.write(s)
print("已补 except，写回")
