# # xydj/main.py
# #原逻辑，放回xydj/目录下即可
# from ncatbot.plugin import BasePlugin, CompatibleEnrollment
# from ncatbot.core.message import GroupMessage
# from ncatbot.core.element import *
# from selenium import webdriver
# from selenium.webdriver.common.by import By
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.support import expected_conditions as EC
# from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException
# from selenium.webdriver.chrome.options import Options
# from selenium.webdriver.chrome.service import Service
# from PIL import Image as PILImage, ImageDraw, ImageFont
# import asyncio
# import logging
# import re
# import requests
# import json
# import time
# import os
# from urllib.parse import urljoin

# bot = CompatibleEnrollment

# # ========================= 工具函数 =========================
# logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# def get_text_size(font, text):
#     lines = text.split('\n')
#     max_width = 0
#     total_height = 0
#     for line in lines:
#         bbox = font.getbbox(line)
#         width = bbox[2] - bbox[0]
#         height = bbox[3] - bbox[1]
#         max_width = max(max_width, width)
#         total_height += height
#     return max_width, total_height

# async def search_game(game_name):
#     logging.info(f"开始搜索游戏: {game_name}")
#     driver = None
#     try:
#         chrome_options = Options()
#         chrome_options.add_argument("--no-sandbox")
#         chrome_options.add_argument("--disable-dev-shm-usage")
#         chrome_options.add_argument("--disable-blink-features=AutomationControlled")
#         chrome_options.add_argument("--headless=new")
#         chrome_options.add_argument("--disable-gpu")
#         chrome_options.add_argument("window-size=1920,1080")
#         chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3")

#         service = Service(executable_path="/usr/local/bin/chromedriver")
#         driver = webdriver.Chrome(service=service, options=chrome_options)

#         url = f"https://www.xianyudanji.to/?cat=1&s= {game_name}&order=views"
#         driver.get(url)
#         logging.info(f"打开网页: {url}")

#         cookies = [
#             {"name": "ripro_notice_cookie", "value": "1"},
#             {"name": "PHPSESSID", "value": "bpef7mrr2tkkinp2brgv6dvfqn"},
#             {"name": "wordpress_logged_in_c1baf48ff9d49282e5cd4050fece6d34",
#              "value": "HHH9201%7C1760406683%7CUYlwXcW8pe5os2fjsOjEAsVmulT0VqwjPTDu3Hoh4xV%7C8442e486cb6994449a45c105aa8419962dda7ac8ad2e3506f113bef3cd2e2c77"}
#         ]
#         logging.info("添加并刷新 Cookie")
#         for cookie in cookies:
#             driver.add_cookie(cookie)
#         driver.refresh()
#         logging.info("刷新页面完成")

#         time.sleep(2)
#         driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
#         time.sleep(2)

#         WebDriverWait(driver, 10).until(
#             EC.presence_of_element_located(
#                 (By.XPATH, f"//*[contains(@title, '{game_name}') or contains(text(), '{game_name}') and @href]"))
#         )
#         logging.info("页面加载完成，开始查找元素...")
#     except TimeoutException:
#         logging.warning("页面加载超时，可能是网络问题或链接不合法。请检查网页链接的合法性，并适当重试。")
#         if driver:
#             driver.quit()
#         return None, None, None
#     except Exception as e:
#         logging.exception("完整 traceback：")
#         if driver:
#             driver.quit()
#         return None, None, None

#     elements = driver.find_elements(By.XPATH,
#                                     f"//*[contains(@title, '{game_name}') or contains(text(), '{game_name}') and @href]")

#     filtered_game_elements = []
#     seen_titles = set()
#     for element in elements:
#         title = element.get_attribute('title') or element.text.strip()
#         if title and title not in seen_titles:
#             filtered_game_elements.append(element)
#             seen_titles.add(title)

#     if not filtered_game_elements:
#         logging.info(f"未找到包含文本或title为 '{game_name}' 的链接元素。")
#         if driver:
#             driver.quit()
#         return None, None, None

