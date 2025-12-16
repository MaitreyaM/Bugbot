

import json
import re
from typing import Any, Dict, Optional
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))

from core.shared_memory import SharedMemory, PatchMetadata
from core.message_logger import MessageLogger
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
- Keep formatting/comments intact; don’t refactor unrelated code.
- Be explicit about what changed and where.
- Return patch metadata as a JSON object: original_file, patched_file, changes_made (list), lines_modified (list)."""


PATCH_TASK_DESCRIPTION = """Generate a patched version of the buggy file based on the following analysis.

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


def create_patch_agent(
    llm_service,
    logger: MessageLogger,
    shared_memory: SharedMemory,
    model_name: str = "gemini-2.0-flash"
):
    """
    Create and configure the Patch Generation Agent.
    
    Args:
        llm_service: The LLM service to use
        logger: MessageLogger for capturing interactions
        shared_memory: SharedMemory to read RCA and fix plan from
        model_name: Name of the LLM model to use
        
    Returns:
        Configured Agent instance
    """
    from clap import Agent
    
  
    rca_dict = shared_memory.get_rca_dict()
    fix_dict = shared_memory.get_fix_plan_dict()
    
    rca_context = json.dumps(rca_dict, indent=2) if rca_dict else "No RCA data available"
    fix_context = json.dumps(fix_dict, indent=2) if fix_dict else "No fix plan available"
    

    affected_file = rca_dict.get("affected_file", "unknown") if rca_dict else "unknown"
    affected_line = rca_dict.get("affected_line", 0) if rca_dict else 0
    patched_filename_hint = f"fixed_{Path(affected_file).name}" if affected_file not in ("", "unknown", None) else "fixed_patch.py"
    
   
    agent = Agent(
        name="Patch_Generation_Agent",
        backstory=PATCH_SYSTEM_PROMPT,
        task_description=PATCH_TASK_DESCRIPTION.format(
            rca_context=rca_context,
            fix_context=fix_context,
            affected_file=affected_file,
            affected_line=affected_line,
            patched_filename_hint=patched_filename_hint
        ),
        task_expected_output="A complete patched file saved to outputs/ and patch metadata in JSON format",
        llm_service=llm_service,
        model=model_name,
        tools=[read_file, write_file, run_terminal_command],
        parallel_tool_calls=False
    )
    
    return agent


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


async def run_patch_agent(
    llm_service,
    logger: MessageLogger,
    shared_memory: SharedMemory,
    model_name: str = "gemini-2.0-flash"
) -> Dict[str, Any]:
    """
    Run the Patch Generation agent and store results in shared memory.
    
    Args:
        llm_service: The LLM service to use
        logger: MessageLogger for capturing interactions
        shared_memory: SharedMemory for reading context and storing patch metadata
        model_name: Name of the LLM model to use
        
    Returns:
        Dictionary with the agent's output and parsed results
    """
  
    patch_context = shared_memory.get_context_for_agent("patch_agent")
    
 
    logger.log_agent_start("Patch_Generation_Agent", {
        "task": "Generate Code Patch",
        "context": {
            "has_rca": patch_context.get("rca") is not None,
            "has_fix_plan": patch_context.get("fix_plan") is not None
        },
        "tools": ["read_file", "write_file"]
    })
    
    try:
       
        agent = create_patch_agent(llm_service, logger, shared_memory, model_name)
        
        import time
        start_time = time.time()
        
        result = await agent.run()
        
        duration_ms = int((time.time() - start_time) * 1000)
        
       
        output = result.get("output", "") if isinstance(result, dict) else str(result)
        
       
        patch_metadata = parse_patch_output(output)
        
        if patch_metadata:
         
            shared_memory.set_patch_metadata(patch_metadata)
            logger.log_memory_update("Patch_Generation_Agent", "patch_metadata", patch_metadata.to_dict())
        
     
        logger.log_agent_end("Patch_Generation_Agent", {
            "output": output[:500] + "..." if len(output) > 500 else output,
            "success": patch_metadata is not None,
            "duration_ms": duration_ms
        })
        
        return {
            "output": output,
            "parsed": patch_metadata.to_dict() if patch_metadata else None,
            "success": patch_metadata is not None
        }
        
    except Exception as e:
        logger.log_error("Patch_Generation_Agent", type(e).__name__, str(e))
        raise

