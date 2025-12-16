
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum
import threading


class EventType(str, Enum):
   
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    MEMORY_UPDATE = "memory_update"
    ERROR = "error"
    SYSTEM = "system"


@dataclass
class LogEvent:
   
    event_id: int
    timestamp: str
    agent_name: str
    event_type: str
    iteration: int
    data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MessageLogger:
    """
    Thread-safe message logger for capturing all agent interactions.
    
    """
    
    def __init__(self, session_id: Optional[str] = None):
        self._lock = threading.RLock()
        self._session_id = session_id or str(uuid.uuid4())[:8]
        self._start_time = datetime.utcnow().isoformat()
        self._events: List[LogEvent] = []
        self._event_counter = 0
        self._current_iterations: Dict[str, int] = {}
    
    def _next_event_id(self) -> int:
        """Get the next event ID."""
        self._event_counter += 1
        return self._event_counter
    
    def _get_iteration(self, agent_name: str) -> int:
        """Get current iteration for an agent."""
        return self._current_iterations.get(agent_name, 0)
    
    def _increment_iteration(self, agent_name: str) -> int:
        """Increment and return iteration for an agent."""
        self._current_iterations[agent_name] = self._current_iterations.get(agent_name, 0) + 1
        return self._current_iterations[agent_name]
    
    def log_event(
        self,
        agent_name: str,
        event_type: EventType,
        data: Optional[Dict[str, Any]] = None,
        iteration: Optional[int] = None
    ) -> None:
       
        with self._lock:
            event = LogEvent(
                event_id=self._next_event_id(),
                timestamp=datetime.utcnow().isoformat(),
                agent_name=agent_name,
                event_type=event_type.value,
                iteration=iteration if iteration is not None else self._get_iteration(agent_name),
                data=data or {}
            )
            self._events.append(event)
    
    def log_agent_start(self, agent_name: str, task_info: Dict[str, Any]) -> None:
        """Log the start of an agent's execution."""
        with self._lock:
            iteration = self._increment_iteration(agent_name)
            self.log_event(
                agent_name=agent_name,
                event_type=EventType.AGENT_START,
                data={
                    "task": task_info.get("task", ""),
                    "context_received": task_info.get("context", {}),
                    "tools_available": task_info.get("tools", [])
                },
                iteration=iteration
            )
    
    def log_agent_end(self, agent_name: str, result: Dict[str, Any]) -> None:
       
        self.log_event(
            agent_name=agent_name,
            event_type=EventType.AGENT_END,
            data={
                "output": result.get("output", ""),
                "success": result.get("success", True),
                "duration_ms": result.get("duration_ms", 0)
            }
        )
    
    def log_tool_call(
        self,
        agent_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Any
    ) -> None:
       
        self.log_event(
            agent_name=agent_name,
            event_type=EventType.TOOL_CALL,
            data={
                "tool_name": tool_name,
                "arguments": arguments
            }
        )
        
        
        self.log_event(
            agent_name=agent_name,
            event_type=EventType.TOOL_RESULT,
            data={
                "tool_name": tool_name,
                "result": str(result)[:2000] if result else None,  
                "result_truncated": len(str(result)) > 2000 if result else False
            }
        )
    
    def log_llm_request(
        self,
        agent_name: str,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """Log an LLM API request."""
        
        truncated_messages = []
        for msg in messages:
            truncated_msg = msg.copy()
            if "content" in truncated_msg and truncated_msg["content"]:
                content = str(truncated_msg["content"])
                if len(content) > 1000:
                    truncated_msg["content"] = content[:1000] + "... [truncated]"
            truncated_messages.append(truncated_msg)
        
        self.log_event(
            agent_name=agent_name,
            event_type=EventType.LLM_REQUEST,
            data={
                "model": model,
                "messages": truncated_messages,
                "tools_provided": [t.get("function", {}).get("name", "unknown") for t in (tools or [])],
                "message_count": len(messages)
            }
        )
    
    def log_llm_response(
        self,
        agent_name: str,
        text_content: Optional[str],
        tool_calls: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """Log an LLM API response."""
        self.log_event(
            agent_name=agent_name,
            event_type=EventType.LLM_RESPONSE,
            data={
                "text_content": text_content[:1000] + "... [truncated]" if text_content and len(text_content) > 1000 else text_content,
                "tool_calls": tool_calls or [],
                "has_tool_calls": bool(tool_calls)
            }
        )
    
    def log_memory_update(
        self,
        agent_name: str,
        section: str,
        data: Dict[str, Any]
    ) -> None:
        """Log a shared memory update."""
        self.log_event(
            agent_name=agent_name,
            event_type=EventType.MEMORY_UPDATE,
            data={
                "section": section,
                "keys_updated": list(data.keys()) if data else []
            }
        )
    
    def log_error(
        self,
        agent_name: str,
        error_type: str,
        error_message: str,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
   
        self.log_event(
            agent_name=agent_name,
            event_type=EventType.ERROR,
            data={
                "error_type": error_type,
                "error_message": error_message,
                "details": details or {}
            }
        )
    
    def log_system(self, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Log a system-level event."""
        self.log_event(
            agent_name="system",
            event_type=EventType.SYSTEM,
            data={
                "message": message,
                **(data or {})
            }
        )
    
    def get_events(self) -> List[Dict[str, Any]]:
        """Get all logged events as dictionaries."""
        with self._lock:
            return [e.to_dict() for e in self._events]
    
    def get_events_for_agent(self, agent_name: str) -> List[Dict[str, Any]]:
        """Get all events for a specific agent."""
        with self._lock:
            return [e.to_dict() for e in self._events if e.agent_name == agent_name]
    
    def get_full_log(self) -> Dict[str, Any]:
        """Get the complete log structure."""
        with self._lock:
            return {
                "session_id": self._session_id,
                "start_time": self._start_time,
                "end_time": datetime.utcnow().isoformat(),
                "total_events": len(self._events),
                "agents_involved": list(set(e.agent_name for e in self._events if e.agent_name != "system")),
                "events": self.get_events()
            }
    
    def save(self, filepath: str) -> None:
        """
        Save the complete message history to a JSON file.
        
        Args:
            filepath: Path to save the JSON file
        """
        with self._lock:
            path = Path(filepath)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.get_full_log(), f, indent=2, ensure_ascii=False)
    
    def __repr__(self) -> str:
        return f"MessageLogger(session={self._session_id}, events={len(self._events)})"

