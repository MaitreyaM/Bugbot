"""
Patch Generation Agent (LangGraph Version)

This agent is responsible for:
- Reading the RCA and the fix plan
- Using tools to interact with the codebase
- Generating the actual code fix
- Writing the fix into a new file only (e.g., fixed_<original>.py)
- Avoiding hallucinations
- Applying minimal, safe changes

Migrated to use LangGraph's create_react_agent for reliable tool calling.
"""

import json
import re
import time
from typing import Any, Dict, Optional
from pathlib import Path

from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

from core.shared_memory import SharedMemory, PatchMetadata
from core.message_logger import MessageLogger, EventType
from tools.file_tools import read_file, write_file
from tools.terminal_tools import run_terminal_command


PATCH_SYSTEM_PROMPT = """You are an expert code-generation specialist focused on precise, minimal patches.

Goal: produce a fixed source file based on the RCA and fix plan, with minimal, well-scoped edits.

Recommended flow:
- Use `read_file` to load the original file before changing anything.
- Apply the smallest change set that fully addresses the root cause and fix plan.
- Use `write_file` to save the full corrected file (e.g., `fixed_<basename>.py` or the provided hint).
- Optionally use `run_terminal_command` for light validation (e.g., grep, format, quick tests) if needed.

Guidelines:
- Keep formatting/comments intact; don't refactor unrelated code.
- Be explicit about what changed and where.
- Return patch metadata as a JSON object: original_file, patched_file, changes_made (list), lines_modified (list)."""


def parse_patch_output(output: str) -> Optional[PatchMetadata]:
    """
    Parse the Patch agent's output to extract structured metadata.
    
    Args:
        output: Raw output string from the Patch agent
        
    Returns:
        PatchMetadata object if parsing succeeds, None otherwise
    """
    try:
        
        json_match = re.search(r'\{[^{}]*"original_file"[^{}]*\}', output, re.DOTALL)
        if not json_match:
            json_match = re.search(r'\{[\s\S]*?"changes_made"[\s\S]*?\][\s\S]*?\}', output)
        
        if json_match:
            json_str = json_match.group()
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
              
                start_idx = output.find('{"original_file"')
                if start_idx == -1:
                    start_idx = output.find('{\n    "original_file"')
                
                if start_idx != -1:
                    brace_count = 0
                    end_idx = start_idx
                    for i, char in enumerate(output[start_idx:], start_idx):
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                end_idx = i + 1
                                break
                    
                    json_str = output[start_idx:end_idx]
                    data = json.loads(json_str)
                else:
                    raise json.JSONDecodeError("No valid JSON found", output, 0)
            
            return PatchMetadata(
                original_file=data.get("original_file", ""),
                patched_file=data.get("patched_file", ""),
                changes_made=data.get("changes_made", []),
                lines_modified=data.get("lines_modified", [])
            )
        
        return None
        
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        print(f"Error parsing Patch output: {e}")
        return None


