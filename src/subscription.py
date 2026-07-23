import base64
import aiohttp
from typing import List, Optional
from .logger import logger
from .config import FiltersConfig
from .vless_parser import VlessHost, parse_vless_uri

async def fetch_subscription(url: str, timeout: int = 30) -> Optional[str]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=timeout) as response:
                response.raise_for_status()
                return await response.text()
    except Exception as e:
        logger.error(f"Failed to fetch subscription: {e}")
        return None

def decode_subscription(content: str) -> List[str]:
    try:
        # Base64 strings might not have correct padding
        padding = len(content) % 4
        if padding:
            content += '=' * (4 - padding)
        decoded_bytes = base64.b64decode(content)
        decoded_str = decoded_bytes.decode('utf-8')
        return [line.strip() for line in decoded_str.splitlines() if line.strip()]
    except Exception as e:
        logger.error(f"Failed to decode subscription: {e}")
        # Sometimes subscription is not base64 but just plaintext lines
        return [line.strip() for line in content.splitlines() if line.strip()]

def filter_hosts(hosts: List[VlessHost], filters: FiltersConfig) -> List[VlessHost]:
    filtered = []
    for host in hosts:
        # Filter by name
        if filters.name_contains:
            if not any(nc.lower() in host.name.lower() for nc in filters.name_contains):
                continue
                
        # Filter by protocol type
        if filters.protocol_type:
            ptype = host.params.get("type", "").lower()
            if ptype != filters.protocol_type.lower():
                continue
                
        filtered.append(host)
        
    return filtered

async def get_filtered_hosts(url: str, filters: FiltersConfig) -> Optional[List[VlessHost]]:
    content = await fetch_subscription(url)
    if not content:
        return None
        
    lines = decode_subscription(content)
    
    hosts = []
    for line in lines:
        parsed = parse_vless_uri(line)
        if parsed:
            hosts.append(parsed)
            
    filtered = filter_hosts(hosts, filters)
    logger.info(f"Loaded {len(filtered)} hosts from subscription (out of {len(hosts)} total)")
    return filtered
