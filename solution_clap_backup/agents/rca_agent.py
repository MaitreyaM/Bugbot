"""
RCA Agent - Root Cause Analysis Agent

This agent is responsible for:
- Analyzing provided stack traces and logs
- Identifying what caused the error
- Identifying the affected file and code area
- Providing supporting evidence

The agent uses tools to parse error traces and read source files.
"""

import json
import re
from typing import Any, Dict, List, Optional
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))

from core.shared_memory import SharedMemory, RCAResult
from core.message_logger import MessageLogger
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


RCA_TASK_DESCRIPTION = """Perform an RCA of the error trace at: {trace_path}

Suggested flow:
1) Call `parse_error_trace` to get primary file/line/function.
2) Use `read_file` on that file to inspect the code around the line.
3) If needed, `list_directory` to find related files.
4) Produce one JSON object with fields: error_type, error_message, root_cause, affected_file, affected_line, affected_function, evidence (list)."""


def create_rca_agent(
    llm_service,
    logger: MessageLogger,
    shared_memory: SharedMemory,
    trace_path: str,
    model_name: str = "gemini-2.0-flash"
):
    
   
    from clap import Agent
    
  
    agent = Agent(
        name="RCA_Agent",
        backstory=RCA_SYSTEM_PROMPT,
        task_description=RCA_TASK_DESCRIPTION.format(trace_path=trace_path),
        task_expected_output="A structured JSON RCA report identifying the root cause of the error",
        llm_service=llm_service,
        model=model_name,
        tools=[parse_error_trace, read_file, list_directory],
        parallel_tool_calls=False
    )
    
    return agent


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


async def run_rca_agent(
    llm_service,
    logger: MessageLogger,
    shared_memory: SharedMemory,
    trace_path: str,
    model_name: str = "gemini-2.0-flash"
) -> Dict[str, Any]:
   
    logger.log_agent_start("RCA_Agent", {
        "task": "Root Cause Analysis",
        "trace_path": trace_path,
        "tools": ["parse_error_trace", "read_file", "list_directory"]
    })
    
    try:
      
        agent = create_rca_agent(llm_service, logger, shared_memory, trace_path, model_name)
        
        import time
        start_time = time.time()
        
        result = await agent.run()
        
        duration_ms = int((time.time() - start_time) * 1000)
        
     
        output = result.get("output", "") if isinstance(result, dict) else str(result)
        
  
        rca_result = parse_rca_output(output)
        
        if rca_result:
       
            shared_memory.set_rca(rca_result)
            logger.log_memory_update("RCA_Agent", "rca", rca_result.to_dict())
        
      
        logger.log_agent_end("RCA_Agent", {
            "output": output[:500] + "..." if len(output) > 500 else output,
            "success": rca_result is not None,
            "duration_ms": duration_ms
        })
        
        return {
            "output": output,
            "parsed": rca_result.to_dict() if rca_result else None,
            "success": rca_result is not None
        }
        
    except Exception as e:
        logger.log_error("RCA_Agent", type(e).__name__, str(e))
        raise

