

import asyncio
import argparse
import sys
import os
from pathlib import Path
from datetime import datetime


sys.path.insert(0, str(Path(__file__).parent))

from langgraph.graph import StateGraph, START, END

from graph_state import RCAGraphState
from config import (
    CODEBASE_PATH, 
    ERROR_TRACE_PATH, 
    OUTPUT_DIR,
)
from core.shared_memory import SharedMemory
from core.message_logger import MessageLogger
from llm_provider import get_llm_for_provider
from agents.rca_agent import create_rca_agent_node
from agents.fix_agent import create_fix_agent_node
from agents.patch_agent import create_patch_agent_node


async def run_rca_pipeline(
    trace_path: str,
    codebase_path: str,
    output_dir: str
) -> dict:
    
    print("\n" + "=" * 60)
    print("MULTI-AGENT RCA + FIX SYSTEM")
    print("=" * 60)
    print(f"Start Time: {datetime.now().isoformat()}")
    print(f"Error Trace: {trace_path}")
    print(f"Codebase: {codebase_path}")
    print(f"Output Dir: {output_dir}")
    print("=" * 60 + "\n")
    
    
    shared_memory = SharedMemory()
    logger = MessageLogger()
    
    
    logger.log_system("Pipeline started", {
        "trace_path": str(trace_path),
        "codebase_path": str(codebase_path),
        "output_dir": str(output_dir)
    })
    
   
    try:
        llm = get_llm_for_provider()
    except ValueError as e:
        print(f"Configuration Error: {e}")
        sys.exit(1)
    
    results = {
        "rca": None,
        "fix": None,
        "patch": None,
        "success": False
    }
    
    try:
       
        workflow = StateGraph(RCAGraphState)
        
    
        workflow.add_node(
            "rca_agent",
            create_rca_agent_node(llm, logger, shared_memory, trace_path)
        )
        workflow.add_node(
            "fix_agent", 
            create_fix_agent_node(llm, logger, shared_memory)
        )
        workflow.add_node(
            "patch_agent",
            create_patch_agent_node(llm, logger, shared_memory, output_dir)
        )
        
       
        workflow.add_edge(START, "rca_agent")
        workflow.add_edge("rca_agent", "fix_agent")
        workflow.add_edge("fix_agent", "patch_agent")
        workflow.add_edge("patch_agent", END)
        
      
        graph = workflow.compile()
        
      
        
     
        initial_state = {
            "messages": [],
            "rca": None,
            "fix_plan": None,
            "patch_metadata": None,
            "trace_path": trace_path,
            "codebase_path": codebase_path,
            "output_dir": output_dir,
        }
        
     
        print("\n" + "-" * 40)
        print("PHASE 1: Root Cause Analysis")
        print("-" * 40)
        
     
        final_state = await graph.ainvoke(initial_state)
        
       
        rca_data = shared_memory.get_rca_dict()
        results["rca"] = {"parsed": rca_data, "success": rca_data is not None}
        
        if not rca_data:
            print("Warning: RCA parsing may have issues, continuing anyway...")
        
        error_type = "Unknown"
        if rca_data:
            error_type = rca_data.get("error_type", "Unknown")
        print(f"RCA Complete. Root cause identified: {error_type}")
        

        print("\n" + "-" * 40)
        print("PHASE 2: Fix Suggestion")
        print("-" * 40)
        
    
        fix_data = shared_memory.get_fix_plan_dict()
        results["fix"] = {"parsed": fix_data, "success": fix_data is not None}
        
        if not fix_data:
            print("Warning: Fix plan parsing may have issues, continuing anyway...")
        
        steps_count = 0
        if fix_data:
            steps_count = len(fix_data.get("steps", []))
        print(f"Fix Plan Complete. Steps: {steps_count}")
        
 
        print("\n" + "-" * 40)
        print("PHASE 3: Patch Generation")
        print("-" * 40)
        
      
        patch_data = shared_memory.get_patch_metadata_dict()
        results["patch"] = {"parsed": patch_data, "success": patch_data is not None}
        
        if not patch_data:
            print("Warning: Patch metadata parsing may have issues...")
        
        patched_file = "Unknown"
        if patch_data:
            patched_file = patch_data.get("patched_file", "Unknown")
        print(f"Patch Complete. File: {patched_file}")
        
        results["success"] = True
        
    except Exception as e:
        print(f"\nError during pipeline execution: {type(e).__name__}: {e}")
        logger.log_error("Pipeline", type(e).__name__, str(e))
        import traceback
        traceback.print_exc()
    
    finally:
     
        print("\n" + "-" * 40)
        print("SAVING OUTPUTS")
        print("-" * 40)
        
     
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
     
        shared_memory_path = output_path / "shared_memory.json"
        shared_memory.save(str(shared_memory_path))
        print(f"Shared Memory saved to: {shared_memory_path}")
        
     
        message_history_path = output_path / "message_history.json"
        logger.log_system("Pipeline completed", {"success": results["success"]})
        logger.save(str(message_history_path))
        print(f"Message History saved to: {message_history_path}")
        
     
        patch_meta = shared_memory.get_patch_metadata_dict()
        patch_file = None
        if patch_meta and patch_meta.get("patched_file"):
            patch_file = Path(patch_meta["patched_file"])
            if not patch_file.is_absolute():
                patch_file = output_path / patch_file
        else:
            candidates = list(output_path.glob("fixed_*"))
            if candidates:
                patch_file = candidates[0]

        if patch_file and patch_file.exists():
            print(f"Patch File created: {patch_file}")
        else:
            print("Warning: Patch file was not created")
    

    print("\n" + "=" * 60)
    print("PIPELINE SUMMARY")
    print("=" * 60)
    
    rca_data = shared_memory.get_rca_dict()
    fix_data = shared_memory.get_fix_plan_dict()
    patch_data = shared_memory.get_patch_metadata_dict()
    
    if rca_data:
        print(f"\nRCA Results:")
        print(f"  Error Type: {rca_data.get('error_type', 'Unknown')}")
        print(f"  Error Message: {rca_data.get('error_message', 'Unknown')}")
        print(f"  Affected File: {rca_data.get('affected_file', 'Unknown')}")
        print(f"  Affected Line: {rca_data.get('affected_line', 'Unknown')}")
        print(f"  Root Cause: {rca_data.get('root_cause', 'Unknown')[:100]}...")
    
    if fix_data:
        print(f"\nFix Plan:")
        print(f"  Description: {fix_data.get('description', 'Unknown')[:100]}...")
        print(f"  Steps: {len(fix_data.get('steps', []))}")
        print(f"  Safety Considerations: {len(fix_data.get('safety_considerations', []))}")
    
    if patch_data:
        print(f"\nPatch Metadata:")
        print(f"  Original File: {patch_data.get('original_file', 'Unknown')}")
        print(f"  Patched File: {patch_data.get('patched_file', 'Unknown')}")
        print(f"  Changes Made: {len(patch_data.get('changes_made', []))}")
    
    print("\n" + "=" * 60)
    print(f"End Time: {datetime.now().isoformat()}")
    print(f"Overall Success: {results['success']}")
    print("=" * 60 + "\n")
    
    return results


def main():
    
    parser = argparse.ArgumentParser(
        description="Multi-Agent RCA + Fix System (LangGraph)",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--trace",
        type=str,
        default=str(ERROR_TRACE_PATH),
        help=f"Path to error trace JSON file (default: {ERROR_TRACE_PATH})"
    )
    
    parser.add_argument(
        "--codebase",
        type=str,
        default=str(CODEBASE_PATH),
        help=f"Path to codebase directory (default: {CODEBASE_PATH})"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        default=str(OUTPUT_DIR),
        help=f"Path to output directory (default: {OUTPUT_DIR})"
    )
    
    args = parser.parse_args()
    
   
    if not Path(args.trace).exists():
        print(f"Error: Trace file not found: {args.trace}")
        sys.exit(1)
    
    if not Path(args.codebase).exists():
        print(f"Error: Codebase directory not found: {args.codebase}")
        sys.exit(1)
    
   
    try:
        results = asyncio.run(run_rca_pipeline(
            trace_path=args.trace,
            codebase_path=args.codebase,
            output_dir=args.output
        ))
        
        sys.exit(0 if results.get("success") else 1)
        
    except KeyboardInterrupt:
        print("\nPipeline interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
