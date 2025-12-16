# Multi-Agent RCA + Fix System (LangGraph)

A  3-agent AI system that performs Root Cause Analysis (RCA), generates fix suggestions, and produces code patches for a Python/FastAPI codebase.

# THIS WAS TESTED USING KIMI K2 and QWEN 3 32B open source models primarily which are weaker than gemini (since i did not have gemini credits left.) . Which is why some tools tend to help with complex parsing for these smaller open source models that are cheaper. 

Built with: Langgraph so anyone else can understand my approach (intiial prototype was with my own framework clap agents built from scratch) : https://github.com/MaitreyaM/Clap-Agents
- Custom shared memory and logging layer (`SharedMemory`, `MessageLogger`) for assignment-compliant JSON outputs

## Overview

This system analyzes error traces from APM tools, identifies the root cause of bugs, suggests fixes, and automatically generates patched source files.

At a high level, the pipeline is:

1. **RCA Agent**: Reads the trace + code, produces a structured RCA JSON (root cause, file, line, evidence).
2. **Fix Suggestion Agent**: Reads the RCA from shared memory, produces a structured fix plan JSON.
3. **Patch Generation Agent**: Reads RCA + fix plan, uses tools to read and patch the code, writes a new fixed file and patch metadata.

### Architecture

![System Design](architecture.svg)

Conceptually, the flow is:

- **LangGraph graph** orchestrates three agent nodes (`rca_agent`, `fix_agent`, `patch_agent`) in sequence.
- Each agent uses a LangGraph prebuilt ReAct-style executor (`create_react_agent`) with tools.
- Agents write their structured outputs into `SharedMemory`, and all steps are logged via `MessageLogger` into `message_history.json`.

## Approach & Evolution

I implemented this in **two iterations**:

- **Attempt 1 – Clap-Agents (initial prototype)**  
  - Used the custom multi-agent framework `clap-agents` with ReAct agents and tools.  
  - This worked conceptually but was **brittle with smaller models** (Kimi K2, Qwen):
    - Models often emitted tool calls as plain text instead of actual callable JSON.
    - The framework treated these as final answers, so tools never executed.
    - RCA frequently failed due to weaker models, causing downstream Fix/Patch agents to operate on empty context.

- **Final Version – LangGraph (current solution)**  
  - Migrated orchestration to LangGraph + LangChain, keeping the same domain logic and tools.  
  - Benefits:
    - Uses **standard tool-calling semantics** that work reliably with Groq’s Kimi K2.
    - Easy to plug in multiple providers (Groq, Gemini) behind a small `llm_provider.py` abstraction.
    - Still writes outputs through the same `SharedMemory` and `MessageLogger` .
  - Results:
    - With `LLM_PROVIDER=groq` (Kimi K2), the pipeline succeeds end-to-end, generating:
      - Correct RCA (AttributeError on `User.emails` vs `User.email`)
      - Minimal fix plan
      - `outputs/fixed_user.py` full fixed file
   

## Requirements

- Python 3.10+
- Conda environment (e.g. `middleware-py310`)
- **Groq API Key** (recommended, tested with `moonshotai/kimi-k2-instruct-0905`)
- Optional: **Google API Key** (for Gemini)

## Installation

1. **Clone or navigate to the project root:**
   ```bash
   cd middleware_assignment/
   ```

2. **Create and activate the conda environment (recommended):**
   ```bash
   conda create -n middleware-py310 python=3.10
   conda activate middleware-py310
   ```

3. **Install dependencies:**
   ```bash
   cd solution/
   pip install -r requirements.txt
   ```

4. **Set up environment variables:**
   
   Create a `.env` file in the solution directory:
   ```bash
   # Groq API Key (primary - tested with Kimi K2)
   GROQ_API_KEY=your_groq_api_key_here
   
   # Optional: Google API Key (Gemini) if you have quota
   GOOGLE_API_KEY=your_google_api_key_here

   # Optional: override models
   GROQ_MODEL=moonshotai/kimi-k2-instruct-0905
   GOOGLE_MODEL=gemini-2.0-flash-exp
   ```

## Usage

