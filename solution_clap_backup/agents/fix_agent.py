

import json
import re
from typing import Any, Dict, Optional
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))

from core.shared_memory import SharedMemory, FixPlan
from core.message_logger import MessageLogger



FIX_SYSTEM_PROMPT = """You are a senior software architect for safe, minimal code fixes.

Goal: turn the RCA into a clear, actionable fix plan.

Principles:
- Minimal change surface; avoid refactors.
- Safety first: edge cases, side effects, backward compatibility.
- Clear, numbered steps that can be executed exactly.
- Testing implications included.

Output: one JSON object with description, steps[], safety_considerations[], expected_outcome."""


FIX_TASK_DESCRIPTION = """Based on the RCA analysis, generate a detailed fix plan.

RCA input:
{rca_context}

Your task:
- Reflect the RCA’s root cause.
- Propose the smallest viable change set to fix it.
- Include safety/edge-case considerations and testing notes.
- Return one JSON object: description, steps[], safety_considerations[], expected_outcome."""


def create_fix_agent(
    llm_service,
    logger: MessageLogger,
    shared_memory: SharedMemory,
    model_name: str = "gemini-2.0-flash"
):
    """
    Create and configure the Fix Suggestion Agent.
    
    Args:
        llm_service: The LLM service to use
        logger: MessageLogger for capturing interactions
        shared_memory: SharedMemory to read RCA results from
        model_name: Name of the LLM model to use
        
    Returns:
        Configured Agent instance
    """
    from clap import Agent
    
    
    rca_dict = shared_memory.get_rca_dict()
    rca_context = json.dumps(rca_dict, indent=2) if rca_dict else "No RCA data available"
    
    
    agent = Agent(
        name="Fix_Suggestion_Agent",
        backstory=FIX_SYSTEM_PROMPT,
        task_description=FIX_TASK_DESCRIPTION.format(rca_context=rca_context),
        task_expected_output="A structured JSON fix plan with steps and safety considerations",
        llm_service=llm_service,
        model=model_name,
        tools=[],  
        parallel_tool_calls=False
    )
    
    return agent


def parse_fix_output(output: str) -> Optional[FixPlan]:
    """
    Parse the Fix agent's output to extract structured data.
    
    Args:
        output: Raw output string from the Fix agent
        
    Returns:
        FixPlan object if parsing succeeds, None otherwise
    """
    try:
       
        json_match = re.search(r'\{[^{}]*"description"[^{}]*\}', output, re.DOTALL)
        if not json_match:
            
            json_match = re.search(r'\{[\s\S]*?"steps"[\s\S]*?\][\s\S]*?\}', output)
        
        if json_match:
            json_str = json_match.group()
            
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
                
                start_idx = output.find('{"description"')
                if start_idx == -1:
                    start_idx = output.find('{\n    "description"')
                if start_idx == -1:
                    start_idx = output.find('{\n  "description"')
                
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
            
            return FixPlan(
                description=data.get("description", ""),
                steps=data.get("steps", []),
                safety_considerations=data.get("safety_considerations", []),
                expected_outcome=data.get("expected_outcome", "")
            )
        
       
        description_match = re.search(r'(?:Description|description)[:\s]+(.+?)(?:\n|$)', output)
        
        if description_match:
            return FixPlan(
                description=description_match.group(1),
                steps=["Manual parsing required - see raw output"],
                safety_considerations=[],
                expected_outcome="Review raw output for details"
            )
        
        return None
        
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        print(f"Error parsing Fix output: {e}")
        return None


async def run_fix_agent(
    llm_service,
    logger: MessageLogger,
    shared_memory: SharedMemory,
    model_name: str = "gemini-2.0-flash"
) -> Dict[str, Any]:
    """
    Run the Fix Suggestion agent and store results in shared memory.
    
    Args:
        llm_service: The LLM service to use
        logger: MessageLogger for capturing interactions
        shared_memory: SharedMemory for reading RCA and storing fix plan
        model_name: Name of the LLM model to use
        
    Returns:
        Dictionary with the agent's output and parsed results
    """
    
    rca_context = shared_memory.get_context_for_agent("fix_agent")
    
    
    logger.log_agent_start("Fix_Suggestion_Agent", {
        "task": "Generate Fix Plan",
        "context": {"has_rca": rca_context.get("rca") is not None},
        "tools": []
    })
    
    try:
        
        agent = create_fix_agent(llm_service, logger, shared_memory, model_name)
        
        import time
        start_time = time.time()
        
        result = await agent.run()
        
        duration_ms = int((time.time() - start_time) * 1000)
        
       
        output = result.get("output", "") if isinstance(result, dict) else str(result)
        
        
        fix_plan = parse_fix_output(output)
        
        if fix_plan:
         
            shared_memory.set_fix_plan(fix_plan)
            logger.log_memory_update("Fix_Suggestion_Agent", "fix_plan", fix_plan.to_dict())
        
      
        logger.log_agent_end("Fix_Suggestion_Agent", {
            "output": output[:500] + "..." if len(output) > 500 else output,
            "success": fix_plan is not None,
            "duration_ms": duration_ms
        })
        
        return {
            "output": output,
            "parsed": fix_plan.to_dict() if fix_plan else None,
            "success": fix_plan is not None
        }
        
    except Exception as e:
        logger.log_error("Fix_Suggestion_Agent", type(e).__name__, str(e))
        raise

