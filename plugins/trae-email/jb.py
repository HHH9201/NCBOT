#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trae 批量注册脚本 (单进程稳定版)
功能：
1. 串行注册多个账号，避免 Socket.io 连接冲突
2. 全自动流程

依赖：
    pip install selenium python-socketio[client]

用法：
    python trae_register_batch.py --count 10
"""

import json
import time
import random
import string
import re
import urllib.parse
import urllib.request
import threading
import argparse
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

# 导入 selenium
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
except ImportError:
    print("[错误] selenium 未安装，请运行: pip install selenium")
    exit(1)

# 导入 socketio
try:
    import socketio
    SOCKETIO_AVAILABLE = True
except ImportError:
    SOCKETIO_AVAILABLE = False
    print("[错误] python-socketio 未安装，请运行: pip install python-socketio[client]")
    exit(1)


# ==================== 配置 ====================

TEMPMAIL_DOMAIN = "tempmail.cn"
TRAEE_REGISTER_URL = "https://www.trae.ai/sign-up"

TIMEOUT = {
    'page_load': 10,
    'element': 5,
    'verification_code': 120,
    'short_wait': 0.5,
    'medium_wait': 1,
}


# ==================== 工具函数 ====================

def generate_random_shortid(length: int = 8) -> str:
    charset = string.ascii_lowercase + string.digits
    return ''.join(random.choices(charset, k=length))


def generate_password(length: int = 12) -> str:
    charset = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(random.choices(charset, k=length))


def extract_verification_code(text: str) -> Optional[str]:
    patterns = [
        r'Trae\s+(\d{6})',
        r'(?i)verification\s+code[:\s]*(\d{6})',
        r'(?i)code[:\s]*(\d{6})',
        r'\b(\d{6})\b',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


# ==================== 单个账号注册 ====================

def register_one_account(account_index: int, total: int, headless: bool = True) -> Optional[Dict]:
    """注册单个账号"""
    print(f"\n{'='*50}")
    print(f"[注册] 第 {account_index}/{total} 个账号")
    print(f"{'='*50}")
    
    # 生成邮箱和密码
    shortid = generate_random_shortid(8)
    email = f"{shortid}@{TEMPMAIL_DOMAIN}"
    password = generate_password()
    
    print(f"[信息] 邮箱: {email}")
    print(f"[信息] 密码: {password}")
    
    driver = None
    sio = None
    code_received = None
    
    try:
        # 启动浏览器
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1280,720")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        })
        wait = WebDriverWait(driver, TIMEOUT['element'])
        
        # 打开注册页面
        driver.get(TRAEE_REGISTER_URL)
        
        # 启动 Socket.io 监听
        def start_mail_listener():
            nonlocal code_received, sio
            try:
                sio = socketio.Client(reconnection=False)
                
                @sio.event
                def connect():
                    sio.emit('set shortid', shortid)
                    print(f"[邮箱] Socket.io 已连接")
                
                @sio.on('mail')
                def on_mail(mail):
                    nonlocal code_received
                    text = mail.get('text', '')
                    subject = mail.get('headers', {}).get('subject', '')
                    print(f"[邮箱] 收到邮件: {subject}")
                    code = extract_verification_code(text + ' ' + subject)
                    if code:
                        code_received = code
                        print(f"[邮箱] 获取到验证码: {code}")
                        sio.disconnect()
                
                sio.connect('https://tempmail.cn', transports=['websocket', 'polling'])
                
                # 等待验证码
                start_time = time.time()
                while code_received is None and time.time() - start_time < TIMEOUT['verification_code']:
                    time.sleep(0.5)
                
                if sio.connected:
                    sio.disconnect()
                    
            except Exception as e:
                print(f"[错误] Socket.io: {e}")
        
        mail_thread = threading.Thread(target=start_mail_listener, daemon=True)
        mail_thread.start()
        
        # 填写邮箱
        print("[自动] 填写邮箱...")
        email_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="email"]')))
        email_input.clear()
        email_input.send_keys(email)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", email_input)
        
        # 点击发送验证码
        print("[自动] 点击发送验证码...")
        try:
            send_btn = driver.find_element(By.CSS_SELECTOR, '.right-part.send-code')
            send_btn.click()
        except:
            driver.execute_script("document.querySelector('.right-part.send-code').click()")
        
        # 等待验证码
        print("[自动] 等待验证码...")
        start_time = time.time()
        while code_received is None and time.time() - start_time < TIMEOUT['verification_code']:
            time.sleep(0.5)
        
        if not code_received:
            print("[错误] 获取验证码超时")
            driver.quit()
            return None
        
        # 填写验证码
        print("[自动] 填写验证码...")
        code_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[placeholder*="Verification code"]')))
        code_input.clear()
        code_input.send_keys(code_received)
        
        # 填写密码
        print("[自动] 填写密码...")
        pass_input = driver.find_element(By.CSS_SELECTOR, 'input[type="password"]')
        pass_input.clear()
        pass_input.send_keys(password)
        
        # 点击注册
        print("[自动] 点击注册...")
        try:
            sign_up_btn = driver.find_element(By.CSS_SELECTOR, '.btn-submit')
            sign_up_btn.click()
        except:
            driver.execute_script("document.querySelector('.btn-submit').click()")
        
        # 等待登录完成
        time.sleep(3)
        
        # 尝试获取 Token
        token = None
        try:
            script = """
                let token = localStorage.getItem('token') || localStorage.getItem('user_token') ||
                           sessionStorage.getItem('token') || sessionStorage.getItem('user_token');
                if (!token) {
                    const match = document.cookie.match(/token=([^;]+)/);
                    if (match) token = match[1];
                }
                return token;
            """
            token = driver.execute_script(script)
        except:
            pass
        
        driver.quit()
        
        print(f"[成功] 注册完成!")
        return {
            'email': email,
            'password': password,
            'token': token
        }
        
    except Exception as e:
        print(f"[错误] 注册失败: {e}")
        if driver:
            driver.quit()
        return None


# ==================== 主程序 ====================

def main():
    print("""
