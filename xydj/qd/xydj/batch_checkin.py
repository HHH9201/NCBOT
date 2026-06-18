#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
咸鱼单机网站 - 批量签到脚本
功能：使用 all_cookies.json 中的所有 Cookie 进行批量签到
"""

from curl_cffi import requests as curl_requests
from py_mini_racer import MiniRacer
import re
import json
import time
from datetime import datetime
from pathlib import Path

# 访问配置：目标网站 www.xianyudanji.app 的 SNI 在国内被拦截，
# 改用其 CDN 域名 mq8tuxdn.luvipcdn.cn 作为访问入口（绕过 SNI 拦截），
# 通过 Host 头告诉服务器真实域名，证书为自签名故关闭验证。
BASE_URL = "https://mq8tuxdn.luvipcdn.cn"
REAL_DOMAIN = "https://www.xianyudanji.app"


GUARD_MOCK = '''
var document = {
    cookie: 'guard=%s',
    referrer: 'https://www.xianyudanji.app/',
    location: { href: 'https://www.xianyudanji.app/' },
    addEventListener: function(){},
    removeEventListener: function(){},
    createElement: function(){ return {style:{}} },
    getElementsByTagName: function(){ return [] },
    getElementById: function(){ return null },
    querySelector: function(){ return null },
    body: { appendChild: function(){} }
};
var window = {
    location: { href: 'https://www.xianyudanji.app/', reload: function(){} },
    navigator: { userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', webdriver: false },
    addEventListener: function(){},
    removeEventListener: function(){},
    setTimeout: function(fn,delay){ return 1; },
    setInterval: function(fn,delay){ return 1; },
    clearTimeout: function(){},
    clearInterval: function(){},
    Date: Date,
    performance: { now: function(){ return 0; } },
    innerWidth: 1920, innerHeight: 1080,
    outerWidth: 1920, outerHeight: 1080,
    screen: { width: 1920, height: 1080 },
    chrome: { runtime: {} },
    console: { log: function(){}, warn: function(){}, error: function(){} },
    atob: function(s){ return s; },
    btoa: function(s){ return s; },
    crypto: { getRandomValues: function(arr){ for(var i=0;i<arr.length;i++) arr[i]=Math.floor(Math.random()*256); return arr; } }
};
var navigator = window.navigator;
var location = document.location;
var process = undefined;
var global = window;
var self = window;
var setTimeout = window.setTimeout;
var setInterval = window.setInterval;
var clearTimeout = window.clearTimeout;
var clearInterval = window.clearInterval;
var addEventListener = window.addEventListener;
'''


def bypass_guard(base_url):
    """过 WAF guard 防护，返回验证后的 cookie 字符串（含 _ok1_），带重试"""
    for attempt in range(5):
        if attempt > 0:
            time.sleep(5)
        try:
            session = curl_requests.Session(impersonate="chrome", verify=False)
            session.headers['Host'] = 'www.xianyudanji.app'

            r = session.get(base_url, timeout=30)
            guard_val = session.cookies.get('guard', '')
            if not guard_val:
                continue

            js_resp = session.get(f"{base_url}/_guard/auto.js", timeout=30)
            if js_resp.status_code != 200:
                continue

            ctx = MiniRacer()
            mock_code = GUARD_MOCK % guard_val
            ctx.eval(mock_code + js_resp.text)
            cookie_result = ctx.eval('document.cookie')
            if 'guardret=' not in cookie_result:
                continue
            guardret = cookie_result.split('guardret=')[1].split(';')[0].strip()

            session.cookies.clear()
            session.headers['Cookie'] = f'guard={guard_val}; guardret={guardret}'
            r2 = session.get(f"{base_url}/", timeout=30)
            if '/_guard/' in r2.text:
                continue

            # 直接用 session.cookies 获取 _ok1_，比解析 headers 更可靠
            ok1 = session.cookies.get('_ok1_', '')
            return f'_ok1_={ok1}' if ok1 else ''
        except Exception:
            continue
    return ''


def get_points(session, base_url):
    """获取积分"""
    try:
        response = session.get(f"{base_url}/user/aff", timeout=15)
        if response.status_code == 200:
            match = re.search(r'当前余额[：:]\s*(\d+(?:\.\d+)?)', response.text)
            if match:
                return match.group(1)
            match = re.search(r'<p[^>]*class="small m-0"[^>]*>当前余额[：:]\s*(\d+(?:\.\d+)?)</p>', response.text)
            if match:
                return match.group(1)
        return None
    except:
        return None


def checkin_account(username, cookie_str):
    """单个账号签到"""
    base_url = BASE_URL
    ajax_url = f"{base_url}/wp-admin/admin-ajax.php"

    session = curl_requests.Session(impersonate="chrome", verify=False)
    session.headers.update({
        'Host': 'www.xianyudanji.app',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'X-Requested-With': 'XMLHttpRequest',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Origin': REAL_DOMAIN,
        'Referer': f"{REAL_DOMAIN}/user/aff",
    })
    
    # 过 guard 防护，获取验证 cookie
    ok1_cookies = bypass_guard(base_url)
    if not ok1_cookies:
        print("    [!] guard 防护绕过失败，尝试继续...")

    # 合并用户 cookie 和验证 cookie
    user_cookie = cookie_str.strip().rstrip(';')
    if ok1_cookies:
        session.headers['Cookie'] = f'{user_cookie}; {ok1_cookies}'
    else:
        session.headers['Cookie'] = user_cookie

    # 获取 nonce
    nonce = ""
    try:
        response = session.get(f"{base_url}/user/aff", timeout=15)
        if response.status_code == 200:
            nonce_patterns = [
                r'nonce["\s:=]+["\']([a-f0-9]+)["\']',
                r'_wpnonce["\s:=]+["\']([a-f0-9]+)["\']',
                r'"nonce":"([a-f0-9]+)"',
                r'var\s+\w*[Nn]once\s*=\s*["\']([a-f0-9]+)["\']',
            ]

            for pattern in nonce_patterns:
                match = re.search(pattern, response.text)
                if match:
                    nonce = match.group(1)
                    break
    except Exception as e:
        print(f"    [!] 获取 nonce 失败: {e}")
    
    # 签到
    data = {
        'action': 'user_qiandao',
        'nonce': nonce
    }
    
    try:
        response = session.post(ajax_url, data=data, timeout=15)
        print(f"    [调试] 响应状态: {response.status_code}, 内容长度: {len(response.text)}")
        if response.status_code == 200:
            # 检查是否返回了 HTML（可能是被拦截了）
            if response.text.strip().startswith('<') or not response.text.strip():
                return False, f"返回非JSON内容: {response.text[:200]}"
            try:
                result = response.json()
                if result.get('status') == '1' or result.get('success') or '成功' in str(result):
                    return True, result.get('msg', '签到成功')
                elif '已签到' in str(result) or 'already' in str(result).lower():
                    return True, '今日已签到'
                else:
                    return False, result.get('msg', '签到失败')
            except json.JSONDecodeError as e:
                return False, f"JSON解析失败: {e}, 响应内容: {response.text[:200]}"
        else:
            return False, f'请求失败: {response.status_code}'
    except Exception as e:
        return False, str(e)


def batch_checkin():
    """批量签到"""
    # 加载 Cookie
    try:
        with open('all_cookies.json', 'r', encoding='utf-8') as f:
            all_cookies = json.load(f)
    except FileNotFoundError:
        print("未找到 all_cookies.json，请先运行 cookie_manager.py login")
        return
    
    if not all_cookies:
        print("暂无 Cookie，请先登录")
        return
    
    print("=" * 70)
    print("咸鱼单机网站 - 批量签到")
    print("=" * 70)
    print(f"时间: {datetime.now()}")
    print(f"账号数量: {len(all_cookies)}")
    print("=" * 70)
    
    success_count = 0
    fail_count = 0
    results = []
    
    for username, data in all_cookies.items():
        cookie_str = data.get('cookie', '')
        
        if not cookie_str:
            print(f"\n[{datetime.now()}] {username}: 无 Cookie，跳过")
            fail_count += 1
            continue
        
        print(f"\n[{datetime.now()}] 正在签到: {username}")
        
        # 签到
        success, msg = checkin_account(username, cookie_str)
        time.sleep(2)  # 避免频率限制
        
        if success:
            print(f"[{datetime.now()}] ✅ {username}: {msg}")
            success_count += 1
            
            # 获取积分
            base_url = BASE_URL
            session = curl_requests.Session(impersonate="chrome", verify=False)
            session.headers.update({
                'Host': 'www.xianyudanji.app',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN',
            })
            
            ok1_cookies = bypass_guard(base_url)
            user_cookie = cookie_str.strip().rstrip(';')
            if ok1_cookies:
                session.headers['Cookie'] = f'{user_cookie}; {ok1_cookies}'
            else:
                session.headers['Cookie'] = user_cookie
            points = get_points(session, base_url)
            if points:
                print(f"[{datetime.now()}]    积分: {points}")
            else:
                print(f"[{datetime.now()}]    积分: 未知")
            
            results.append({
                'username': username,
                'status': 'success',
                'msg': msg,
                'points': points
            })
        else:
            print(f"[{datetime.now()}] ❌ {username}: {msg}")
            fail_count += 1
            results.append({
                'username': username,
                'status': 'fail',
                'msg': msg,
                'points': None
            })
    
    # 总结
    print("\n" + "=" * 70)
    print("批量签到完成:")
    print(f"  成功: {success_count}")
    print(f"  失败: {fail_count}")
    print(f"  总计: {len(all_cookies)}")
    print("=" * 70)
    
    # 打印积分汇总
    print("\n积分汇总:")
    print("-" * 70)
    print(f"{'账号':<30} {'状态':<10} {'积分':<10}")
    print("-" * 70)
    for r in results:
        status = '✅' if r['status'] == 'success' else '❌'
        points = r['points'] if r['points'] else '未知'
        print(f"{r['username']:<30} {status:<10} {points:<10}")
    print("-" * 70)

    # 写入通知文件，供 NCBOT 发送
    try:
        notify_path = Path(__file__).resolve().parent / "checkin_notify.json"
        lines = ["📋 咸鱼单机每日签到结果", ""]
        for r in results:
            if r['status'] == 'success':
                points = r['points'] if r['points'] else '未知'
                lines.append(f"✅ {r['username']} 签到完成，当前余额：{points}")
            else:
                lines.append(f"❌ {r['username']} 签到失败：{r['msg']}")
        lines.append("")
        lines.append(f"总计: {len(results)} | 成功: {success_count} | 失败: {fail_count}")

        notify_data = {
            "message": "\n".join(lines),
            "group_id": 695934967
        }
        with open(notify_path, 'w', encoding='utf-8') as f:
            json.dump(notify_data, f, ensure_ascii=False)
        print(f"\n[通知] 结果已写入 {notify_path}")
    except Exception as e:
        print(f"\n[通知] 写入通知文件失败: {e}")


if __name__ == "__main__":
    batch_checkin()
