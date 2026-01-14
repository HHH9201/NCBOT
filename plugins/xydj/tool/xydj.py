# xydj/tool/xydj.py
import logging
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from PIL import Image, ImageDraw, ImageFont
import re
import os
import asyncio
import requests
import json

# 使用更清爽的日志格式，去掉进程和线程信息
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

def get_text_size(font, text):
    lines = text.split('\n')
    max_width = 0
    total_height = 0
    for line in lines:
        bbox = font.getbbox(line)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        max_width = max(max_width, width)
        total_height += height
    return max_width, total_height

async def search_game(game_name, cookies_list=None):
    logging.info(f"开始搜索游戏: {game_name}")
    driver = None
    try:
        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("window-size=1920,1080")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3")

        service = Service(executable_path="/usr/local/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=chrome_options)

        url = f"https://www.xianyudanji.ai/?cat=1&s={game_name}&order=views"
        driver.get(url)
        logging.info(f"打开网页: {url}")

        if cookies_list:
            logging.info("添加并刷新 Cookie")
            for cookie in cookies_list:
                driver.add_cookie(cookie)
            driver.refresh()
            logging.info("刷新页面完成")

        time.sleep(2)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, f"//*[contains(@title, '{game_name}') or contains(text(), '{game_name}') and @href]"))
        )
        logging.info("页面加载完成，开始查找元素...")
    except TimeoutException:
        logging.warning("页面加载超时，可能是网络问题或链接不合法。请检查网页链接的合法性，并适当重试。")
        if driver:
            driver.quit()
        return None, None, None
    except Exception as e:
        logging.error(f"发生错误: {e}")
        if driver:
            driver.quit()
        return None, None, None

    elements = driver.find_elements(By.XPATH,
                                    f"//*[contains(@title, '{game_name}') or contains(text(), '{game_name}') and @href]")

    filtered_game_elements = []
    seen_titles = set()
    for element in elements:
        title = element.get_attribute('title') or element.text.strip()
        if title and title not in seen_titles:
            filtered_game_elements.append(element)
            seen_titles.add(title)

    if not filtered_game_elements:
        logging.info(f"未找到包含文本或title为 '{game_name}' 的链接元素。")
        if driver:
            driver.quit()
        return None, None, None

    logging.info(f"找到 {len(filtered_game_elements)} 个包含文本或title为 '{game_name}' 的链接元素：")
    for idx, element in enumerate(filtered_game_elements, start=1):
        title = element.get_attribute('title') or element.text.strip()
        logging.info(f"{idx}. {title}")

    text_lines = [f"{idx}. {element.get_attribute('title') or element.text.strip()}" for idx, element in
                  enumerate(filtered_game_elements, start=1)]
    text_content = "\n".join(text_lines)

    font_path = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
    if not os.path.exists(font_path):
        logging.warning(f"字体文件 {font_path} 不存在，将使用默认字体。")
        font_path = None

    font_size = 20
    font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()

    text_width, text_height = get_text_size(font, text_content)
    image_width = text_width + 20
    image_height = text_height + 20

    image = Image.new("RGB", (image_width, image_height), color="white")
    draw = ImageDraw.Draw(image)
    draw.text((10, 10), text_content, font=font, fill="black")

    # 将图片转换为base64编码，避免保存到本地文件
    import io
    img_buffer = io.BytesIO()
    image.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    img_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
    image_path = f"data:image/png;base64,{img_base64}"
    logging.info(f"图片已转换为base64编码")

    return image_path, filtered_game_elements, driver

