import urllib.parse
from dataclasses import dataclass
from typing import Dict, Optional, Any

@dataclass
class VlessHost:
    raw_uri: str
    uuid: str
    host: str
    port: int
    name: str
    params: Dict[str, str]
    json_outbound: Optional[Dict[str, Any]] = None

def parse_vless_uri(uri: str) -> Optional[VlessHost]:
    try:
        if not uri.startswith("vless://"):
            return None
            
        parsed = urllib.parse.urlparse(uri)
        
        # userInfo and netloc: uuid@host:port
        netloc = parsed.netloc
        if "@" in netloc:
            uuid, host_port = netloc.split("@", 1)
        else:
            return None
            
        if ":" in host_port:
            host, port_str = host_port.split(":", 1)
            port = int(port_str)
        else:
            host = host_port
            port = 443
            
        params = dict(urllib.parse.parse_qsl(parsed.query))
        name = urllib.parse.unquote(parsed.fragment) if parsed.fragment else host
        
        return VlessHost(
            raw_uri=uri,
            uuid=uuid,
            host=host,
            port=port,
            name=name,
            params=params
        )
    except Exception as e:
        return None
