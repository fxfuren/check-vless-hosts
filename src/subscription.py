import base64
import aiohttp
import json
from typing import List, Optional, Any
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

def decode_base64_str(content: str) -> str:
    try:
        padding = len(content) % 4
        if padding:
            content += '=' * (4 - padding)
        return base64.b64decode(content).decode('utf-8')
    except:
        return content

def parse_json_outbounds(data: Any) -> List[VlessHost]:
    outbounds = data.get("outbounds", [])
    hosts = []
    for out in outbounds:
        protocol = out.get("protocol", "")
        # Ignore core outbounds
        if protocol in ("freedom", "blackhole", "dns"):
            continue
            
        tag = out.get("tag", "Unknown Host")
        host = VlessHost(
            raw_uri=f"json://{tag}", # Mock URI
            uuid="",
            host="",
            port=443,
            name=tag,
            params={},
            json_outbound=out
        )
        hosts.append(host)
    return hosts

def parse_subscription_content(content: str) -> List[VlessHost]:
    # 1. Try parsing directly as JSON
    try:
        data = json.loads(content)
        if "outbounds" in data:
            return parse_json_outbounds(data)
    except:
        pass
        
    # 2. Try decoding base64 and then parsing as JSON
    try:
        decoded_str = decode_base64_str(content)
        data = json.loads(decoded_str)
        if "outbounds" in data:
            return parse_json_outbounds(data)
    except:
        pass
        
    # 3. Fallback to parsing line-by-line VLESS URIs
    lines = decode_base64_str(content).splitlines()
    hosts = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parsed = parse_vless_uri(line)
        if parsed:
            hosts.append(parsed)
            
    return hosts

def filter_hosts(hosts: List[VlessHost], filters: FiltersConfig) -> List[VlessHost]:
    filtered = []
    for host in hosts:
        if filters.name_contains:
            if not any(nc.lower() in host.name.lower() for nc in filters.name_contains):
                continue
                
        if filters.protocol_type:
            # If it's a JSON outbound, try to extract protocol or network
            ptype = ""
            if host.json_outbound:
                stream = host.json_outbound.get("streamSettings", {})
                ptype = stream.get("network", "")
            else:
                ptype = host.params.get("type", "").lower()
                
            if ptype.lower() != filters.protocol_type.lower():
                continue
                
        filtered.append(host)
        
    return filtered

async def get_filtered_hosts(url: str, filters: FiltersConfig) -> Optional[List[VlessHost]]:
    content = await fetch_subscription(url)
    if not content:
        return None
        
    hosts = parse_subscription_content(content)
    filtered = filter_hosts(hosts, filters)
    
    # Sort deterministically so Xray SOCKS port mappings don't shuffle randomly
    filtered.sort(key=lambda h: h.name)
    logger.info(f"Loaded {len(filtered)} hosts from subscription (out of {len(hosts)} total)")
    return filtered