#     logging.info(f"找到 {len(filtered_game_elements)} 个包含文本或title为 '{game_name}' 的链接元素：")
#     for idx, element in enumerate(filtered_game_elements, start=1):
#         title = element.get_attribute('title') or element.text.strip()
#         logging.info(f"{idx}. {title}")

#     text_lines = [f"{idx}. {element.get_attribute('title') or element.text.strip()}" for idx, element in
#                   enumerate(filtered_game_elements, start=1)]
#     text_content = "\n".join(text_lines)

#     font_path = "/home/h/BOT/NC/plugins/xydj/tool/msyhbd.ttc"
#     if not os.path.exists(font_path):
#         logging.warning(f"字体文件 {font_path} 不存在，将使用默认字体。")
#         font_path = None

#     font_size = 20
#     font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()

#     text_width, text_height = get_text_size(font, text_content)
#     image_width = text_width + 20
#     image_height = text_height + 20

#     image = PILImage.new("RGB", (image_width, image_height), color="white")
#     draw = ImageDraw.Draw(image)
#     draw.text((10, 10), text_content, font=font, fill="black")

#     image_path = "123.png"
#     image.save(image_path)
#     logging.info(f"图片已保存为 {image_path}")

#     return image_path, filtered_game_elements, driver

# async def process_game_choice(choice, filtered_game_elements, driver, group_id, api):
#     if 1 <= choice <= len(filtered_game_elements):
#         selected_element = filtered_game_elements[choice - 1]
#         try:
#             title = selected_element.get_attribute('title') or selected_element.text.strip()
#             img_element = selected_element.find_element(By.TAG_NAME, "img")
#             img_src = img_element.get_attribute("src")
#             img_path = "selected_game.png"
#             img_element.screenshot(img_path)

#             logging.info(f"用户点击的元素信息：")
#             logging.info(f"  标题: {title}")
#             logging.info(f"  图片链接: {img_src}")
#             logging.info(f"  图片已保存为: {img_path}")

#             messages = [
#                 (f"您选择的游戏是：{title}", None),
#                 ("您选择的游戏图片如下：", img_path),
#                 (f"游戏图片的src地址为：{img_src}", None)
#             ]

#             send_forward_message(group_id, messages, api)

#             selected_element.click()
#         except ElementClickInterceptedException:
#             driver.execute_script("arguments[0].click();", selected_element)
#         except Exception as e:
#             logging.error(f"处理用户选择时发生错误: {e}")
#             return ["处理用户选择时发生错误，请联系管理员。"]

#         current_window = driver.current_window_handle
#         WebDriverWait(driver, 10).until(lambda d: len(d.window_handles) > 1)
#         new_window = [window for window in driver.window_handles if window != current_window][0]
#         driver.switch_to.window(new_window)

#         try:
#             login_button = WebDriverWait(driver, 5).until(
#                 EC.element_to_be_clickable((By.XPATH, '//*[@id="app"]/header/div/div/div[3]/a'))
#             )
#             login_button.click()
#             time.sleep(2)
#             driver.find_element(By.XPATH, "//*[contains(@name,'username')]").send_keys("1783069903@qq.com")
#             driver.find_element(By.XPATH, "//*[contains(@name,'password')]").send_keys("heh031701")
#             driver.find_element(By.XPATH, "//button[text()='立即登录']").click()
#             logging.info("执行登录操作")
#         except TimeoutException:
#             logging.info("未找到登录按钮，跳过登录")
#         except Exception as e:
#             logging.error(f"登录过程中发生错误: {e}")

#         # ========================= 重写提取逻辑 =========================
#         def extract_download_info(driver, current_window, new_window) -> list[str]:
#             """
#             在新打开的游戏详情页里提取
#             返回: ['解压密码: xxx', '百度网盘: `https://...` ', '夸克网盘: `https://...` ', ...]
#             """
#             wait = WebDriverWait(driver, 15)
#             results = []

