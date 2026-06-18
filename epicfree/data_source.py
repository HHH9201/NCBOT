# data_source.py - Epic 限免数据源（适配 NcatBot5）
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from traceback import format_exc
from typing import Dict, List, Literal, Union, Optional

from httpx import AsyncClient

from .config import plugin_config

logger = logging.getLogger("epicfree")

# 插件数据目录
PLUGIN_DIR = Path(__file__).resolve().parent
DATA_DIR = PLUGIN_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 订阅状态配置文件
subscribe_file = DATA_DIR / "status.json"
# 上次推送内容缓存
pushed_cache_file = DATA_DIR / "last_pushed.json"


def get_proxy_url() -> Optional[str]:
    """根据插件配置生成 httpx 所需的代理 URL 字符串"""
    if not plugin_config.proxy_type or not plugin_config.proxy_host:
        logger.info("[Proxy Config] 未配置代理, 将直接连接。")
        return None

    proxy_url = ""
    proxy_type_lower = plugin_config.proxy_type.lower()

    if proxy_type_lower in ["socks5", "http"]:
        scheme = proxy_type_lower
        host_port = f"{plugin_config.proxy_host}:{plugin_config.proxy_port}"
        if plugin_config.proxy_username and plugin_config.proxy_password:
            auth_part = f"{plugin_config.proxy_username}:{plugin_config.proxy_password}@"
            proxy_url = f"{scheme}://{auth_part}{host_port}"
        else:
            proxy_url = f"{scheme}://{host_port}"

    if not proxy_url:
        logger.warning(f"[Proxy Config] 无效的 proxy_type: {plugin_config.proxy_type}")
        return None

    logger.info(f"[Proxy Config] 插件已配置代理: {proxy_url}")
    return proxy_url


async def subscribe_helper(
    method: Literal["读取", "启用", "删除"] = "读取", sub_type: str = "", subject: str = ""
) -> Union[Dict, str]:
    """写入与读取订阅配置"""
    if subscribe_file.exists():
        try:
            status_data = json.loads(subscribe_file.read_text(encoding="UTF-8"))
        except Exception:
            status_data = {"群聊": [], "私聊": []}
    else:
        status_data = {"群聊": [], "私聊": []}
        subscribe_file.write_text(
            json.dumps(status_data, ensure_ascii=False, indent=2), encoding="UTF-8"
        )

    if method == "读取":
        return status_data
    elif method == "启用":
        if subject in status_data.get(sub_type, []):
            return f"{sub_type}{subject} 已经订阅过 Epic 限免游戏资讯了哦！"
        status_data.setdefault(sub_type, []).append(subject)
    elif method == "删除":
        if subject not in status_data.get(sub_type, []):
            return f"{sub_type}{subject} 未曾订阅过 Epic 限免游戏资讯！"
        status_data[sub_type].remove(subject)

    try:
        subscribe_file.write_text(
            json.dumps(status_data, ensure_ascii=False, indent=2), encoding="UTF-8"
        )
        return f"{sub_type}{subject} Epic 限免游戏资讯订阅已{method}！"
    except Exception as e:
        logger.error(f"写入 Epic 订阅 JSON 错误 {e.__class__.__name__}\n{format_exc()}")
        return f"{sub_type}{subject} Epic 限免游戏资讯订阅{method}失败.."


def check_push(msg_list: List[dict]) -> bool:
    """检查是否需要重新推送（去重）"""
    last_text: List[str] = (
        json.loads(pushed_cache_file.read_text(encoding="UTF-8"))
        if pushed_cache_file.exists()
        else []
    )
    # 提取本次消息中的游戏链接，作为唯一标识
    this_text = [
        item["content"]
        for item in msg_list
        if item.get("type") == "text"
        and item.get("content", "").startswith("https://store.epicgames.com")
    ]

    need_push = this_text != last_text
    if need_push:
        logger.debug(f"检测到新的 Epic 免费游戏，准备推送。上次推送: {last_text}, 本次: {this_text}")
        pushed_cache_file.write_text(
            json.dumps(this_text, ensure_ascii=False, indent=2), encoding="UTF-8"
        )
    return need_push


async def query_epic_api() -> List:
    """获取所有 Epic Game Store 促销游戏"""
    async with AsyncClient(proxy=get_proxy_url()) as client:
        try:
            res = await client.get(
                "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions",
                params={"locale": "zh-CN", "country": "CN", "allowCountries": "CN"},
                headers={
                    "Referer": "https://www.epicgames.com/store/zh-CN/",
                    "Content-Type": "application/json; charset=utf-8",
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                        " (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36"
                    ),
                },
                timeout=10.0,
            )
            res_json = res.json()
            return res_json["data"]["Catalog"]["searchStore"]["elements"]
        except Exception as e:
            logger.error(f"请求 Epic Store API 错误 {e.__class__.__name__}\n{format_exc()}")
            return []


