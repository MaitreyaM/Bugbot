

import json
import re
import time
from typing import Any, Dict, Optional

from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

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


def parse_fix_output(output: str) -> Optional[FixPlan]:
    
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


def create_fix_agent_node(
    llm,
    logger: MessageLogger,
    shared_memory: SharedMemory
):
   
    

    rca_dict = shared_memory.get_rca_dict()
    rca_context = json.dumps(rca_dict, indent=2) if rca_dict else "No RCA data available"
    
    
    task_description = f"""Based on the RCA analysis, generate a detailed fix plan.

    RCA input:
    {rca_context}

    Your task:
    - Reflect the RCA's root cause.
    - Propose the smallest viable change set to fix it.
    - Include safety/edge-case considerations and testing notes.
    - Return one JSON object: description, steps[], safety_considerations[], expected_outcome."""
    
   
    agent_executor = create_react_agent(
        model=llm,
        tools=[],  
        prompt=FIX_SYSTEM_PROMPT,
    )
    
    def fix_node(state: dict) -> dict:
        """Execute Fix agent and log everything."""
        
       
        rca_context = shared_memory.get_context_for_agent("fix_agent")
        logger.log_agent_start("Fix_Suggestion_Agent", {
            "task": "Generate Fix Plan",
            "context": {"has_rca": rca_context.get("rca") is not None},
            "tools": []
        })
        
        start_time = time.time()
        
       
        current_messages = state.get("messages", [])
        if not current_messages or "fix plan" not in str(current_messages[-1]).lower():
            current_messages.append(HumanMessage(content=task_description))
            state["messages"] = current_messages
        
        
        try:
            result = agent_executor.invoke(state)
        except Exception as e:
            logger.log_error("Fix_Suggestion_Agent", type(e).__name__, str(e))
            raise
        
        duration_ms = int((time.time() - start_time) * 1000)
        
       
        final_content = result["messages"][-1].content if result.get("messages") else ""
        fix_plan = parse_fix_output(str(final_content))
        
        if fix_plan:
          
            shared_memory.set_fix_plan(fix_plan)
            logger.log_memory_update("Fix_Suggestion_Agent", "fix_plan", fix_plan.to_dict())
        
       
        logger.log_agent_end("Fix_Suggestion_Agent", {
            "output": str(final_content)[:500] + ("..." if len(str(final_content)) > 500 else ""),
            "success": fix_plan is not None,
            "duration_ms": duration_ms
        })
        
      
        return {
            "messages": result.get("messages", []),
            "fix_plan": shared_memory.get_fix_plan_dict()
        }
    
    return fix_node


async def run_fix_agent(
    llm,
    logger: MessageLogger,
    shared_memory: SharedMemory
) -> Dict[str, Any]:
    
    node = create_fix_agent_node(llm, logger, shared_memory)
    
  
    initial_state = {
        "messages": [],
        "rca": shared_memory.get_rca_dict(),
        "fix_plan": None,
        "patch_metadata": None,
        "trace_path": "",
        "codebase_path": "",
        "output_dir": ""
    }
    
    result_state = node(initial_state)
    
    fix_dict = shared_memory.get_fix_plan_dict()
    
    return {
        "output": str(result_state.get("messages", [])[-1].content if result_state.get("messages") else ""),
        "parsed": fix_dict,
        "success": fix_dict is not None
    }
