import aiohttp
import urllib.parse
import html
from typing import List, Optional
from .logger import logger
from .config import TelegramConfig
from .state import StateEvent, HostStatus
from .prober import ProbeResult
from .vless_parser import parse_vless_uri

class TelegramAlerter:
    def __init__(self, config: Optional[TelegramConfig]):
        self.config = config
        
    def _format_event(self, event: StateEvent) -> str:
        if not self.config:
            return ""
            
        e = self.config.emoji
        
        # Optional: Add custom emoji tags if they are numeric (Telegram premium emoji ID)
        def pe(emoji_val: str) -> str:
            if emoji_val.isdigit():
                return f'<tg-emoji emoji-id="{emoji_val}">⭐</tg-emoji>'
            return emoji_val
            
        # Determine main emoji and text based on new status
        if event.new_status == HostStatus.UP:
            status_emoji = pe(e.success)
            status_text = "ВОССТАНОВЛЕН"
        elif event.new_status == HostStatus.DEGRADED:
            status_emoji = "⚠️"
            status_text = "ДЕГРАДАЦИЯ"
        else:
            status_emoji = pe(e.error)
            status_text = "НЕДОСТУПЕН"
            
        title_emoji = pe(e.notification)
        
        parsed = parse_vless_uri(event.raw_uri)
        host_address = parsed.host if parsed else "Unknown"
        
        msg = f"{title_emoji} <b>{status_emoji} Хост {status_text}</b>\n\n"
        msg += f"{pe(e.info)} <b>Имя:</b> <code>{html.escape(event.host_name)}</code>\n"
        msg += f"{pe(e.link)} <b>Адрес:</b> <code>{html.escape(host_address)}</code>\n"
        
        msg += f"\n{pe(e.stats)} <b>Результаты проверок:</b>\n"
        for r in event.results:
            if r.success:
                latency_str = f"{r.latency_ms:.0f}ms" if r.latency_ms is not None else "N/A"
                msg += f"  {pe(e.success)} {html.escape(r.target_label)}: OK ({latency_str})\n"
            else:
                msg += f"  {pe(e.error)} {html.escape(r.target_label)}: FAIL ({html.escape(r.error or 'Unknown')})\n"
                
        return msg

    async def send_event(self, event: StateEvent):
        if not self.config:
            return
            
        text = self._format_event(event)
        
        url = f"https://api.telegram.org/bot{self.config.bot_token}/sendMessage"
        payload = {
            "chat_id": self.config.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        
        if self.config.topic_id:
            payload["message_thread_id"] = self.config.topic_id
            
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status >= 400:
                        error_text = await resp.text()
                        logger.error(f"Telegram API error: {resp.status} - {error_text}")
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")
            
    async def send_startup_notification(self):
        if not self.config:
            return
            
        e = self.config.emoji
        text = f"{e.notification if not e.notification.isdigit() else '<tg-emoji emoji-id=\"' + e.notification + '\">⭐</tg-emoji>'} <b>Мониторинг запущен</b>"
        
        url = f"https://api.telegram.org/bot{self.config.bot_token}/sendMessage"
        payload = {
            "chat_id": self.config.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_notification": True
        }
        
        if self.config.topic_id:
            payload["message_thread_id"] = self.config.topic_id
            
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(url, json=payload, timeout=10)
        except Exception as e:
            logger.error(f"Failed to send Telegram startup notification: {e}")
