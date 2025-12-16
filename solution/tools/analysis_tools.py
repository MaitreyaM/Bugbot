
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import sys


sys.path.insert(0, str(Path(__file__).parent.parent))

from config import ERROR_TRACE_PATH


from langchain_core.tools import tool


def _extract_stack_frames(stack_details: str) -> List[Dict[str, Any]]:
    
    try:
        frames = json.loads(stack_details)
        return frames if isinstance(frames, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _filter_internal_frames(frames: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    
    internal_frames = []
    for frame in frames:
        is_external = frame.get("exception.is_file_external", "true")
        if is_external == "false" or is_external is False:
            internal_frames.append(frame)
    return internal_frames


def _format_frame(frame: Dict[str, Any]) -> str:
    """Format a single stack frame for readable output."""
    file_path = frame.get("exception.file", "unknown")
    line_num = frame.get("exception.line", "?")
    func_name = frame.get("exception.function_name", "unknown")
    func_body = frame.get("exception.function_body", "")
    
    output = f"""
File: {file_path}
Line: {line_num}
Function: {func_name}
Code:
{func_body}
"""
    return output.strip()


@tool
def parse_error_trace(trace_path: str) -> str:
    """
    Parse a JSON error trace file and extract key information for analysis.
    
    This tool reads an APM error trace file and extracts:
    - Error type and message
    - Stack trace with file locations
    - Internal (application) code frames vs external (library) frames
    - Function bodies where the error occurred
    
    Use this as the first step in root cause analysis to understand
    what error occurred and where in the code it happened.
    
    Args:
        trace_path: Path to the JSON error trace file
        
    Returns:
        A formatted summary of the error trace with all relevant details
        for debugging, or an error message if parsing fails.
    """
    try:
       
        path = Path(trace_path)
        if not path.is_absolute():
            
            if not path.exists():
                path = ERROR_TRACE_PATH
        
        if not path.exists():
            return f"Error: Trace file not found at {path}"
        
        
        with open(path, "r", encoding="utf-8") as f:
            trace_data = json.load(f)
        
        
        if isinstance(trace_data, list):
            if len(trace_data) == 0:
                return "Error: Trace file contains empty array"
            trace_data = trace_data[0]  
        
      
        event_attrs = trace_data.get("event_attributes", {})
        
       
        error_type = event_attrs.get("exception.type", "Unknown")
        error_message = event_attrs.get("exception.message", "No message")
        error_language = event_attrs.get("exception.language", "unknown")
        full_stacktrace = event_attrs.get("exception.stacktrace", "")
        
        
        stack_details_str = event_attrs.get("exception.stack_details", "[]")
        all_frames = _extract_stack_frames(stack_details_str)
        internal_frames = _filter_internal_frames(all_frames)
        
       
        output_parts = [
            "=" * 60,
            "ERROR TRACE ANALYSIS",
            "=" * 60,
            "",
            f"Error Type: {error_type}",
            f"Error Message: {error_message}",
            f"Language: {error_language}",
            f"Event: {trace_data.get('event_name', 'unknown')}",
            "",
            "-" * 40,
            "INTERNAL APPLICATION FRAMES (Your Code):",
            "-" * 40,
        ]
        
        if internal_frames:
            for i, frame in enumerate(internal_frames, 1):
                output_parts.append(f"\n--- Frame {i} ---")
                output_parts.append(_format_frame(frame))
        else:
            output_parts.append("No internal frames found (error may be in library code)")
        
        
        if internal_frames:
            primary_frame = internal_frames[0]
            output_parts.extend([
                "",
                "-" * 40,
                "PRIMARY ERROR LOCATION:",
                "-" * 40,
                f"File: {primary_frame.get('exception.file', 'unknown')}",
                f"Line: {primary_frame.get('exception.line', 'unknown')}",
                f"Function: {primary_frame.get('exception.function_name', 'unknown')}",
            ])
        
       
        output_parts.extend([
            "",
            "-" * 40,
            "FULL STACKTRACE:",
            "-" * 40,
            full_stacktrace[:2000] + ("... [truncated]" if len(full_stacktrace) > 2000 else ""),
        ])
        
      
        output_parts.extend([
            "",
            "=" * 60,
            "SUMMARY FOR RCA:",
            "=" * 60,
            f"- Error: {error_type}: {error_message}",
            f"- Total stack frames: {len(all_frames)}",
            f"- Internal (app) frames: {len(internal_frames)}",
        ])
        
        if internal_frames:
            primary = internal_frames[0]
            output_parts.append(f"- Primary location: {primary.get('exception.file', 'unknown')}:{primary.get('exception.line', '?')}")
        
        return "\n".join(output_parts)
        
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON in trace file: {e}"
    except KeyError as e:
        return f"Error: Missing expected field in trace: {e}"
    except Exception as e:
        return f"Error parsing trace file: {type(e).__name__}: {e}"

