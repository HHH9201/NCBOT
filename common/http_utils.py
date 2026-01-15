# /home/hjh/BOT/NCBOT/common/http_utils.py
import asyncio
import logging
import random
import aiohttp
from typing import Optional, Dict, Any, Union

from .const import USER_AGENTS, DEFAULT_HEADERS
from .config import GLOBAL_CONFIG

class AsyncHttpClient:
    """
    通用异步HTTP客户端，封装了重试、UA轮询、代理和错误处理
    """
    def __init__(self, 
                 proxy: Optional[str] = None, 
                 retry_count: int = 3, 
                 retry_delay: float = 2.0,
                 timeout: int = 30):
        self.proxy = proxy or GLOBAL_CONFIG.get('proxy')
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        
        # 验证代理格式
        if self.proxy and not self.proxy.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
            logging.warning(f"[HTTP] 代理配置格式不正确: {self.proxy}，已禁用代理")
            self.proxy = None

    def _get_headers(self, headers: Optional[Dict] = None) -> Dict:
        """构造请求头，合并默认头和用户头，并随机选择UA"""
        final_headers = DEFAULT_HEADERS.copy()
        if headers:
            final_headers.update(headers)
        
        # 如果没有指定UA，随机选择一个
        if 'User-Agent' not in final_headers or final_headers['User-Agent'] == "Mozilla/5.0":
            final_headers['User-Agent'] = random.choice(USER_AGENTS)
            
        return final_headers

    async def fetch(self, 
                   url: str, 
                   method: str = "GET", 
                   headers: Optional[Dict] = None, 
                   params: Optional[Dict] = None,
                   data: Any = None,
                   json_data: Any = None,
                   verify_ssl: bool = False,
                   response_type: str = "text") -> Union[str, Dict, bytes, None]:
        """
        执行HTTP请求
        
        Args:
            url: 请求URL
            method: 请求方法 (GET, POST等)
            headers: 自定义请求头
            params: URL参数
            data: 表单数据
            json_data: JSON数据
            verify_ssl: 是否验证SSL证书 (默认False)
            response_type: 返回类型 ("text", "json", "content")
            
        Returns:
            请求结果，失败返回None
        """
        
        for attempt in range(self.retry_count):
            current_headers = self._get_headers(headers)
            
            try:
                async with aiohttp.ClientSession(
                    timeout=self.timeout,
                    connector=aiohttp.TCPConnector(ssl=verify_ssl)
                ) as session:
                    async with session.request(
                        method, 
                        url, 
                        headers=current_headers,
                        params=params,
                        data=data,
                        json=json_data,
                        proxy=self.proxy
                    ) as response:
                        
                        if response.status in [403, 429]:
                            logging.warning(f"[HTTP] 请求被拦截 ({response.status})，尝试重试... ({attempt+1}/{self.retry_count})")
                            await asyncio.sleep(self.retry_delay * (attempt + 1))
                            continue
                            
                        if response.status >= 400:
                            logging.error(f"[HTTP] 请求失败: {url} [{response.status}]")
                            return None
                            
                        if response_type == "json":
                            return await response.json()
                        elif response_type == "content":
                            return await response.read()
                        else:
                            return await response.text()
                            
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logging.warning(f"[HTTP] 请求异常: {e}，正在重试... ({attempt+1}/{self.retry_count})")
                await asyncio.sleep(self.retry_delay * (attempt + 1))
            except Exception as e:
                logging.error(f"[HTTP] 未知错误: {e}")
                return None
                
        logging.error(f"[HTTP] 请求最终失败: {url}")
        return await response.text()
                            
    async def get_redirect_url(self, url: str, headers: Optional[Dict] = None, verify_ssl: bool = False) -> Optional[str]:
        """获取重定向后的真实URL"""
        current_headers = self._get_headers(headers)
        try:
            async with aiohttp.ClientSession(
                timeout=self.timeout,
                connector=aiohttp.TCPConnector(ssl=verify_ssl)
            ) as session:
                async with session.head(url, headers=current_headers, proxy=self.proxy, allow_redirects=True) as resp:
                    return str(resp.url)
        except Exception as e:
            # 如果 HEAD 失败，尝试 GET
            try:
                async with aiohttp.ClientSession(
                    timeout=self.timeout,
                    connector=aiohttp.TCPConnector(ssl=verify_ssl)
                ) as session:
                    async with session.get(url, headers=current_headers, proxy=self.proxy, allow_redirects=True) as resp:
                        return str(resp.url)
            except Exception as e2:
                logging.error(f"[HTTP] 获取重定向URL失败: {e2}")
                return None

    async def get_text(self, url: str, **kwargs) -> Optional[str]:
        return await self.fetch(url, response_type="text", **kwargs)

    async def get_json(self, url: str, **kwargs) -> Optional[Dict]:
        return await self.fetch(url, response_type="json", **kwargs)

    async def get_content(self, url: str, **kwargs) -> Optional[bytes]:
        return await self.fetch(url, response_type="content", **kwargs)

# 全局默认实例
http_client = AsyncHttpClient()
