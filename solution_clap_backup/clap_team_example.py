"""
Experimental Clap-Agents Team setup for the RCA → Fix → Patch workflow.

This file DOES NOT affect the main production pipeline in `main.py`.
It is meant to demonstrate using Clap's `Team` and `Agent` patterns
directly, similar to the examples in the clap-agents repo.

Usage (from solution/):
    LLM_PROVIDER=groq python clap_team_example.py
"""

import asyncio
from pathlib import Path

from dotenv import load_dotenv

from clap import Team, Agent, GroqService

from tools import (
    parse_error_trace,
    read_file,
    write_file,
    list_directory,
    run_terminal_command,
)
from config import ERROR_TRACE_PATH


load_dotenv()


async def run_rca_fix_patch_team() -> None:
    
    llm_service = GroqService()
    model = "meta-llama/llama-4-scout-17b-16e-instruct"

    trace_path = str(ERROR_TRACE_PATH)

    with Team() as team:
     
        rca_agent = Agent(
            name="RCA_Agent_Team",
            backstory=(
                "You analyze Python/FastAPI/SQLAlchemy errors. "
                "Use tools to understand the trace and code, then return a JSON RCA."
            ),
            task_description=(
                f"Perform an RCA of the error trace at {trace_path}. "
                "Use `parse_error_trace` first, then `read_file` and `list_directory` as needed. "
                "Return one JSON object with: error_type, error_message, root_cause, "
                "affected_file, affected_line, affected_function, evidence (list)."
            ),
            task_expected_output="A single JSON object describing the RCA.",
            llm_service=llm_service,
            model=model,
            tools=[parse_error_trace, read_file, list_directory],
            parallel_tool_calls=False,
        )

     
        fix_agent = Agent(
            name="Fix_Suggestion_Agent_Team",
            backstory=(
                "You are a senior engineer who designs minimal, safe fixes "
                "based on an RCA JSON."
            ),
            task_description=(
                "You will receive the RCA_Agent_Team's output as context. "
                "Generate a JSON fix plan with fields: description, steps[], "
                "safety_considerations[], expected_outcome."
            ),
            task_expected_output="A JSON fix plan object.",
            llm_service=llm_service,
            model=model,
          
            parallel_tool_calls=False,
        )


        patch_agent = Agent(
            name="Patch_Generation_Agent_Team",
            backstory=(
                "You apply minimal, precise code patches using tools. "
                "You always read the original file first, then write a full "
                "corrected file named fixed_<basename>_team.py."
            ),
            task_description=(
                "Use the RCA and fix plan from other agents as context. "
                "1) Use `read_file` on the affected file from the RCA. "
                "2) Apply the fix described in the plan. "
                "3) Use `write_file` to save a full corrected file named "
                "`fixed_user_team.py` in the outputs directory. "
                "Return JSON patch metadata with: original_file, patched_file, "
                "changes_made, lines_modified."
            ),
            task_expected_output="Patch metadata JSON and a new fixed file under outputs/.",
            llm_service=llm_service,
            model=model,
            tools=[read_file, write_file, run_terminal_command],
            parallel_tool_calls=False,
        )

        rca_agent >> fix_agent >> patch_agent

    
        await team.run()

        
        print("\n=== TEAM RESULTS (experimental) ===")
        for name, result in team.results.items():
            print(f"\nAgent: {name}")
          
            if isinstance(result, dict) and "output" in result:
                text = str(result["output"])
            else:
                text = str(result)
            print(text[:500] + ("..." if len(text) > 500 else ""))


def main() -> None:
    asyncio.run(run_rca_fix_patch_team())


if __name__ == "__main__":
    main()