#             # 1. 解压密码（优先按钮，回退文本）
#             try:
#                 # 按钮方式
#                 pwd_btn = wait.until(
#                     EC.element_to_be_clickable(
#                         (By.XPATH, '//button[@data-clipboard-text and preceding-sibling::a[contains(text(),"解压密码")]]')
#                     )
#                 )
#                 pwd = pwd_btn.get_attribute("data-clipboard-text").strip()
#                 results.append(f"解压密码: {pwd}")
#             except Exception:
#                 try:
#                     # 文本方式
#                     pwd_txt = driver.find_element(
#                         By.XPATH, '//span[contains(text(),"解压密码")]/following-sibling::span[1]'
#                     ).text.strip()
#                     results.append(f"解压密码: {pwd_txt}")
#                 except Exception:
#                     results.append("解压密码: 未找到")

#             # 2. 四大网盘
#             pan_list = ["百度网盘", "夸克网盘", "不限速UC网盘", "123"]
#             for pan in pan_list:
#                 try:
#                     element = wait.until(
#                         EC.element_to_be_clickable((By.XPATH, f'//*[contains(text(), "{pan}")]'))
#                     )
#                     element.click()

#                     WebDriverWait(driver, 10).until(lambda d: len(d.window_handles) > 2)
#                     new_window_for_link = [window for window in driver.window_handles if window != current_window and window != new_window][0]
#                     driver.switch_to.window(new_window_for_link)

#                     download_link = driver.current_url
#                     results.append(f"{pan}: {download_link}")

#                     driver.close()
#                     driver.switch_to.window(new_window)
#                 except TimeoutException:
#                     logging.info(f"未找到 {pan} 元素，跳过")
#                     results.append(f"{pan}: 未找到")
#                 except Exception as e:
#                     logging.error(f"处理 {pan} 时发生错误: {e}")
#                     results.append(f"{pan}: 发生错误，无法获取下载链接")

#             return results

#         # 使用新的提取函数
#         extracted_info = extract_download_info(driver, current_window, new_window)

#         driver.quit()
#         return extracted_info
#     else:
#         return ["无效的序号，请重新选择。"]

# def send_forward_message(group_id, messages, api):
#     url = "http://192.168.196.88:3006/send_group_forward_msg "
#     headers = {
#         'Content-Type': 'application/json',
#         'Authorization': 'Bearer h031701'
#     }

#     payload_messages = []

#     fixed_message_node = {"type": "node", "data": {"content": [
#         {"type": "text", "data": {"text": "觉得好用的话可以赞助一下服务器的费用，5毛1快不嫌少，5元10元不嫌多"}},
#         {"type": "image", "data": {"file": "/home/h/BOT/NC/plugins/xydj/tool/QQ.png"}}
#     ]}}
#     payload_messages.append(fixed_message_node)

#     for text, image_url in messages:
#         node = {"type": "node", "data": {"content": []}}
#         if text:
#             node["data"]["content"].append({"type": "text", "data": {"text": text}})
#         if image_url:
#             node["data"]["content"].append({"type": "image", "data": {"file": image_url}})
#         payload_messages.append(node)

#     payload = json.dumps({
#         "group_id": group_id,
#         "messages": payload_messages
#     })

#     try:
#         response = requests.post(url, headers=headers, data=payload, timeout=10)
#         print("[Forward] status:", response.status_code)
#         print("[Forward] resp :", response.text)  
#         if response.status_code == 200:
#             logging.info("消息发送成功")
#         else:
#             logging.error(f"消息发送失败，状态码：{response.status_code}, 响应内容：{response.text}")
#     except Exception as e:
#         logging.error(f"发送消息时发生错误：{e}")
#         logging.error("请检查网络连接或服务地址是否正确。")

# # ========================= 主插件 =========================
# class MyPlugin(BasePlugin):
#     name = "MyPlugin"
#     version = "0.0.1"

#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.message_queue = asyncio.Queue()
#         self.waiting_for_reply = False
#         self.processing = False
#         self.target_message_id = None
#         self.user_who_sent_command = None
#         self.filtered_game_elements = []
#         self.driver = None
#         self.timer_task = None
#         self.extracted_info = []

