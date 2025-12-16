

import os
from pathlib import Path
from typing import Optional
import sys


sys.path.insert(0, str(Path(__file__).parent.parent))

from config import MAX_FILE_SIZE_BYTES, ALLOWED_READ_EXTENSIONS, OUTPUT_DIR, CODEBASE_PATH



from langchain_core.tools import tool



def _validate_path(path: str, allow_absolute: bool = True) -> Path:
    
    if not path or not path.strip():
        raise ValueError("Path cannot be empty")
    
    
    normalized = Path(path).resolve()
    
   
    try:
        path_str = str(normalized)
        if ".." in path:
            pass  
    except Exception as e:
        raise ValueError(f"Invalid path: {e}")
    
    return normalized


def _is_path_within_allowed(path: Path, allowed_roots: list) -> bool:
    """Check if a path is within any of the allowed root directories."""
    path_resolved = path.resolve()
    for root in allowed_roots:
        try:
            root_resolved = Path(root).resolve()
            path_resolved.relative_to(root_resolved)
            return True
        except ValueError:
            continue
    return False


@tool
def read_file(file_path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
    """
    Read the contents of a file from the codebase, optionally for a specific line range.
    
    
    Args:
        file_path: Path to the file to read (relative to codebase or absolute)
        start_line: Optional 1-based start line (inclusive)
        end_line: Optional 1-based end line (inclusive)
        
    Returns:
        The contents of the file as a string, or an error message if the file
        cannot be read. When a range is provided, only that slice is returned.
    """
    try:
       
        original_path = file_path
        if file_path.startswith("/usr/srv/app/"):
            
            local_path = file_path.replace("/usr/srv/app/", "")
            file_path = local_path
        
        
        path = Path(file_path)
        
       
        candidates = []
        
        if path.is_absolute():
            candidates.append(path)
        else:
            # Try various combinations
            candidates.extend([
                CODEBASE_PATH / "app" / file_path,  
                CODEBASE_PATH / file_path,         
                Path(file_path),                   
            ])
            
            
            if any(file_path.startswith(d) for d in ["services/", "models/", "routes/", "config/", "utils/"]):
                candidates.insert(0, CODEBASE_PATH / "app" / file_path)
        
        resolved_path = None
        for candidate in candidates:
            try:
                if candidate.exists():
                    resolved_path = candidate.resolve()
                    break
            except Exception:
                continue
        
        if resolved_path is None:
            return f"Error: File not found. Original path: {original_path}\nSearched in:\n" + "\n".join(f"  - {c}" for c in candidates)
        
        
        if not resolved_path.exists():
            return f"Error: File does not exist: {resolved_path}"
        
        if not resolved_path.is_file():
            return f"Error: Path is not a file: {resolved_path}"
        
        
        file_size = resolved_path.stat().st_size
        if file_size > MAX_FILE_SIZE_BYTES:
            return f"Error: File too large ({file_size} bytes). Maximum allowed: {MAX_FILE_SIZE_BYTES} bytes"
        
        
        if resolved_path.suffix.lower() not in ALLOWED_READ_EXTENSIONS:
            return f"Error: File type not allowed. Allowed types: {', '.join(ALLOWED_READ_EXTENSIONS)}"
        
    
        if start_line is not None and start_line < 1:
            return "Error: start_line must be >= 1"
        if end_line is not None and end_line < 1:
            return "Error: end_line must be >= 1"
        if start_line is not None and end_line is not None and start_line > end_line:
            return "Error: start_line cannot be greater than end_line"

       
        try:
            with open(resolved_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
         
            try:
                with open(resolved_path, "r", encoding="latin-1") as f:
                    content = f.read()
            except Exception as e:
                return f"Error: Could not decode file contents: {e}"
        
       
        lines = content.split("\n")
        total_lines = len(lines)

       
        start_idx = (start_line - 1) if start_line else 0
        end_idx = end_line if end_line else total_lines

    
        start_idx = max(0, min(start_idx, total_lines))
        end_idx = max(start_idx, min(end_idx, total_lines))

        # Hard cap displayed lines to avoid overwhelming the LLM
        MAX_DISPLAY_LINES = 800
        if end_idx - start_idx > MAX_DISPLAY_LINES:
            end_idx = start_idx + MAX_DISPLAY_LINES
            truncated_note = f"\n\n[Truncated to {MAX_DISPLAY_LINES} lines to keep output concise]"
        else:
            truncated_note = ""

        selected_lines = lines[start_idx:end_idx]
        numbered_content = "\n".join(f"{i + start_idx + 1:4d} | {line}" for i, line in enumerate(selected_lines))
        
        range_info = ""
        if start_line or end_line:
            range_info = f" (showing lines {start_idx + 1}-{end_idx} of {total_lines})"
        
        return f"File: {resolved_path}\nSize: {file_size} bytes\nLines: {total_lines}{range_info}\n\n{numbered_content}{truncated_note}"
        
    except Exception as e:
        return f"Error reading file: {type(e).__name__}: {e}"


@tool
def write_file(file_path: str, content: str) -> str:
    """
    Write content to a new file in the outputs directory.
    
    Use this tool to create the patched/fixed version of a source file.
    For safety, files can only be written to the outputs directory.
    The file will be created with the name 'fixed_<original_name>'.
    
    Args:
        file_path: Name for the output file (will be created in outputs/)
        content: The content to write to the file
        
    Returns:
        Success message with the path to the created file, or an error message.
    """
    try:
       
        if not content or not content.strip():
            return "Error: Content cannot be empty"
        
       
        filename = Path(file_path).name
        if not filename:
            return "Error: Invalid filename"
        
       
        output_path = OUTPUT_DIR / filename
        
       
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
    
        if output_path.exists():
           
            import time
            timestamp = int(time.time())
            backup_path = OUTPUT_DIR / f"{filename}.backup_{timestamp}"
            output_path.rename(backup_path)
        
       
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        
      
        written_size = output_path.stat().st_size
        line_count = content.count("\n") + 1
        
        return f"Success: File written to {output_path}\nSize: {written_size} bytes\nLines: {line_count}"
        
    except PermissionError:
        return f"Error: Permission denied writing to {output_path}"
    except Exception as e:
        return f"Error writing file: {type(e).__name__}: {e}"


@tool
def list_directory(dir_path: str) -> str:
    """
    List the contents of a directory in the codebase.
    
    Use this tool to explore the structure of the codebase and find
    relevant files. Returns a hierarchical listing of files and subdirectories.
    
    Args:
        dir_path: Path to the directory to list (relative to codebase or absolute)
        
    Returns:
        A formatted listing of directory contents, or an error message.
    """
    try:
       
        original_path = dir_path
        if dir_path.startswith("/usr/srv/app/"):
            dir_path = dir_path.replace("/usr/srv/app/", "")
        
       
        path = Path(dir_path)
        
       
        candidates = []
        if path.is_absolute():
            candidates.append(path)
        else:
            candidates.extend([
                CODEBASE_PATH / "app" / dir_path,
                CODEBASE_PATH / dir_path,
                Path(dir_path),
            ])
        
        resolved_path = None
        for candidate in candidates:
            try:
                if candidate.exists() and candidate.is_dir():
                    resolved_path = candidate.resolve()
                    break
            except Exception:
                continue
        
        if resolved_path is None:
            return f"Error: Directory not found. Original: {original_path}\nSearched:\n" + "\n".join(f"  - {c}" for c in candidates)
        
    
        items = []
        try:
            for item in sorted(resolved_path.iterdir()):
                if item.name.startswith("."):
                    continue  
                    
                if item.is_dir():
                    items.append(f"  [DIR]  {item.name}/")
                else:
                    size = item.stat().st_size
                    items.append(f"  [FILE] {item.name} ({size} bytes)")
        except PermissionError:
            return f"Error: Permission denied accessing {resolved_path}"
        
        if not items:
            return f"Directory is empty: {resolved_path}"
        
        output = f"Directory: {resolved_path}\nTotal items: {len(items)}\n\n"
        output += "\n".join(items)
        
        return output
        
    except Exception as e:
        return f"Error listing directory: {type(e).__name__}: {e}"
