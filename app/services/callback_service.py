"""
消息回调服务
将监听到的消息通过 HTTP POST 异步回调推送到外部服务
"""
import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, Optional

import httpx

from app.utils.config import settings

logger = logging.getLogger(__name__)


class CallbackService:
    """消息回调服务"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CallbackService, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._config = settings.callback

    @property
    def enabled(self) -> bool:
        return self._config.enabled and bool(self._config.url)

    def generate_signature(self, secret: str, timestamp: str, body: str) -> str:
        """生成 HMAC-SHA256 签名

        签名算法: HMAC-SHA256(secret, timestamp + "." + body)

        Args:
            secret: 签名密钥
            timestamp: Unix 时间戳（秒级字符串）
            body: 请求体 JSON 字符串

        Returns:
            十六进制签名字符串
        """
        message = f"{timestamp}.{body}"
        signature = hmac.new(
            secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    def build_payload(self, msg_data: Dict[str, Any], who: str) -> str:
        """构建回调请求体

        Args:
            msg_data: wxautox4 原始消息数据 (msg.raw)
            who: 监听的联系人名称

        Returns:
            JSON 字符串
        """
        payload = {
            "who": who,
            "message": msg_data,
            "timestamp": int(time.time())
        }
        return json.dumps(payload, ensure_ascii=False)

    async def send_callback(self, body: str) -> bool:
        """异步发送回调请求，包含重试逻辑

        Args:
            body: JSON 请求体

        Returns:
            是否发送成功
        """
        if not self.enabled:
            return False

        last_error: Optional[Exception] = None
        for attempt in range(1, self._config.retry_attempts + 1):
            timestamp = str(int(time.time()))
            signature = self.generate_signature(self._config.secret, timestamp, body)
            headers = {
                "Content-Type": "application/json",
                "X-Callback-Timestamp": timestamp,
                "X-Callback-Signature": signature,
            }

            try:
                async with httpx.AsyncClient(timeout=self._config.timeout) as client:
                    response = await client.post(
                        self._config.url,
                        content=body,
                        headers=headers,
                    )

                if 200 <= response.status_code < 300:
                    logger.info(
                        "回调成功: url=%s, status=%d, attempt=%d",
                        self._config.url, response.status_code, attempt,
                    )
                    return True

                logger.warning(
                    "回调返回非成功状态: url=%s, status=%d, body=%s, attempt=%d",
                    self._config.url, response.status_code, response.text[:200], attempt,
                )

            except httpx.RequestError as e:
                last_error = e
                logger.warning(
                    "回调请求失败: url=%s, error=%s, attempt=%d",
                    self._config.url, str(e), attempt,
                )

            if attempt < self._config.retry_attempts:
                await asyncio.sleep(self._config.retry_delay)

        logger.error(
            "回调最终失败: url=%s, attempts=%d, last_error=%s",
            self._config.url, self._config.retry_attempts, last_error,
        )
        return False


# 全局回调服务实例
callback_service = CallbackService()