#     async def countdown(self, msg, group_id):
#         """倒计时任务"""
#         await asyncio.sleep(40)
#         if self.waiting_for_reply:
#             self.waiting_for_reply = False
#             if self.driver:
#                 self.driver.quit()
#             await self.api.post_group_msg(
#                 group_id=group_id,
#                 rtf=MessageChain([Reply(msg.message_id), Text("等待超时，操作已取消。请重新搜索")])
#             )

#     @bot.group_event()
#     async def on_group_message(self, msg: GroupMessage):
#         await self.message_queue.put(msg)

#         if self.waiting_for_reply and msg.user_id == self.user_who_sent_command:
#             if self.processing:
#                 return

#             user_choice = re.sub(r'\[CQ:[^\]]+\]', '', msg.raw_message).strip()

#             if user_choice == "0":  # 用户选择退出
#                 await self.api.post_group_msg(
#                     group_id=msg.group_id,
#                     rtf=MessageChain([Reply(msg.message_id), Text("操作已取消。")])
#                 )
#                 self._cleanup()
#                 return

#             if not user_choice.isdigit():
#                 await self.api.post_group_msg(
#                     group_id=msg.group_id,
#                     rtf=MessageChain([Reply(msg.message_id), Text("回复错误，操作已取消。请重新搜索游戏。")])
#                 )
#                 self._cleanup()
#                 return

#             user_choice = int(user_choice)

#             if not 1 <= user_choice <= len(self.filtered_game_elements):
#                 await self.api.post_group_msg(
#                     group_id=msg.group_id,
#                     rtf=MessageChain([Reply(msg.message_id), Text("回复错误，操作已取消。请重新搜索游戏。")])
#                 )
#                 self._cleanup()
#                 return

#             await self.api.post_group_msg(
#                 group_id=msg.group_id,
#                 rtf=MessageChain([Reply(msg.message_id), Text(f"已选择第 {user_choice} 个游戏，请等待大概1分钟！！！")])
#             )

#             self.processing = True
#             self._cancel_timer()

#             try:
#                 self.extracted_info = await process_game_choice(user_choice, self.filtered_game_elements, self.driver, msg.group_id, self.api)
#                 if self.extracted_info:
#                     messages = [(info, None) for info in self.extracted_info]
#                     await self.send_forward_message(msg.group_id, messages)
#                 else:
#                     await self.api.post_group_msg(
#                         group_id=msg.group_id,
#                         rtf=MessageChain([Reply(msg.message_id), Text("未找到有效的下载链接。")])
#                     )
#             except Exception as e:
#                 logging.error(f"处理用户选择时发生错误: {e}")
#                 await self.api.post_group_msg(
#                     group_id=msg.group_id,
#                     rtf=MessageChain([Reply(msg.message_id), Text("哎我擦，报错咯，快找管理员！")])
#                 )
#             finally:
#                 self._cleanup()

#         elif msg.raw_message.strip().startswith("单机"):
#             game_name = msg.raw_message.strip()[2:]
#             if not game_name:
#                 await self.api.post_group_msg(
#                     group_id=msg.group_id,
#                     rtf=MessageChain([Reply(msg.message_id), Text("请输入游戏名字，例如：搜索文明")])
#                 )
#                 return

#             try:
#                 image_path, filtered_game_elements, driver = await search_game(game_name)
#                 if image_path is None:
#                     message1 = MessageChain([
#                         Reply(msg.message_id),
#                         Text("未找到，检查游戏名字，搜索游戏字数少一点试试呢"),
#                     ])
#                     await self.api.post_group_msg(group_id=msg.group_id, rtf=message1)
#                     if driver:
#                         driver.quit()
#                     return

#                 message = MessageChain([
#                     Reply(msg.message_id),
#                     Text("请根据序号选择游戏（30秒内未选择将自动退出）：\n"),
#                     Image(image_path)
#                 ])
#                 response = await self.api.post_group_msg(group_id=msg.group_id, rtf=message)

