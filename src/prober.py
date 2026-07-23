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
    connector = ProxyConnector.from_url(f"socks5://127.0.0.1:{socks_port}")
    start_time = time.monotonic()
    
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
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
        return ProbeResult(target_label=target.label, success=False, error=str(e))

async def probe_host(host: VlessHost, socks_port: int, targets: List[ProbeTarget], timeout_sec: float) -> HostProbeResult:
    tasks = [probe_target(socks_port, target, timeout_sec) for target in targets]
    results = await asyncio.gather(*tasks)
    return HostProbeResult(
        host_name=host.name,
        raw_uri=host.raw_uri,
        results=list(results)
    )

async def probe_all_hosts(hosts: List[VlessHost], base_port: int, targets: List[ProbeTarget], timeout_sec: float) -> List[HostProbeResult]:
    tasks = []
    for i, host in enumerate(hosts):
        socks_port = base_port + i
        tasks.append(probe_host(host, socks_port, targets, timeout_sec))
        
    results = await asyncio.gather(*tasks)
    return list(results)
