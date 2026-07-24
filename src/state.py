import json
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from enum import Enum
from .logger import logger
from .prober import HostProbeResult, ProbeResult

class HostStatus(str, Enum):
    UP = "up"
    DEGRADED = "degraded"
    DOWN = "down"

@dataclass
class HostState:
    name: str
    raw_uri: str
    host_address: str = "Unknown"
    consecutive_down: int = 0
    consecutive_degraded: int = 0
    last_alerted_status: HostStatus = HostStatus.UP
    last_results: List[Dict] = field(default_factory=list)

@dataclass
class StateEvent:
    host_name: str
    raw_uri: str
    host_address: str
    old_status: HostStatus
    new_status: HostStatus
    results: List[ProbeResult]

class StateManager:
    def __init__(self, state_path: str, threshold_down: int, threshold_degraded: int):
        self.state_path = state_path
        self.threshold_down = threshold_down
        self.threshold_degraded = threshold_degraded
        self.hosts: Dict[str, HostState] = {}
        self.load()
        
    def load(self):
        if not os.path.exists(self.state_path):
            return
            
        try:
            with open(self.state_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            for name, state_dict in data.items():
                self.hosts[name] = HostState(
                    name=state_dict['name'],
                    raw_uri=state_dict['raw_uri'],
                    host_address=state_dict.get('host_address', "Unknown"),
                    consecutive_down=state_dict.get('consecutive_down', 0),
                    consecutive_degraded=state_dict.get('consecutive_degraded', 0),
                    last_alerted_status=HostStatus(state_dict.get('last_alerted_status', HostStatus.UP.value)),
                    last_results=state_dict.get('last_results', [])
                )
        except Exception as e:
            logger.error(f"Failed to load state from {self.state_path}: {e}")
            
    def save(self):
        try:
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            with open(self.state_path, 'w', encoding='utf-8') as f:
                json.dump({name: asdict(state) for name, state in self.hosts.items()}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save state to {self.state_path}: {e}")

    def evaluate(self, probe_results: List[HostProbeResult]) -> List[StateEvent]:
        events = []
        current_names = set(r.host_name for r in probe_results)
        
        # Cleanup removed hosts
        keys_to_remove = [name for name in self.hosts if name not in current_names]
        for name in keys_to_remove:
            del self.hosts[name]
            
        for result in probe_results:
            name = result.host_name
            if name not in self.hosts:
                self.hosts[name] = HostState(name=name, raw_uri=result.raw_uri, host_address=result.host_address)
                
            state = self.hosts[name]
            state.raw_uri = result.raw_uri
            state.host_address = result.host_address
            state.last_results = [asdict(r) for r in result.results]
            
            if result.is_all_success:
                state.consecutive_down = 0
                state.consecutive_degraded = 0
                if state.last_alerted_status != HostStatus.UP:
                    events.append(StateEvent(
                        host_name=name,
                        raw_uri=state.raw_uri,
                        host_address=state.host_address,
                        old_status=state.last_alerted_status,
                        new_status=HostStatus.UP,
                        results=result.results
                    ))
                    state.last_alerted_status = HostStatus.UP
                    
            elif result.is_all_failed:
                state.consecutive_down += 1
                state.consecutive_degraded = 0
                if state.consecutive_down >= self.threshold_down and state.last_alerted_status != HostStatus.DOWN:
                    events.append(StateEvent(
                        host_name=name,
                        raw_uri=state.raw_uri,
                        host_address=state.host_address,
                        old_status=state.last_alerted_status,
                        new_status=HostStatus.DOWN,
                        results=result.results
                    ))
                    state.last_alerted_status = HostStatus.DOWN
                    
            else: # partial success (degraded)
                state.consecutive_degraded += 1
                state.consecutive_down = 0
                if state.consecutive_degraded >= self.threshold_degraded and state.last_alerted_status != HostStatus.DEGRADED:
                    events.append(StateEvent(
                        host_name=name,
                        raw_uri=state.raw_uri,
                        host_address=state.host_address,
                        old_status=state.last_alerted_status,
                        new_status=HostStatus.DEGRADED,
                        results=result.results
                    ))
                    state.last_alerted_status = HostStatus.DEGRADED
                    
        return events