#                 self.waiting_for_reply = True
#                 self.target_message_id = response['data']['message_id']
#                 self.user_who_sent_command = msg.user_id
#                 self.filtered_game_elements = filtered_game_elements
#                 self.driver = driver
#                 self.timer_task = asyncio.create_task(self.countdown(msg, msg.group_id))
#             except TimeoutException:
#                 await self.api.post_group_msg(
#                     group_id=msg.group_id,
#                     rtf=MessageChain([Reply(msg.message_id), Text("操作超时，请稍后重试。")])
#                 )
#             except Exception as e:
#                 logging.exception("完整 traceback：")
#                 await self.api.post_group_msg(
#                     group_id=msg.group_id,
#                     rtf=MessageChain([Reply(msg.message_id), Text("发生错误，请稍后重试。")])
#                 )
#                 if self.driver:
#                     self.driver.quit()

#     async def send_forward_message(self, group_id, messages):
#         url = "http://192.168.196.88:3006/send_group_forward_msg"
#         headers = {
#             'Content-Type': 'application/json',
#             'Authorization': 'Bearer h031701'
#         }

#         payload_messages = []

#         fixed_message_node = {"type": "node", "data": {"content": [
#             {"type": "text", "data": {"text": "觉得好用的话可以赞助一下服务器的费用，5毛1快不嫌少，5元10元不嫌多"}},
#             {"type": "image", "data": {"file": "/home/h/BOT/NC/plugins/xydj/tool/QQ.png"}}
#         ]}}
#         payload_messages.append(fixed_message_node)

#         # fixed_message_node = {"type": "node", "data": {"content": [
#         #     {"type": "text", "data": {"text": "GPT的免费KEY，免费使用deepseek无卡顿，不等待,快速响应，新用户通过手机号码注册，将获得 2000 万 Tokens,请填写一下我的邀请码，非常感谢:xGXf0Gls，\nhttps://cloud.siliconflow.cn/i/xGXf0Gls"}},
#         #     {"type": "image", "data": {"file": "/home/h/BOT/NC/plugins/xydj/tool/GPT.png"}}
#         # ]}}
#         # payload_messages.append(fixed_message_node)        

#         for text, image_url in messages:
#             node = {"type": "node", "data": {"content": []}}
#             if text:
#                 node["data"]["content"].append({"type": "text", "data": {"text": text}})
#             if image_url:
#                 node["data"]["content"].append({"type": "image", "data": {"file": image_url}})
#             payload_messages.append(node)

#         fixed_message_node = {"type": "node", "data": {"content": [
#             {"type": "image", "data": {"file": "/home/h/BOT/NC/selected_game.png"}}
#         ]}}
#         payload_messages.append(fixed_message_node)

#         payload = json.dumps({
#             "group_id": group_id,
#             "messages": payload_messages
#         })

#         try:
#             response = requests.post(url, headers=headers, data=payload, timeout=10)
#             print("[Forward] status:", response.status_code)
#             print("[Forward] resp :", response.text)  
#             if response.status_code == 200:
#                 logging.info("消息发送成功")
#             else:
#                 logging.error(f"消息发送失败，状态码：{response.status_code}, 响应内容：{response.text}")
#         except Exception as e:
#             logging.error(f"发送消息时发生错误：{e}")
#             logging.error("请检查网络连接或服务地址是否正确。")

#     def _cleanup(self):
#         """清理资源"""
#         if self.driver:
#             self.driver.quit()
#         self.waiting_for_reply = False
#         self.processing = False
#         self._cancel_timer()

#     def _cancel_timer(self):
#         """取消倒计时任务"""
#         if self.timer_task:
#             self.timer_task.cancel()
#             try:
#                 self.timer_task = None
#             except asyncio.CancelledError:
#                 pass

#     async def on_load(self):
#         print(f"{self.name} 插件已加载，版本: {self.version}")
