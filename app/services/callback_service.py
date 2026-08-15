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

    # 通知限流：1分钟内仅发送1条通知
    _NOTIFY_COOLDOWN = 60

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._config = settings.callback
            self._last_notify_time: float = 0.0

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
            "tag": self._config.tag,
            "message": msg_data,
            "timestamp": int(time.time())
        }
        return json.dumps(payload, ensure_ascii=False)

    async def _notify_failure(self, body: str, last_error: Optional[Exception]) -> None:
        """回调失败后发送通知（限流：1分钟内仅1条）

        通知顺序：
        1. 向监听该联系人的 WebSocket 客户端推送"订单服务器通信异常"
        2. 向配置的微信联系人发送通知消息

        Args:
            body: 原始回调请求体
            last_error: 最后一次错误信息
        """
        now = time.time()
        if now - self._last_notify_time < self._NOTIFY_COOLDOWN:
            logger.info("通知冷却中，跳过本次通知（距上次 %.0fs）", now - self._last_notify_time)
            return

        # 解析 who 信息
        who = ""
        try:
            payload = json.loads(body)
            who = payload.get("who", "")
        except (json.JSONDecodeError, TypeError):
            pass

        # 1. 在当前对话中推送通信异常消息
        try:
            from app.services.listen_service import manager
            await manager.broadcast_to_listeners(who, {
                "type": "callback_error",
                "message": "【订单服务器通信异常】\n请稍后重试或联系管理员",
                "who": who,
            })
            logger.info("已向 WebSocket 客户端推送通信异常通知: who=%s", who)
        except Exception as e:
            logger.error("推送 WebSocket 通信异常通知失败: %s", e)

        # 2. 向特定微信联系人发送通知
        notify_contact = self._config.notify_contact
        if notify_contact:
            try:
                from app.services.wechat_service import get_wechat, safe_send_msg

                error_detail = str(last_error) if last_error else "未知错误"
                notify_msg = (
                    f"【订单服务器通信异常】\n"
                    f"监听对象: {who}\n"
                    f"错误信息: {error_detail}"
                )

                await asyncio.to_thread(
                    safe_send_msg,
                    get_wechat(""),
                    notify_contact,
                    notify_msg,
                )
                logger.info("已发送回调失败通知给 %s", notify_contact)
            except Exception as e:
                logger.error("发送回调失败通知时出错: %s", e)

        self._last_notify_time = now

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

        # 回调全部失败后，发送微信通知
        await self._notify_failure(body, last_error)

        return False


# 全局回调服务实例
callback_service = CallbackService()