async def process_game_choice(choice, filtered_game_elements, driver, group_id, api):
    if 1 <= choice <= len(filtered_game_elements):
        selected_element = filtered_game_elements[choice - 1]
        try:
            title = selected_element.get_attribute('title') or selected_element.text.strip()
            img_element = selected_element.find_element(By.TAG_NAME, "img")
            img_src = img_element.get_attribute("src")
            
            # 将截图转换为base64编码，避免保存到本地文件
            screenshot_png = img_element.screenshot_as_png
            img_base64 = base64.b64encode(screenshot_png).decode('utf-8')
            img_path = f"data:image/png;base64,{img_base64}"

            logging.info(f"用户点击的元素信息：")
            logging.info(f"  标题: {title}")
            logging.info(f"  图片链接: {img_src}")
            logging.info(f"  图片已转换为base64编码")

            messages = [
                (f"您选择的游戏是：{title}", None),
                ("您选择的游戏图片如下：", img_path),
                (f"游戏图片的src地址为：{img_src}", None)
            ]

            send_forward_message(group_id, messages, api)

            selected_element.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", selected_element)
        except Exception as e:
            logging.error(f"处理用户选择时发生错误: {e}")
            return ["处理用户选择时发生错误，请联系管理员。"]

        current_window = driver.current_window_handle
        WebDriverWait(driver, 10).until(lambda d: len(d.window_handles) > 1)
        new_window = [window for window in driver.window_handles if window != current_window][0]
        driver.switch_to.window(new_window)

        try:
            login_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, '//*[@id="app"]/header/div/div/div[3]/a'))
            )
            login_button.click()
            time.sleep(2)
            driver.find_element(By.XPATH, "//*[contains(@name,'username')]").send_keys("1783069903@qq.com")
            driver.find_element(By.XPATH, "//*[contains(@name,'password')]").send_keys("hehe031701")
            driver.find_element(By.XPATH, "//button[text()='立即登录']").click()
            logging.info("执行登录操作")
        except TimeoutException:
            logging.info("未找到登录按钮，跳过登录")
        except Exception as e:
            logging.error(f"登录过程中发生错误: {e}")

        extracted_info = []

        try:
            password_button = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (By.XPATH, '//*[@id="ripro_v2_shop_down-4"]//*[contains(text(),"解压密码")]/following-sibling::button'))
            )
            password = password_button.get_attribute("data-clipboard-text").strip()
            extracted_info.append(f"解压密码: {password}")
            logging.info("成功获取解压密码（按钮方式）")
        except TimeoutException:
            logging.warning("未找到解压密码按钮，尝试查找其他方式")
            try:
                password_span = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located(
                        (By.XPATH, '//*[@id="ripro_v2_shop_down-4"]//*[contains(text(),"解压密码")]/following-sibling::p'))
                )
                password = password_span.text.strip()
                extracted_info.append(f"解压密码: {password}")
                logging.info("成功获取解压密码（文本方式）")
            except TimeoutException:
                logging.warning("未找到解压密码的文本")
            except Exception as e:
                logging.error(f"获取解压密码时发生错误（文本方式）: {e}")
        except Exception as e:
            logging.error(f"获取解压密码时发生错误（按钮方式）: {e}")

        target_elements = ["百度网盘", "夸克网盘", "不限速UC网盘", "123"]
        for div_index in target_elements:
            try:
                element = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, f'//*[@id="ripro_v2_shop_down-4"]//*[contains(text(), "{div_index}")]'))
                )
                element.click()

                WebDriverWait(driver, 10).until(lambda d: len(d.window_handles) > 2)
                new_window_for_link = [window for window in driver.window_handles if window != current_window and window != new_window][0]
                driver.switch_to.window(new_window_for_link)

                download_link = driver.current_url
                extracted_info.append(f"{div_index}：{download_link}")

                driver.close()
                driver.switch_to.window(new_window)
            except TimeoutException:
                logging.info(f"未找到 {div_index} 元素，跳过")
            except Exception as e:
                logging.error(f"处理 {div_index} 时发生错误: {e}")
                extracted_info.append(f"{div_index} 发生错误，无法获取下载链接")

        driver.quit()
        return extracted_info
    else:
        return ["无效的序号，请重新选择。"]

def send_forward_message(group_id, messages, api):
    url = "http://101.35.164.122:3006/send_group_forward_msg"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer he031701'
    }

    payload_messages = []

    
        # 添加固定消息和图片到一个新的节点
    fixed_message_node = {"type": "node", "data": {"content": [
        {"type": "text", "data": {"text": "觉得好用的话可以赞助一下服务器的费用，5毛1快不嫌少，5元10元不嫌多"}},
        {"type": "image", "data": {"file": "/home/h/BOT/NC/plugins/xydj/tool/QQ.png"}}  # 替换图片URL
    ]}}
    payload_messages.append(fixed_message_node)
    for text, image_url in messages:
        node = {"type": "node", "data": {"content": []}}
        if text:
            node["data"]["content"].append({"type": "text", "data": {"text": text}})
        if image_url:
            node["data"]["content"].append({"type": "image", "data": {"file": image_url}})
        payload_messages.append(node)



    payload = json.dumps({
        "group_id": group_id,
        "messages": payload_messages
    })

    try:
        response = requests.post(url, headers=headers, data=payload)
        if response.status_code == 200:
            logging.info("消息发送成功")
        else:
            logging.error(f"消息发送失败，状态码：{response.status_code}, 响应内容：{response.text}")
    except Exception as e:
        logging.error(f"发送消息时发生错误：{e}")
        logging.error("请检查网络连接或服务地址是否正确。")