async def get_epic_free() -> List[dict]:
    """
    获取 Epic Game Store 免费游戏信息
    返回格式: [{"type": "text"|"image", "content": "..."}]
    """
    games = await query_epic_api()
    if not games:
        return [{"type": "text", "content": "Epic 可能又抽风啦，请稍后再试（"}]

    logger.debug(
        f"获取到 {len(games)} 个游戏数据：\n{('、'.join(game['title'] for game in games))}"
    )
    game_cnt, msg_list = 0, []
    for game in games:
        game_name = game.get("title", "未知")
        try:
            if not game.get("promotions"):
                continue
            game_promotions = game["promotions"]["promotionalOffers"]
            upcoming_promotions = game["promotions"]["upcomingPromotionalOffers"]
            original_price = game["price"]["totalPrice"]["fmtPrice"]["originalPrice"]
            discount_price = game["price"]["totalPrice"]["fmtPrice"]["discountPrice"]
            if not game_promotions:
                if upcoming_promotions:
                    logger.info(f"跳过即将推出免费游玩的游戏：{game_name}({discount_price})")
                continue
            elif game["price"]["totalPrice"]["fmtPrice"]["discountPrice"] != "0":
                logger.info(f"跳过促销但不免费的游戏：{game_name}({discount_price})")
                continue
            # 处理游戏预览图
            for image in game["keyImages"]:
                if image.get("url") and image["type"] in [
                    "Thumbnail",
                    "VaultOpened",
                    "DieselStoreFrontWide",
                    "OfferImageWide",
                ]:
                    msg_list.append({"type": "image", "content": image["url"]})
                    break
            # 处理游戏发行信息
            game_dev, game_pub = game["seller"]["name"], game["seller"]["name"]
            for pair in game["customAttributes"]:
                if pair["key"] == "developerName":
                    game_dev = pair["value"]
                elif pair["key"] == "publisherName":
                    game_pub = pair["value"]
            dev_com = f"{game_dev} 开发、" if game_dev != game_pub else ""
            companies = (
                f"由 {dev_com}{game_pub} 发行，"
                if game_pub != "Epic Dev Test Account"
                else ""
            )
            # 处理游戏限免结束时间
            date_rfc3339 = game_promotions[0]["promotionalOffers"][0]["endDate"]
            end_date = (
                datetime.strptime(date_rfc3339, "%Y-%m-%dT%H:%M:%S.%f%z")
                .astimezone(timezone(timedelta(hours=8)))
                .strftime("%m {m} %d {d} %H:%M")
                .format(m="月", d="日")
            )
            # 处理游戏商城链接
            if game.get("url"):
                game_url = game["url"]
            else:
                slugs = (
                    [
                        x["pageSlug"]
                        for x in game.get("offerMappings", [])
                        if x.get("pageType") == "productHome"
                    ]
                    + [
                        x["pageSlug"]
                        for x in game.get("catalogNs", {}).get("mappings", [])
                        if x.get("pageType") == "productHome"
                    ]
                    + [
                        x["value"]
                        for x in game.get("customAttributes", [])
                        if "productSlug" in x.get("key")
                    ]
                )
                game_url = "https://store.epicgames.com/zh-CN{}".format(
                    f"/p/{slugs[0]}" if len(slugs) else ""
                )
            game_cnt += 1
            msg_list.append({"type": "text", "content": game_url})
            msg_list.append(
                {
                    "type": "text",
                    "content": "{} ({})\n\n{}\n\n游戏{}将在 {} 结束免费游玩，戳上方链接领取吧~".format(
                        game_name,
                        original_price,
                        game["description"],
                        companies,
                        end_date,
                    ),
                }
            )
        except (AttributeError, IndexError, TypeError):
            logger.debug(f"处理游戏 {game_name} 时遇到应该忽略的错误\n{format_exc()}")
        except Exception as e:
            logger.error(f"组织 Epic 订阅消息错误 {e.__class__.__name__}\n{format_exc()}")

    msg_list.insert(
        0,
        {
            "type": "text",
            "content": f"{game_cnt} 款游戏现在免费！" if game_cnt else "暂未找到正在促销的游戏...",
        },
    )
    return msg_list
