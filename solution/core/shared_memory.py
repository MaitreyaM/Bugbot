

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, field, asdict
import threading


@dataclass
class RCAResult:
    
    error_type: str = ""
    error_message: str = ""
    root_cause: str = ""
    affected_file: str = ""
    affected_line: int = 0
    affected_function: str = ""
    evidence: list = field(default_factory=list)
    timestamp: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RCAResult":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class FixPlan:
    
    description: str = ""
    steps: list = field(default_factory=list)
    safety_considerations: list = field(default_factory=list)
    expected_outcome: str = ""
    timestamp: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FixPlan":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class PatchMetadata:
    
    original_file: str = ""
    patched_file: str = ""
    changes_made: list = field(default_factory=list)
    lines_modified: list = field(default_factory=list)
    patch_content: str = ""
    timestamp: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PatchMetadata":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class SharedMemory:
    """
    Thread-safe shared memory for multi-agent communication.
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        self._state: Dict[str, Any] = {
            "rca": None,
            "fix_plan": None,
            "patch_metadata": None,
            "metadata": {
                "created_at": datetime.utcnow().isoformat(),
                "last_updated": datetime.utcnow().isoformat(),
                "version": "1.0"
            }
        }
    
    def _update_timestamp(self):
        
        self._state["metadata"]["last_updated"] = datetime.utcnow().isoformat()
    
    
    def set_rca(self, rca: RCAResult) -> None:
      
        with self._lock:
            rca.timestamp = datetime.utcnow().isoformat()
            self._state["rca"] = rca.to_dict()
            self._update_timestamp()
    
    def get_rca(self) -> Optional[RCAResult]:
       
        with self._lock:
            if self._state["rca"]:
                return RCAResult.from_dict(self._state["rca"])
            return None
    
    def get_rca_dict(self) -> Optional[Dict[str, Any]]:
       
        with self._lock:
            return self._state.get("rca")
    
   
    def set_fix_plan(self, fix_plan: FixPlan) -> None:
       
        with self._lock:
            fix_plan.timestamp = datetime.utcnow().isoformat()
            self._state["fix_plan"] = fix_plan.to_dict()
            self._update_timestamp()
    
    def get_fix_plan(self) -> Optional[FixPlan]:
       
        with self._lock:
            if self._state["fix_plan"]:
                return FixPlan.from_dict(self._state["fix_plan"])
            return None
    
    def get_fix_plan_dict(self) -> Optional[Dict[str, Any]]:
        
        with self._lock:
            return self._state.get("fix_plan")
    
    
    def set_patch_metadata(self, patch: PatchMetadata) -> None:
       
        with self._lock:
            patch.timestamp = datetime.utcnow().isoformat()
            self._state["patch_metadata"] = patch.to_dict()
            self._update_timestamp()
    
    def get_patch_metadata(self) -> Optional[PatchMetadata]:
       
        with self._lock:
            if self._state["patch_metadata"]:
                return PatchMetadata.from_dict(self._state["patch_metadata"])
            return None
    
    def get_patch_metadata_dict(self) -> Optional[Dict[str, Any]]:
        
        with self._lock:
            return self._state.get("patch_metadata")
    
  
    def get_full_state(self) -> Dict[str, Any]:
        
        with self._lock:
            return json.loads(json.dumps(self._state))  # Deep copy
    
    def get_context_for_agent(self, agent_name: str) -> Dict[str, Any]:
        
        with self._lock:
            if agent_name == "fix_agent":
                return {"rca": self._state.get("rca")}
            elif agent_name == "patch_agent":
                return {
                    "rca": self._state.get("rca"),
                    "fix_plan": self._state.get("fix_plan")
                }
            else:
                return {}
    
    def save(self, filepath: str) -> None:
        with self._lock:
            path = Path(filepath)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2, ensure_ascii=False)
    
    def load(self, filepath: str) -> None:
        
        with self._lock:
            path = Path(filepath)
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    self._state = json.load(f)
    
    def __repr__(self) -> str:
        return f"SharedMemory(rca={'set' if self._state['rca'] else 'empty'}, fix_plan={'set' if self._state['fix_plan'] else 'empty'}, patch={'set' if self._state['patch_metadata'] else 'empty'})"

