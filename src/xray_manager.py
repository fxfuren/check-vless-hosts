import json
import asyncio
import tempfile
import os
from typing import List, Dict, Any, Optional
from .vless_parser import VlessHost
from .logger import logger

def generate_xray_config(hosts: List[VlessHost], base_port: int) -> Dict[str, Any]:
    inbounds = []
    outbounds = []
    rules = []
    
    for i, host in enumerate(hosts):
        socks_port = base_port + i
        in_tag = f"in-host{i}"
        out_tag = f"out-host{i}"
        
        # Inbound
        inbounds.append({
            "tag": in_tag,
            "port": socks_port,
            "listen": "127.0.0.1",
            "protocol": "socks",
            "settings": {"auth": "noauth", "udp": False}
        })
        
        # Outbound
        stream_settings: Dict[str, Any] = {"network": host.params.get("type", "tcp")}
        
        # security
        security = host.params.get("security", "none")
        if security != "none":
            stream_settings["security"] = security
            if security == "tls" or security == "reality":
                tls_settings = {}
                sni = host.params.get("sni", host.host)
                if sni:
                    tls_settings["serverName"] = sni
                
                fp = host.params.get("fp")
                if fp:
                    tls_settings["fingerprint"] = fp
                    
                alpn = host.params.get("alpn")
                if alpn:
                    tls_settings["alpn"] = alpn.split(',')

                pbk = host.params.get("pbk")
                if pbk:
                    tls_settings["publicKey"] = pbk

                sid = host.params.get("sid")
                if sid:
                    tls_settings["shortId"] = sid
                
                if security == "reality":
                    stream_settings["realitySettings"] = tls_settings
                else:
                    stream_settings["tlsSettings"] = tls_settings
        
        # network specific settings
        net_type = stream_settings["network"]
        if net_type == "xhttp":
            stream_settings["xhttpSettings"] = {"path": host.params.get("path", "/")}
        elif net_type == "ws":
            stream_settings["wsSettings"] = {
                "path": host.params.get("path", "/"),
                "headers": {"Host": host.params.get("host", host.params.get("sni", host.host))}
            }
        elif net_type == "grpc":
            stream_settings["grpcSettings"] = {
                "serviceName": host.params.get("serviceName", ""),
                "multiMode": host.params.get("mode", "") == "multi"
            }
        elif net_type == "tcp" and host.params.get("headerType") == "http":
            stream_settings["tcpSettings"] = {
                "header": {
                    "type": "http",
                    "request": {
                        "path": [host.params.get("path", "/")],
                        "headers": {"Host": [host.params.get("host", host.host)]}
                    }
                }
            }
            
        outbounds.append({
            "tag": out_tag,
            "protocol": "vless",
            "settings": {
                "vnext": [{
                    "address": host.host,
                    "port": host.port,
                    "users": [{"id": host.uuid, "encryption": host.params.get("encryption", "none")}]
                }]
            },
            "streamSettings": stream_settings
        })
        
        # Rule
        rules.append({
            "type": "field",
            "inboundTag": [in_tag],
            "outboundTag": out_tag
        })
        
    return {
        "log": {"loglevel": "warning"},
        "inbounds": inbounds,
        "outbounds": outbounds,
        "routing": {
            "domainStrategy": "AsIs",
            "rules": rules
        }
    }

class XrayManager:
    def __init__(self, xray_path: str):
        self.xray_path = xray_path
        self.process: Optional[asyncio.subprocess.Process] = None
        self.config_path: Optional[str] = None
        
    def is_running(self) -> bool:
        return self.process is not None and self.process.returncode is None
        
    async def start(self, hosts: List[VlessHost], base_port: int) -> bool:
        config_obj = generate_xray_config(hosts, base_port)
        
        fd, temp_path = tempfile.mkstemp(suffix=".json", prefix="xray_")
        with os.fdopen(fd, 'w') as f:
            json.dump(config_obj, f)
            
        self.config_path = temp_path
        
        try:
            self.process = await asyncio.create_subprocess_exec(
                self.xray_path, "-c", self.config_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Wait a bit to see if it crashes immediately
            await asyncio.sleep(1)
            if self.process.returncode is not None:
                stderr = await self.process.stderr.read()
                logger.error(f"xray-core failed to start. exit code: {self.process.returncode}, stderr: {stderr.decode()}")
                return False
                
            logger.info("xray-core started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Exception starting xray-core: {e}")
            return False
            
    async def stop(self):
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
            self.process = None
            logger.info("xray-core stopped")
            
        if self.config_path and os.path.exists(self.config_path):
            try:
                os.remove(self.config_path)
            except:
                pass
            self.config_path = None
            
    async def restart(self, hosts: List[VlessHost], base_port: int) -> bool:
        await self.stop()
        return await self.start(hosts, base_port)
