import asyncio
import time
import json
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
    start_time = time.monotonic()
    
    try:
        # Use curl directly to avoid any aiohttp-socks quirks
        cmd = [
            "curl", "-s", "-w", "%{http_code}", "-o", "/dev/null",
            "-x", f"socks5h://127.0.0.1:{socks_port}",
            "-m", str(int(timeout_sec)),
            target.url
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout_bytes, stderr_bytes = await proc.communicate()
        latency = (time.monotonic() - start_time) * 1000
        
        if proc.returncode == 0:
            status_code_str = stdout_bytes.decode().strip()
            status_code = int(status_code_str) if status_code_str.isdigit() else 0
            
            # Curl succeeded, return the HTTP status code
            # Note: For generate_204, status is usually 204.
            # Cloudflare trace is 200.
            success = 200 <= status_code < 400
            return ProbeResult(
                target_label=target.label,
                success=success,
                status_code=status_code,
                latency_ms=latency
            )
        else:
            # Curl failed (e.g. timeout, connection reset)
            error_msg = stderr_bytes.decode().strip()
            if not error_msg:
                if proc.returncode == 28:
                    error_msg = "Timeout"
                elif proc.returncode == 7:
                    error_msg = "Failed to connect to proxy or host"
                elif proc.returncode == 52:
                    error_msg = "Empty reply from server"
                else:
                    error_msg = f"Curl error code {proc.returncode}"
                    
            return ProbeResult(
                target_label=target.label,
                success=False,
                error=error_msg
            )
            
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
        base_delay = i * 1.0
        tasks.append(probe_host(host, socks_port, targets, timeout_sec, base_delay))
        
    results = await asyncio.gather(*tasks)
    return list(results)
