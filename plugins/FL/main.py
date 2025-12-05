import httpx
import logging
import yaml
from ncatbot.plugin import BasePlugin, CompatibleEnrollment
from ncatbot.core import GroupMessage

bot = CompatibleEnrollment
logging.basicConfig(level=logging.INFO)

class FL(BasePlugin):
    name = "FL"
    version = "1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.load_config()

    def load_config(self):
        """加载配置文件"""
        try:
            with open("/home/hjh/BOT/NCBOT/config.yaml", "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            # 使用固定的token，与xydj插件保持一致
            self.api_token = "he031701"
            logging.info(f"已加载API令牌: {self.api_token}")
        except Exception as e:
            logging.error(f"加载配置文件失败: {e}")
            self.api_token = "he031701"  # 默认值

    # ---------- 关键词映射 ----------
    IMAGE_API = {
        "黑丝": "https://v2.api-m.com/api/heisi?type=2&return=302",
        "白丝": "https://v2.api-m.com/api/baisi?type=2&return=302",
        "买家秀": "https://api.yuafeng.cn/API/ly/mjx.php",
        "原神":"https://v2.xxapi.cn/api/ys?return=302",
        "cos":"https://v2.xxapi.cn/api/yscos?return=302",
        "美腿":"https://api.yuafeng.cn/API/ly/tui.php ",
        "xjj":"https://v2.xxapi.cn/api/meinvpic?type=2&return=302",
        "jk":"https://v2.xxapi.cn/api/jk?type=2&return=302",
    }

    VIDEO_API = {
        "蛇姐视频":"https://api.yuafeng.cn/API/ly/sjxl.php",
        "xjj视频":"https://api.yuafeng.cn/API/ly/sp.php",
        "玉足视频":"https://api.yuafeng.cn/API/ly/yzxl.php",
        "jk视频":"http://api.mmp.cc/api/ksvideo?type=mp4&id=jk",
        "欲梦视频":"http://api.mmp.cc/api/ksvideo?type=mp4&id=YuMeng",
        "女大视频":"http://api.mmp.cc/api/ksvideo?type=mp4&id=NvDa",
        "女高视频":"http://api.mmp.cc/api/ksvideo?type=mp4&id=NvGao",
        "热舞视频":"http://api.mmp.cc/api/ksvideo?type=mp4&id=ReWu",
        "清纯视频":"http://api.mmp.cc/api/ksvideo?type=mp4&id=QingCun",
        "玉足视频":"http://api.mmp.cc/api/ksvideo?type=mp4&id=YuZu",
        "蛇姐视频":"http://api.mmp.cc/api/ksvideo?type=mp4&id=SheJie",
        "穿搭视频":"http://api.mmp.cc/api/ksvideo?type=mp4&id=ChuanDa",
        "小姐姐视频":"http://api.mmp.cc/api/ksvideo?type=mp4&id=GaoZhiLiangXiaoJieJie",
        "汉服视频":"http://api.mmp.cc/api/ksvideo?type=mp4&id=HanFu",
        "黑手视频":"http://api.mmp.cc/api/ksvideo?type=mp4&id=HeiSi",
        "变装视频":"http://api.mmp.cc/api/ksvideo?type=mp4&id=BianZhuang",
        "萝莉视频":"http://api.mmp.cc/api/ksvideo?type=mp4&id=LuoLi",
        "甜妹视频":"http://api.mmp.cc/api/ksvideo?type=mp4&id=TianMei",
        "白丝视频":"http://api.mmp.cc/api/ksvideo?type=mp4&id=BaiSi",
    }

    # ---------- 通用发送 ----------
    async def send_forward(self, group_id: int, url: str,
                           media_type: str, title: str = "合集"):
        api = "http://101.35.164.122:3006/send_group_forward_msg"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_token}"
        }

        # 构建API关键词信息文本
        api_info = "=== 图片关键词-一次20个 ===\n"
        api_info += ", ".join(self.IMAGE_API.keys()) + "\n"
        
        api_info += "\n= 视频关键词-比较慢，一次3个 =\n"
        video_keys = [key for key in self.VIDEO_API.keys() if key]  # 跳过空键
        api_info += ", ".join(video_keys) + "\n"

        nodes = []
        
        # 首先添加API信息节点
        nodes.append({
            "type": "node",
            "data": {
                "user_id": 80000000,
                "nickname": "关键词列表",
                "content": [
                    {"type": "text", "data": {"text": api_info}}
                ]
            }
        })
        
        # 由于很多API不支持HEAD请求或需要特殊处理，跳过URL验证，直接信任配置的URL并尝试发送
        logging.info(f"使用URL: {url}，跳过验证直接发送")
        
        # 根据媒体确定发送数量
        if media_type == "image":
            count = 20  # 图片发送20个
            summary = f"共 {count} 张图片"
        else:  # video
            count = 3   # 视频发送5个
            summary = f"共 {count} 个视频"
        
        # 然后添加媒体内容节点
        # 为视频添加浏览器Headers，模拟真实浏览器访问，避免反爬虫机制
        for i in range(1, count + 1):
            if media_type == "video":
                # 视频添加浏览器Headers，提高下载成功率
                nodes.append({
                    "type": "node",
                    "data": {
                        "user_id": 80000000,
                        "nickname": "匿名用户",
                        "content": [
                            {
                                "type": "video",
                                "data": {
                                    "url": url,
                                    "headers": {
                                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                                        "Referer": "https://api-m.com/ ",
                                        "Accept": "*/*",
                                        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
                                    }
                                }
                            }
                        ]
                    }
                })
            else:
                # 图片保持简单，直接发送URL
                nodes.append({
                    "type": "node",
                    "data": {
                        "user_id": 80000000,
                        "nickname": "匿名用户",
                        "content": [
                            {"type": "image", "data": {"url": url}}
                        ]
                    }
                })

        payload = {
            "group_id": group_id,
            "messages": nodes,
            "source": title,
            "summary": summary,
            "prompt": f"[{title}]",
            "news": [{"text": "点击查看详情"}]
        }

        try:
            # 增加超时时间到30秒，避免合并转发消息处理时间过长导致的超时
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(api, headers=headers, json=payload)
                logging.info(f"[Forward{count}] {r.status_code} {r.text}")
        except httpx.ReadTimeout:
            logging.warning(f"请求超时(30秒): {api} - 但可能仍在后台处理中")
        except httpx.ConnectError:
            logging.error(f"连接错误: {api}")
        except httpx.RequestError as e:
            logging.error(f"请求错误: {e}")
        except Exception as e:
            logging.exception("发送失败")

    # ---------- 触发器 ----------
    @bot.group_event
    async def on_group_event(self, msg: GroupMessage):
        text = msg.raw_message.strip()

        if text in self.IMAGE_API:
            await self.send_forward(msg.group_id, self.IMAGE_API[text], "image", f"{text} 图片合集")
        elif text in self.VIDEO_API:
            await self.send_forward(msg.group_id, self.VIDEO_API[text], "video", f"{text} 视频合集")
