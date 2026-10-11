# -*- coding: utf-8 -*-
import requests, json, time

def log(s):
    print(s, flush=True)

app_id = "cli_aa34b85002b8dcd8"
app_secret = "fheXv3ILkSwp8OYJhZ5GOdKTtGkhjbWk"

log("start conn test " + time.strftime("%H:%M:%S"))
try:
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=20,
    )
    log("HTTP " + str(r.status_code) + " " + time.strftime("%H:%M:%S"))
    log(r.text[:400])
except Exception as e:
    log("ERR " + str(e) + " " + time.strftime("%H:%M:%S"))
