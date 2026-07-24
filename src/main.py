import asyncio
import signal
import sys
import os
from .logger import logger
from .config import load_config
from .subscription import get_filtered_hosts
from .xray_manager import XrayManager
from .prober import probe_all_hosts
from .state import StateManager, HostStatus
from .alerter import TelegramAlerter
from .vless_parser import VlessHost

class MonitorDaemon:
    def __init__(self, config_path: str):
        self.config = load_config(config_path)
        self.state_manager = StateManager(
            self.config.state_path, 
            self.config.alert_threshold_down, 
            self.config.alert_threshold_degraded
        )
        self.alerter = TelegramAlerter(self.config.telegram)
        self.xray_manager = XrayManager(self.config.xray_core_path)
        
        self.running = False
        self.cycle_count = 0
        self.current_hosts: list[VlessHost] = []

    async def _fetch_and_apply_subscription(self) -> bool:
        logger.info("Fetching subscription...")
        hosts = await get_filtered_hosts(self.config.subscription_url, self.config.filters)
        if hosts is None:
            logger.warning("Failed to fetch/parse subscription, will keep using previous config if any.")
            return False
            
        if not hosts:
            logger.warning("Subscription returned 0 matching hosts.")
            self.current_hosts = []
            await self.xray_manager.stop()
            return True
            
        # check if changed
        # Compare raw URIs in exact order
        old_uris = [h.raw_uri for h in self.current_hosts]
        new_uris = [h.raw_uri for h in hosts]
        
        if old_uris != new_uris or not self.xray_manager.is_running():
            logger.info("Hosts changed or xray not running, generating new xray config and restarting...")
            self.current_hosts = hosts
            success = await self.xray_manager.restart(self.current_hosts, self.config.socks_base_port)
            if not success:
                logger.error("Failed to start xray-core")
                return False
        else:
            logger.info("Hosts unchanged, keeping current xray-core process.")
            self.current_hosts = hosts
            
        return True

    async def _run_cycle(self):
        if self.cycle_count % self.config.subscription_refresh_every_n_cycles == 0:
            await self._fetch_and_apply_subscription()
            
        self.cycle_count += 1

        if not self.current_hosts or not self.xray_manager.is_running():
            logger.info("No hosts to monitor or xray-core not running. Skipping probe.")
            return

        logger.info(f"Starting probes for {len(self.current_hosts)} hosts...")
        results = await probe_all_hosts(
            self.current_hosts,
            self.config.socks_base_port,
            self.config.probe_targets,
            self.config.probe_timeout_sec
        )
        
        events = self.state_manager.evaluate(results)
        self.state_manager.save()
        
        for event in events:
            logger.info(f"State changed for {event.host_name}: {event.old_status} -> {event.new_status}")
            
            # Логируем точную причину падения
            if event.new_status != HostStatus.UP:
                for r in event.results:
                    if not r.success:
                        reason = r.error if r.error else f"HTTP Status {r.status_code}"
                        logger.warning(f"Host {event.host_name} target '{r.target_label}' failed: {reason}")
            
            await self.alerter.send_event(event)

    async def run(self):
        self.running = True
        logger.info("Starting VLESS Host Monitor daemon")
        await self.alerter.send_startup_notification()
        
        try:
            while self.running:
                cycle_start = asyncio.get_event_loop().time()
                
                try:
                    await self._run_cycle()
                except Exception as e:
                    logger.exception(f"Unexpected error in run cycle: {e}")
                    
                if not self.running:
                    break
                    
                elapsed = asyncio.get_event_loop().time() - cycle_start
                sleep_time = max(0.1, self.config.check_interval_sec - elapsed)
                logger.debug(f"Cycle finished, sleeping for {sleep_time:.2f} seconds")
                await asyncio.sleep(sleep_time)
                
        finally:
            await self.shutdown()
            
    async def shutdown(self):
        logger.info("Shutting down daemon...")
        self.running = False
        self.state_manager.save()
        await self.xray_manager.stop()
        logger.info("Shutdown complete.")

def handle_sigterm(daemon: MonitorDaemon):
    logger.info("Received termination signal, initiating graceful shutdown...")
    daemon.running = False

async def main():
    config_path = os.environ.get("CONFIG_PATH", "config.json")
    try:
        daemon = MonitorDaemon(config_path)
    except Exception as e:
        logger.exception(f"Failed to initialize daemon: {e}")
        sys.exit(1)
        
    loop = asyncio.get_running_loop()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_sigterm, daemon)
        except NotImplementedError:
            # add_signal_handler is not implemented on Windows for some signals
            pass
            
    await daemon.run()

if __name__ == "__main__":
    try:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
