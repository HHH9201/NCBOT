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
            
        self.session: Optional[aiohttp.ClientSession] = None

    async def get_session(self) -> aiohttp.ClientSession:
        """获取或创建aiohttp session"""
        if self.session is None or self.session.closed:
            timeout = self.timeout
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    async def close(self):
        """关闭session"""
        if self.session and not self.session.closed:
            await self.session.close()

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
                   response_type: str = "text",
                   proxy: Optional[str] = None,
                   timeout: Optional[int] = None) -> Union[str, Dict, bytes, None]:
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
            proxy: 代理设置 (None=使用默认, ""=不使用代理, "http://..."=指定代理)
            timeout: 超时时间(秒)，默认使用session配置
            
        Returns:
            请求结果，失败返回None
        """
        
        # 确定使用的代理
        # 如果 proxy 参数为 None，使用 self.proxy
        # 如果 proxy 参数为 ""，则使用 None (不使用代理)
        # 如果 proxy 参数有值，则使用该值
        current_proxy = self.proxy if proxy is None else (None if proxy == "" else proxy)
        
        # 确定超时设置
        request_timeout = aiohttp.ClientTimeout(total=timeout) if timeout is not None else None

        for attempt in range(self.retry_count):
            current_headers = self._get_headers(headers)
            
            try:
                session = await self.get_session()
                # 注意：verify_ssl 参数现在通过 ssl 参数传递给 request
                # aiohttp 期望 ssl 参数为 SSLContext 或 bool
                
                async with session.request(
                    method, 
                    url, 
                    headers=current_headers,
                    params=params,
                    data=data,
                    json=json_data,
                    proxy=current_proxy,
                    ssl=verify_ssl,
                    timeout=request_timeout
                ) as response:
                    
                    if response.status in [403, 429]:
                        logging.warning(f"[HTTP] 请求被拦截 ({response.status})，尝试重试... ({attempt+1}/{self.retry_count})")
                        await asyncio.sleep(self.retry_delay)
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
                error_msg = str(e)
                if not error_msg:
                    error_msg = repr(e)
                logging.warning(f"[HTTP] 请求异常: {error_msg} (尝试 {attempt+1}/{self.retry_count})")
                # 遇到超时或网络错误，继续尝试下一次重试
                await asyncio.sleep(self.retry_delay)
                continue
                
            except Exception as e:
                logging.error(f"[HTTP] 未知错误: {e}")
                return None
        
        return None
                            
    async def get_redirect_url(self, url: str, headers: Optional[Dict] = None, verify_ssl: bool = False, timeout: Optional[int] = None) -> Optional[str]:
        """获取重定向后的真实URL"""
        current_headers = self._get_headers(headers)
        request_timeout = aiohttp.ClientTimeout(total=timeout) if timeout is not None else self.timeout
        
        try:
            async with aiohttp.ClientSession(
                timeout=request_timeout,
                connector=aiohttp.TCPConnector(ssl=verify_ssl)
            ) as session:
                async with session.head(url, headers=current_headers, proxy=self.proxy, allow_redirects=True) as resp:
                    return str(resp.url)
        except Exception as e:
            # 如果 HEAD 失败，尝试 GET
            try:
                async with aiohttp.ClientSession(
                    timeout=request_timeout,
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