### Basic Usage

Run the complete RCA pipeline with default settings (from `solution/`):

```bash
python main.py
```

This will:
1. Parse the error trace from `../trace_1.json`
2. Analyze the codebase at `../fastapi-project`
3. Generate outputs in `./outputs/` (shared memory, message history, patch file)

### Custom Paths & Options

You can customize paths and LLM provider:

```bash
LLM_PROVIDER=groq python main.py \
  --trace ../trace_1.json \
  --codebase ../fastapi-project \
  --output ./outputs
```

Supported `LLM_PROVIDER` values:
- `groq`   – use Groq (Kimi K2, recommended)
- `google` – use Gemini (requires quota)
- `auto`   – try Groq first, then Gemini (if configured)

#### Command Line Options



### shared_memory.json Structure

```json
{
  "rca": {
    "error_type": "AttributeError",
    "error_message": "type object 'User' has no attribute 'emails'",
    "root_cause": "Typo in attribute name - 'emails' should be 'email'",
    "affected_file": "/usr/srv/app/services/user.py",
    "affected_line": 18,
    "affected_function": "create_user_account",
    "evidence": ["..."]
  },
  "fix_plan": {
    "description": "Change 'User.emails' to 'User.email'",
    "steps": ["..."],
    "safety_considerations": ["..."]
  },
  "patch_metadata": {
    "original_file": "app/services/user.py",
    "patched_file": "fixed_user.py",
    "changes_made": ["..."]
  }
}
```

### message_history.json Structure

```json
{
  "session_id": "abc12345",
  "start_time": "2024-01-15T10:30:00.000Z",
  "events": [
    {
      "event_id": 1,
      "timestamp": "...",
      "agent_name": "RCA_Agent",
      "event_type": "agent_start",
      "iteration": 1,
      "data": {...}
    },
    ...
  ]
}
```

## Project Structure

```

## Agents

### 1. RCA Agent

**Purpose:** Analyze error traces and identify root causes.

**Tools Used:**
- `parse_error_trace` - Parse JSON error trace files
- `read_file` - Read source code files
- `list_directory` - Explore codebase structure

**Output:** Structured RCA report with error type, location, and evidence.

### 2. Fix Suggestion Agent

**Purpose:** Generate actionable fix plans.

**Tools Used:** None (reasoning only, uses shared memory context)

**Output:** Fix plan with steps, safety considerations, and expected outcome.

### 3. Patch Generation Agent

**Purpose:** Create corrected source files.

**Tools Used:**
- `read_file` - Read original source file
- `write_file` - Write patched file to outputs/

**Output:** Complete patched file and patch metadata.

## Tool Robustness

All tools include:
- **Path validation** - Prevents directory traversal attacks
- **Error handling** - Graceful failures with descriptive messages
- **Encoding handling** - UTF-8 with fallback to latin-1
- **Size limits** - Prevents reading extremely large files
- **Write protection** - Only allows writing to outputs/ directory

## Troubleshooting

### "No LLM service available"

Set `GROQ_API_KEY` (recommended) or `GOOGLE_API_KEY` in your environment or `.env` file.  
Ensure `LLM_PROVIDER` is one of `groq`, `google`, or `auto`.

### Gemini 429 / quota errors

If you see `RESOURCE_EXHAUSTED` errors from Gemini, your free-tier quota is exhausted.  
You can:
- Switch to `LLM_PROVIDER=groq` (Kimi K2).
- Or use a different Google project/key with available quota.

### "File not found" errors

Ensure paths are correct. The system looks for files in:
- The specified path directly
- Relative to the codebase directory
- Mapped from Docker paths (`/usr/srv/app/` → local paths)

## Example Run (Groq / Kimi K2)

```bash
cd middleware_assignment/solution
LLM_PROVIDER=groq python main.py
```

You should see a summary like:

- RCA: `AttributeError`, `User.emails` vs `User.email`, file `/usr/srv/app/services/user.py`, line `18`.
- Fix Plan: 3 steps, multiple safety considerations.
- Patch: `fixed_user.py` created under `outputs/` with a single-line change to the query.



