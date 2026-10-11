# -*- coding: utf-8 -*-
"""独立测试：无头Edge打开微博登录页，定位并截图二维码。"""
import time, sys
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By

DRIVER = r"D:\weibo_claw_bot\drivers\msedgedriver.exe"
LOGIN_URL = ("https://passport.weibo.com/sso/signin?entry=wapsso&source=wapssowb"
             "&url=https%3A%2F%2Fm.weibo.cn%2Fp%2Ftabbar%3Fcontainerid%3D100803_-_recentvisit")

opts = Options()
opts.add_argument("--headless=new")
opts.add_argument("--disable-gpu")
opts.add_argument("--no-sandbox")
opts.add_argument("--window-size=800,700")
opts.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0")

driver = webdriver.Edge(service=Service(DRIVER), options=opts)
print("1 浏览器已启动")
driver.get(LOGIN_URL)
print("2 已打开登录页，等待加载…")
time.sleep(6)

# 尝试多种二维码选择器
selectors = [
    "img[src*='qr']", ".qrcode img", "#qrcode img", "img[alt*='二维码']",
    "img[alt*='QR']", ".W_login_qrcode img", ".code img", "iframe img",
]
found = None
for sel in selectors:
    try:
        el = driver.find_element(By.CSS_SELECTOR, sel)
        if el:
            found = el
            print(f"3 找到二维码元素: {sel} src={el.get_attribute('src')[:120]}")
            break
    except Exception:
        pass

if found:
    try:
        found.screenshot(r"D:\weibo_claw_bot\_qr_test.png")
        print("4 已截取二维码元素 -> _qr_test.png")
    except Exception as e:
        print("4 元素截图失败:", e)
        driver.save_screenshot(r"D:\weibo_claw_bot\_qr_page.png")
        print("4 已保存整页截图 _qr_page.png")
else:
    print("3 未找到二维码元素，保存整页截图")
    driver.save_screenshot(r"D:\weibo_claw_bot\_qr_page.png")

# 打印当前标题和部分源码确认页面
print("5 title:", driver.title)
driver.quit()
print("6 完成")
