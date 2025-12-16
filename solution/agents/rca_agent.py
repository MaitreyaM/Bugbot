

import json
import re
import time
from typing import Any, Dict, Optional

from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

from core.shared_memory import SharedMemory, RCAResult
from core.message_logger import MessageLogger, EventType
from tools.file_tools import read_file, list_directory
from tools.analysis_tools import parse_error_trace


RCA_SYSTEM_PROMPT = """You are an expert software debugger for Python/FastAPI/SQLAlchemy services.

Goal: deliver a concise, evidence-backed RCA for the provided error trace.

Use tools effectively:
- Start with `parse_error_trace` to extract error type, message, and primary location.
- Use `read_file` to inspect the implicated source code and confirm the mistake.
- Use `list_directory` only if you need to locate files.

Always:
- Verify hypotheses in the actual code.
- Distinguish the symptom (exception) from the true root cause.
- Ground conclusions in specific code evidence (file/line/function).

Return one JSON object with: error_type, error_message, root_cause, affected_file, affected_line, affected_function, evidence (list of short bullets)."""


def parse_rca_output(output: str) -> Optional[RCAResult]:
   
    try:
        
        json_match = re.search(r'\{[^{}]*"error_type"[^{}]*\}', output, re.DOTALL)
        if not json_match:
            json_match = re.search(r'\{[\s\S]*?"evidence"[\s\S]*?\][\s\S]*?\}', output)
        
        if json_match:
            json_str = json_match.group()
            data = json.loads(json_str)
            
            return RCAResult(
                error_type=data.get("error_type", ""),
                error_message=data.get("error_message", ""),
                root_cause=data.get("root_cause", ""),
                affected_file=data.get("affected_file", ""),
                affected_line=int(data.get("affected_line", 0)),
                affected_function=data.get("affected_function", ""),
                evidence=data.get("evidence", [])
            )
        
       
        error_type_match = re.search(r'(?:Error Type|error_type)[:\s]+([A-Za-z]+Error)', output)
        error_msg_match = re.search(r'(?:Error Message|error_message)[:\s]+(.+?)(?:\n|$)', output)
        
        if error_type_match:
            return RCAResult(
                error_type=error_type_match.group(1),
                error_message=error_msg_match.group(1) if error_msg_match else "",
                root_cause="Unable to parse structured output - see raw analysis",
                affected_file="",
                affected_line=0,
                affected_function="",
                evidence=["Raw output parsing required manual review"]
            )
        
        return None
        
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        print(f"Error parsing RCA output: {e}")
        return None


def create_rca_agent_node(
    llm,
    logger: MessageLogger,
    shared_memory: SharedMemory,
    trace_path: str
):
    """
    Create RCA agent node that logs to MessageLogger.
    
    Args:
        llm: LangChain LLM instance
        logger: MessageLogger for capturing interactions
        shared_memory: SharedMemory for storing results
        trace_path: Path to error trace file
        
    Returns:
        Function that can be used as a LangGraph node
    """
    
    
    task_description = f"""Perform an RCA of the error trace at: {trace_path}

Suggested flow:
1) Call `parse_error_trace` to get primary file/line/function.
2) Use `read_file` on that file to inspect the code around the line.
3) If needed, `list_directory` to find related files.
4) Produce one JSON object with fields: error_type, error_message, root_cause, affected_file, affected_line, affected_function, evidence (list)."""
    
    
    agent_executor = create_react_agent(
        model=llm,
        tools=[parse_error_trace, read_file, list_directory],
        prompt=RCA_SYSTEM_PROMPT,
    )
    
    def rca_node(state: dict) -> dict:
        """Execute RCA agent and log everything."""
        
        
        logger.log_agent_start("RCA_Agent", {
            "task": "Root Cause Analysis",
            "trace_path": trace_path,
            "tools": ["parse_error_trace", "read_file", "list_directory"]
        })
        
        start_time = time.time()
        
       
        current_messages = state.get("messages", [])
        if not current_messages or "Root Cause Analysis" not in str(current_messages[-1]):
            current_messages.append(HumanMessage(content=task_description))
            state["messages"] = current_messages
        
      
        try:
            result = agent_executor.invoke(state)
        except Exception as e:
            logger.log_error("RCA_Agent", type(e).__name__, str(e))
            raise
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        
        for msg in result.get("messages", []):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    logger.log_event(
                        agent_name="RCA_Agent",
                        event_type=EventType.TOOL_CALL,
                        data={
                            "tool_name": tool_call["name"],
                            "arguments": tool_call["args"]
                        }
                    )
            
          
            if hasattr(msg, "type") and msg.type == "tool":
                logger.log_event(
                    agent_name="RCA_Agent",
                    event_type=EventType.TOOL_RESULT,
                    data={
                        "tool_name": msg.name,
                        "result": str(msg.content)[:2000],
                        "result_truncated": len(str(msg.content)) > 2000
                    }
                )
        
       
        final_content = result["messages"][-1].content if result.get("messages") else ""
        rca_result = parse_rca_output(str(final_content))
        
        if rca_result:
            
            shared_memory.set_rca(rca_result)
            logger.log_memory_update("RCA_Agent", "rca", rca_result.to_dict())
        
        
        logger.log_agent_end("RCA_Agent", {
            "output": str(final_content)[:500] + ("..." if len(str(final_content)) > 500 else ""),
            "success": rca_result is not None,
            "duration_ms": duration_ms
        })
        
     
        return {
            "messages": result.get("messages", []),
            "rca": shared_memory.get_rca_dict() 
        }
    
    return rca_node


async def run_rca_agent(
    llm,
    logger: MessageLogger,
    shared_memory: SharedMemory,
    trace_path: str
) -> Dict[str, Any]:
    """
    Run the RCA agent and store results in shared memory.
    
    This is a compatibility wrapper for the old interface.
    
    Args:
        llm: LangChain LLM instance
        logger: MessageLogger for capturing interactions
        shared_memory: SharedMemory for reading context and storing results
        trace_path: Path to error trace file
        
    Returns:
        Dictionary with the agent's output and parsed results
    """
   
    node = create_rca_agent_node(llm, logger, shared_memory, trace_path)
    
    
    initial_state = {
        "messages": [],
        "rca": None,
        "fix_plan": None,
        "patch_metadata": None,
        "trace_path": trace_path,
        "codebase_path": "",
        "output_dir": ""
    }
    
    result_state = node(initial_state)
    
    rca_dict = shared_memory.get_rca_dict()
    
    return {
        "output": str(result_state.get("messages", [])[-1].content if result_state.get("messages") else ""),
        "parsed": rca_dict,
        "success": rca_dict is not None
    }
