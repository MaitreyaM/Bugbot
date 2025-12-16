

import asyncio
import argparse
import sys
import os
from pathlib import Path
from datetime import datetime


sys.path.insert(0, str(Path(__file__).parent))

from config import (
    GOOGLE_API_KEY, 
    GROQ_API_KEY,
    LLM_MODEL,
    LLM_PROVIDER,
    GOOGLE_MODEL,
    GROQ_MODEL,
    CODEBASE_PATH, 
    ERROR_TRACE_PATH, 
    OUTPUT_DIR,
    validate_config
)
from core.shared_memory import SharedMemory
from core.message_logger import MessageLogger
from agents.rca_agent import run_rca_agent
from agents.fix_agent import run_fix_agent
from agents.patch_agent import run_patch_agent


def get_llm_service():
    """
    Initialize the appropriate LLM service based on LLM_PROVIDER env var.
    
    LLM_PROVIDER options:
    - "google": Use Google Gemini only
    - "groq": Use Groq only  
    - "auto": Try Google first, fall back to Groq (default)
    
    Returns:
        Tuple of (LLM service instance, model name to use)
    """
    from clap import GroqService
    
 
    if LLM_PROVIDER == "groq":
        if not GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY required when LLM_PROVIDER=groq")
        print(f"Using Groq LLM service (model: {GROQ_MODEL})")
        return GroqService(), GROQ_MODEL
    
   
    if LLM_PROVIDER == "google":
        if not GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY required when LLM_PROVIDER=google")
        from clap import GoogleOpenAICompatService
        print(f"Using Google Gemini LLM service (model: {GOOGLE_MODEL})")
        return GoogleOpenAICompatService(api_key=GOOGLE_API_KEY), GOOGLE_MODEL
    
  
    if GOOGLE_API_KEY:
        try:
            from clap import GoogleOpenAICompatService
            print(f"Using Google Gemini LLM service (model: {GOOGLE_MODEL})")
            return GoogleOpenAICompatService(api_key=GOOGLE_API_KEY), GOOGLE_MODEL
        except Exception as e:
            print(f"Google service unavailable ({e}), trying Groq...")
    
    if GROQ_API_KEY:
        print(f"Using Groq LLM service (model: {GROQ_MODEL})")
        return GroqService(), GROQ_MODEL
    
    raise ValueError("No LLM service available. Set GOOGLE_API_KEY or GROQ_API_KEY")


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
    
    
    llm_service, model_name = get_llm_service()
    
    results = {
        "rca": None,
        "fix": None,
        "patch": None,
        "success": False
    }
    
    try:
       
        print("\n" + "-" * 40)
        print("PHASE 1: Root Cause Analysis")
        print("-" * 40)
        
        rca_result = await run_rca_agent(
            llm_service=llm_service,
            logger=logger,
            shared_memory=shared_memory,
            trace_path=str(trace_path),
            model_name=model_name
        )
        results["rca"] = rca_result
        
        if not rca_result or not rca_result.get("success"):
            print("Warning: RCA parsing may have issues, continuing anyway...")
        
        error_type = "Unknown"
        parsed_rca = rca_result.get("parsed") if rca_result else None
        if parsed_rca:
            error_type = parsed_rca.get("error_type", "Unknown")
        print(f"RCA Complete. Root cause identified: {error_type}")
      
        print("\n" + "-" * 40)
        print("PHASE 2: Fix Suggestion")
        print("-" * 40)
        
        fix_result = await run_fix_agent(
            llm_service=llm_service,
            logger=logger,
            shared_memory=shared_memory,
            model_name=model_name
        )
        results["fix"] = fix_result
        
        if not fix_result or not fix_result.get("success"):
            print("Warning: Fix plan parsing may have issues, continuing anyway...")
        
        steps_count = 0
        parsed_fix = fix_result.get("parsed") if fix_result else None
        if parsed_fix:
            steps_count = len(parsed_fix.get("steps", []))
        print(f"Fix Plan Complete. Steps: {steps_count}")
        
    
        print("\n" + "-" * 40)
        print("PHASE 3: Patch Generation")
        print("-" * 40)
        
        patch_result = await run_patch_agent(
            llm_service=llm_service,
            logger=logger,
            shared_memory=shared_memory,
            model_name=model_name
        )
        results["patch"] = patch_result
        
        if not patch_result or not patch_result.get("success"):
            print("Warning: Patch metadata parsing may have issues...")
        
        patched_file = "Unknown"
        parsed_patch = patch_result.get("parsed") if patch_result else None
        if parsed_patch:
            patched_file = parsed_patch.get("patched_file", "Unknown")
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
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Multi-Agent RCA + Fix System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python main.py
    python main.py --trace ../trace_1.json --codebase ../fastapi-project
    python main.py --output ./my_outputs
        """
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
    
  
    try:
        validate_config()
    except ValueError as e:
        print(f"Configuration Error: {e}")
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

