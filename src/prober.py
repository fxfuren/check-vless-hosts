import asyncio
import time
import aiohttp
from aiohttp_socks import ProxyConnector
from dataclasses import dataclass
from typing import Optional, List, Dict
from .vless_parser import VlessHost
from .config import ProbeTarget
from .logger import logger

@dataclass
class ProbeResult:
    target_label: str
    success: bool
    status_code: Optional[int] = None
    latency_ms: Optional[float] = None
    error: Optional[str] = None

@dataclass
class HostProbeResult:
    host_name: str
    raw_uri: str
    host_address: str
    results: List[ProbeResult]
    
    @property
    def is_all_success(self) -> bool:
        return all(r.success for r in self.results) if self.results else False
        
    @property
    def is_partial_success(self) -> bool:
        return any(r.success for r in self.results) and not self.is_all_success
        
    @property
    def is_all_failed(self) -> bool:
        return not any(r.success for r in self.results) if self.results else True

async def probe_target(socks_port: int, target: ProbeTarget, timeout_sec: float) -> ProbeResult:
    connector = ProxyConnector.from_url(f"socks5://127.0.0.1:{socks_port}", rdns=True)
    start_time = time.monotonic()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }
    
    try:
        async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
            async with session.get(target.url, timeout=aiohttp.ClientTimeout(total=timeout_sec)) as resp:
                latency = (time.monotonic() - start_time) * 1000
                success = resp.status < 400
                return ProbeResult(
                    target_label=target.label,
                    success=success,
                    status_code=resp.status,
                    latency_ms=latency
                )
    except asyncio.TimeoutError:
        return ProbeResult(target_label=target.label, success=False, error="Timeout")
    except Exception as e:
        error_msg = str(e)
        if not error_msg:
            error_msg = type(e).__name__
        return ProbeResult(target_label=target.label, success=False, error=error_msg)

async def probe_host_target_with_delay(delay: float, socks_port: int, target: ProbeTarget, timeout_sec: float) -> ProbeResult:
    if delay > 0:
        await asyncio.sleep(delay)
    return await probe_target(socks_port, target, timeout_sec)

async def probe_host(host: VlessHost, socks_port: int, targets: List[ProbeTarget], timeout_sec: float, base_delay: float = 0.0) -> HostProbeResult:
    tasks = []
    for i, target in enumerate(targets):
        # Stagger each target by 0.5s
        tasks.append(probe_host_target_with_delay(base_delay + i * 0.5, socks_port, target, timeout_sec))
        
    results = await asyncio.gather(*tasks)
    return HostProbeResult(
        host_name=host.name,
        raw_uri=host.raw_uri,
        host_address=host.host,
        results=list(results)
    )

async def probe_all_hosts(hosts: List[VlessHost], base_port: int, targets: List[ProbeTarget], timeout_sec: float) -> List[HostProbeResult]:
    tasks = []
    for i, host in enumerate(hosts):
        socks_port = base_port + i
        # Stagger each host by 1.0s to avoid bursting
        base_delay = i * 1.0
        tasks.append(probe_host(host, socks_port, targets, timeout_sec, base_delay))
        
    results = await asyncio.gather(*tasks)
    return list(results)
