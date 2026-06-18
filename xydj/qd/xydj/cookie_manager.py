#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
咸鱼单机网站 - Cookie 管理器
功能：管理多个账号的 Cookie，存储在一个 JSON 文件中
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright


COOKIE_FILE = "all_cookies.json"


def load_cookies():
    """加载所有 Cookie"""
    if Path(COOKIE_FILE).exists():
        with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_cookies(cookies_data):
    """保存所有 Cookie"""
    with open(COOKIE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cookies_data, f, indent=2, ensure_ascii=False)
    print(f"[{datetime.now()}] Cookie 已保存到: {COOKIE_FILE}")


async def login_and_save(username, password):
    """登录并保存 Cookie"""
    base_url = "https://www.xianyudanji.app"
    
    print(f"\n[{datetime.now()}] 正在登录: {username}")
    
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        headless=True,
        args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
    )
    
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        viewport={'width': 1280, 'height': 800},
        locale='zh-CN',
        timezone_id='Asia/Shanghai'
    )
    
    page = await context.new_page()
    page.set_default_timeout(60000)
    
    try:
        # 访问签到页面
        await page.goto(f"{base_url}/user/aff", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)
        
        # 关闭弹窗
        try:
            swal_btn = await page.query_selector(".swal2-confirm")
            if swal_btn and await swal_btn.is_visible():
                await swal_btn.click()
                await asyncio.sleep(1)
        except:
            pass
        
        # 填写登录信息
        await asyncio.sleep(2)
        
        username_input = await page.query_selector("input[name='username']")
        if username_input:
            await username_input.fill(username)
        
        password_input = await page.query_selector("input[name='password']")
        if password_input:
            await password_input.fill(password)
        
        # 点击登录按钮
        login_btn = await page.query_selector("button.go-login")
        if login_btn:
            await login_btn.click()
        
        # 等待登录完成
        await asyncio.sleep(5)
        await page.wait_for_load_state("networkidle", timeout=30000)
        
        # 提取 Cookie
        cookies = await context.cookies()
        
        cookie_parts = []
        for cookie in cookies:
            cookie_parts.append(f"{cookie['name']}={cookie['value']}")
        
        cookie_str = '; '.join(cookie_parts)
        
        if cookie_str:
            print(f"[{datetime.now()}] 登录成功! Cookie 数量: {len(cookies)}")
            return cookie_str
        else:
            print(f"[{datetime.now()}] Cookie 获取失败")
            return None
            
    except Exception as e:
        print(f"[{datetime.now()}] 登录失败: {e}")
        return None
    finally:
        await browser.close()
        await playwright.stop()


async def batch_login(accounts_file="success_accounts.txt"):
    """批量登录并保存 Cookie"""
    print("=" * 60)
    print("咸鱼单机网站 - 批量登录 Cookie 管理器")
    print("=" * 60)
    print(f"时间: {datetime.now()}")
    print("=" * 60)
    
    # 读取账号
    try:
        with open(accounts_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"未找到账号文件: {accounts_file}")
        return
    
    # 加载已有 Cookie
    all_cookies = load_cookies()
    
    success_count = 0
    fail_count = 0
    
    for line in lines:
        line = line.strip()
        if not line or '---' not in line:
            continue
        
        username, password = line.split('---', 1)
        
        # 检查是否已有 Cookie
        if username in all_cookies:
            print(f"\n[{datetime.now()}] 跳过 {username} (已有 Cookie)")
            continue
        
        # 登录
        cookie_str = await login_and_save(username, password)
        
        if cookie_str:
            all_cookies[username] = {
                'cookie': cookie_str,
                'login_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'password': password
            }
            success_count += 1
        else:
            fail_count += 1
        
        # 每次登录后保存
        save_cookies(all_cookies)
    
    # 总结
    print("\n" + "=" * 60)
    print("批量登录完成:")
    print(f"  成功: {success_count}")
    print(f"  失败: {fail_count}")
    print(f"  总计: {len(all_cookies)} 个账号")
    print("=" * 60)


def list_cookies():
    """列出所有 Cookie"""
    all_cookies = load_cookies()
    
    if not all_cookies:
        print("暂无 Cookie")
        return
    
    print("=" * 60)
    print("已保存的 Cookie:")
    print("=" * 60)
    
    for username, data in all_cookies.items():
        print(f"\n账号: {username}")
        print(f"  登录时间: {data.get('login_time', '未知')}")
        print(f"  Cookie 长度: {len(data.get('cookie', ''))}")
    
    print("\n" + "=" * 60)
    print(f"总计: {len(all_cookies)} 个账号")
    print("=" * 60)


def get_cookie(username):
    """获取指定账号的 Cookie"""
    all_cookies = load_cookies()
    
    if username in all_cookies:
        return all_cookies[username]['cookie']
    
    return None


def delete_cookie(username):
    """删除指定账号的 Cookie"""
    all_cookies = load_cookies()
    
    if username in all_cookies:
        del all_cookies[username]
        save_cookies(all_cookies)
        print(f"[{datetime.now()}] 已删除 {username} 的 Cookie")
    else:
        print(f"[{datetime.now()}] 未找到 {username} 的 Cookie")


def export_cookies():
    """导出所有 Cookie 为文本格式"""
    all_cookies = load_cookies()
    
    if not all_cookies:
        print("暂无 Cookie")
        return
    
    print("=" * 60)
    print("导出 Cookie:")
    print("=" * 60)
    
    for username, data in all_cookies.items():
        print(f"\n# {username}")
        print(data.get('cookie', ''))
    
    print("\n" + "=" * 60)


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python cookie_manager.py login <账号文件>     # 批量登录")
        print("  python cookie_manager.py list                 # 列出所有 Cookie")
        print("  python cookie_manager.py get <用户名>         # 获取指定账号的 Cookie")
        print("  python cookie_manager.py delete <用户名>      # 删除指定账号的 Cookie")
        print("  python cookie_manager.py export               # 导出所有 Cookie")
        return
    
    command = sys.argv[1]
    
    if command == "login":
        accounts_file = sys.argv[2] if len(sys.argv) > 2 else "success_accounts.txt"
        asyncio.run(batch_login(accounts_file))
    elif command == "list":
        list_cookies()
    elif command == "get":
        if len(sys.argv) < 3:
            print("请指定用户名")
            return
        cookie = get_cookie(sys.argv[2])
        if cookie:
            print(f"Cookie: {cookie}")
        else:
            print("未找到该账号的 Cookie")
    elif command == "delete":
        if len(sys.argv) < 3:
            print("请指定用户名")
            return
        delete_cookie(sys.argv[2])
    elif command == "export":
        export_cookies()
    else:
        print(f"未知命令: {command}")


if __name__ == "__main__":
    main()