def create_patch_agent_node(
    llm,
    logger: MessageLogger,
    shared_memory: SharedMemory,
    output_dir: str
):
    
    
    
    rca_dict = shared_memory.get_rca_dict()
    fix_dict = shared_memory.get_fix_plan_dict()
    
    rca_context = json.dumps(rca_dict, indent=2) if rca_dict else "No RCA data available"
    fix_context = json.dumps(fix_dict, indent=2) if fix_dict else "No fix plan available"
    
    
    affected_file = rca_dict.get("affected_file", "unknown") if rca_dict else "unknown"
    affected_line = rca_dict.get("affected_line", 0) if rca_dict else 0
    patched_filename_hint = f"fixed_{Path(affected_file).name}" if affected_file not in ("", "unknown", None) else "fixed_patch.py"
    
    task_description = f"""Generate a patched version of the buggy file based on the following analysis.

## RCA Analysis:
{rca_context}

## Fix Plan:
{fix_context}

Your task:
- Read the original source file: {affected_file} (start with `read_file`).
- Focus on the bug area (around line {affected_line}) and apply the planned fix.
- Write the full corrected file using `write_file`. Prefer `{patched_filename_hint}` unless the plan specifies another name.
- Provide patch metadata JSON with original_file, patched_file, changes_made, lines_modified.

Write the ENTIRE corrected file content, not just a diff."""
    
    
    agent_executor = create_react_agent(
        model=llm,
        tools=[read_file, write_file, run_terminal_command],
        prompt=PATCH_SYSTEM_PROMPT,
    )
    
    def patch_node(state: dict) -> dict:
        """Execute Patch agent and log everything."""
        
       
        patch_context = shared_memory.get_context_for_agent("patch_agent")
        logger.log_agent_start("Patch_Generation_Agent", {
            "task": "Generate Code Patch",
            "context": {
                "has_rca": patch_context.get("rca") is not None,
                "has_fix_plan": patch_context.get("fix_plan") is not None
            },
            "tools": ["read_file", "write_file"]
        })
        
        start_time = time.time()
        
        
        current_messages = state.get("messages", [])
        if not current_messages or "patch" not in str(current_messages[-1]).lower():
            current_messages.append(HumanMessage(content=task_description))
            state["messages"] = current_messages
        
       
        try:
            result = agent_executor.invoke(state)
        except Exception as e:
            logger.log_error("Patch_Generation_Agent", type(e).__name__, str(e))
            raise
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        
        for msg in result.get("messages", []):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    logger.log_event(
                        agent_name="Patch_Generation_Agent",
                        event_type=EventType.TOOL_CALL,
                        data={
                            "tool_name": tool_call["name"],
                            "arguments": tool_call["args"]
                        }
                    )
            
            
            if hasattr(msg, "type") and msg.type == "tool":
                logger.log_event(
                    agent_name="Patch_Generation_Agent",
                    event_type=EventType.TOOL_RESULT,
                    data={
                        "tool_name": msg.name,
                        "result": str(msg.content)[:2000],
                        "result_truncated": len(str(msg.content)) > 2000
                    }
                )
        
        
        final_content = result["messages"][-1].content if result.get("messages") else ""
        patch_metadata = parse_patch_output(str(final_content))
        
        if patch_metadata:
            
            shared_memory.set_patch_metadata(patch_metadata)
            logger.log_memory_update("Patch_Generation_Agent", "patch_metadata", patch_metadata.to_dict())
        
        
        logger.log_agent_end("Patch_Generation_Agent", {
            "output": str(final_content)[:500] + ("..." if len(str(final_content)) > 500 else ""),
            "success": patch_metadata is not None,
            "duration_ms": duration_ms
        })
        
       
        return {
            "messages": result.get("messages", []),
            "patch_metadata": shared_memory.get_patch_metadata_dict()
        }
    
    return patch_node


async def run_patch_agent(
    llm,
    logger: MessageLogger,
    shared_memory: SharedMemory,
    output_dir: str = "./outputs"
) -> Dict[str, Any]:
    """
    Run the Patch Generation agent and store results in shared memory.
    
    This is a compatibility wrapper for the old interface.
    
    Args:
        llm: LangChain LLM instance
        logger: MessageLogger for capturing interactions
        shared_memory: SharedMemory for reading context and storing patch metadata
        output_dir: Directory to write patched files to
        
    Returns:
        Dictionary with the agent's output and parsed results
    """
    
    node = create_patch_agent_node(llm, logger, shared_memory, output_dir)
    
   
    initial_state = {
        "messages": [],
        "rca": shared_memory.get_rca_dict(),
        "fix_plan": shared_memory.get_fix_plan_dict(),
        "patch_metadata": None,
        "trace_path": "",
        "codebase_path": "",
        "output_dir": output_dir
    }
    
    result_state = node(initial_state)
    
    patch_dict = shared_memory.get_patch_metadata_dict()
    
    return {
        "output": str(result_state.get("messages", [])[-1].content if result_state.get("messages") else ""),
        "parsed": patch_dict,
        "success": patch_dict is not None
    }
