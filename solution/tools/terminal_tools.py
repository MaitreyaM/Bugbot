

import os
import subprocess
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).parent.parent))

from config import PROJECT_ROOT
from langchain_core.tools import tool


DEFAULT_WORKSPACE = PROJECT_ROOT


@tool
def run_terminal_command(command: str) -> str:
    """
    Run a shell command in the project workspace and return its output.

    Args:
        command: The shell command to run .

    Returns:
        Combined stdout/stderr from the command, or an error description.
    """
    try:
        if not command or not command.strip():
            return "Error: command cannot be empty"

        
        os.makedirs(DEFAULT_WORKSPACE, exist_ok=True)

        result = subprocess.run(
            command,
            shell=True,
            cwd=str(DEFAULT_WORKSPACE),
            capture_output=True,
            text=True,
            timeout=30,
        )

        output = result.stdout or ""
        error = result.stderr or ""
        if result.returncode != 0:
            return f"Command exited with code {result.returncode}.\nSTDOUT:\n{output}\nSTDERR:\n{error}"

        return output if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: command timed out after 30 seconds"
    except Exception as e:
        return f"Error running command: {type(e).__name__}: {e}"