╔══════════════════════════════════════════╗
║      Trae 批量注册 (单进程稳定版)        ║
╚══════════════════════════════════════════╝
""")
    
    parser = argparse.ArgumentParser(description='Trae 批量注册')
    parser.add_argument('--count', type=int, default=5, help='注册数量 (默认: 5)')
    parser.add_argument('--headless', action='store_true', help='无头模式')
    parser.add_argument('--interval', type=int, default=2, help='账号间隔秒数 (默认: 2)')
    args = parser.parse_args()
    
    count = args.count
    headless = args.headless
    interval = args.interval
    
    print(f"[配置] 注册数量: {count}")
    print(f"[配置] 无头模式: {headless}")
    print(f"[配置] 账号间隔: {interval}秒")
    
    results = []
    start_time = time.time()
    
    for i in range(1, count + 1):
        result = register_one_account(i, count, headless)
        if result:
            results.append(result)
            # 保存到文件
            with open("trae_accounts.txt", "a", encoding="utf-8") as f:
                f.write(f"邮箱: {result['email']}\n")
                f.write(f"密码: {result['password']}\n")
                f.write("-" * 40 + "\n")
        
        # 间隔一段时间再注册下一个
        if i < count:
            print(f"\n[等待] {interval} 秒后注册下一个...")
            time.sleep(interval)
    
    elapsed = time.time() - start_time
    
    # 打印总结
    print(f"\n{'='*50}")
    print(f"[完成] 成功注册 {len(results)}/{count} 个账号")
    print(f"[耗时] {elapsed:.1f} 秒")
    print(f"[平均] {elapsed/max(len(results),1):.1f} 秒/账号")
    print(f"[文件] 已保存到 trae_accounts.txt")
    print(f"{'='*50}")
    
    return 0 if results else 1


if __name__ == "__main__":
    exit(main())
