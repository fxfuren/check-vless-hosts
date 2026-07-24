import json
import os
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from .logger import logger

@dataclass
class ProbeTarget:
    label: str
    url: str

@dataclass
class FiltersConfig:
    name_contains: List[str] = field(default_factory=list)
    protocol_type: Optional[str] = None

@dataclass
class TelegramEmojiConfig:
    notification: str = "🔔"
    success: str = "✅"
    error: str = "❌"
    stats: str = "📊"
    time: str = "⏱"
    link: str = "🔗"
    info: str = "ℹ️"

@dataclass
class TelegramConfig:
    bot_token: str
    chat_id: str
    topic_id: Optional[str] = None
    emoji: TelegramEmojiConfig = field(default_factory=TelegramEmojiConfig)

@dataclass
class AppConfig:
    subscription_url: str
    check_interval_sec: int = 60
    subscription_refresh_every_n_cycles: int = 10
    xray_core_path: str = "/usr/bin/xray"
    socks_base_port: int = 10001
    probe_timeout_sec: int = 15
    probe_targets: List[ProbeTarget] = field(default_factory=list)
    filters: FiltersConfig = field(default_factory=FiltersConfig)
    alert_threshold_down: int = 2
    alert_threshold_degraded: int = 2
    telegram: Optional[TelegramConfig] = None
    state_path: str = "/data/state.json"

def load_config(path: str) -> AppConfig:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found at {path}")
        
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    # Parse nested objects
    probe_targets = [ProbeTarget(**pt) for pt in data.get('probe_targets', [])]
    
    filters_data = data.get('filters', {})
    filters = FiltersConfig(
        name_contains=filters_data.get('name_contains', []),
        protocol_type=filters_data.get('protocol_type')
    )
    
    telegram_data = data.get('telegram')
    telegram = None
    if telegram_data:
        emoji_data = telegram_data.get('emoji', {})
        emoji = TelegramEmojiConfig(**emoji_data)
        telegram = TelegramConfig(
            bot_token=telegram_data['bot_token'],
            chat_id=telegram_data['chat_id'],
            topic_id=telegram_data.get('topic_id'),
            emoji=emoji
        )
        
    config = AppConfig(
        subscription_url=data['subscription_url'],
        check_interval_sec=data.get('check_interval_sec', 60),
        subscription_refresh_every_n_cycles=data.get('subscription_refresh_every_n_cycles', 10),
        xray_core_path=data.get('xray_core_path', '/usr/bin/xray'),
        socks_base_port=data.get('socks_base_port', 10001),
        probe_timeout_sec=data.get('probe_timeout_sec', 15),
        probe_targets=probe_targets,
        filters=filters,
        alert_threshold_down=data.get('alert_threshold_down', 2),
        alert_threshold_degraded=data.get('alert_threshold_degraded', 2),
        telegram=telegram,
        state_path=data.get('state_path', '/data/state.json')
    )
    
    logger.info("Config loaded successfully", extra={"extra_data": {"config_path": path}})
    return config
