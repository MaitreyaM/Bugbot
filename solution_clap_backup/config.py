"""
Configuration for the Multi-Agent RCA System.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent
PROJECT_ROOT = BASE_DIR.parent

# API Configuration
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# LLM Configuration
# Set LLM_PROVIDER to "google", "groq", or "auto" (auto tries google first, then groq)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").lower()

# Model names for each provider
GOOGLE_MODEL = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")
GROQ_MODEL = os.getenv("GROQ_MODEL", "moonshotai/kimi-k2-instruct-0905")

# LLM_MODEL will be set based on provider selection
LLM_MODEL = GOOGLE_MODEL if LLM_PROVIDER == "google" else GROQ_MODEL

# Path Configuration
CODEBASE_PATH = PROJECT_ROOT / "fastapi-project"
ERROR_TRACE_PATH = PROJECT_ROOT / "trace_1.json"
OUTPUT_DIR = BASE_DIR / "outputs"

# Ensure output directory exists
OUTPUT_DIR.mkdir(exist_ok=True)

# Tool Configuration
MAX_FILE_SIZE_BYTES = 1_000_000  # 1MB max file read
ALLOWED_READ_EXTENSIONS = {".py", ".txt", ".json", ".md", ".html", ".yml", ".yaml", ".ini", ".cfg", ".toml"}


LOG_LEVEL = "INFO"

def validate_config():
    """Validate that required configuration is present."""
    errors = []
    
    if not GOOGLE_API_KEY and not GROQ_API_KEY:
        errors.append("Either GOOGLE_API_KEY or GROQ_API_KEY must be set in environment")
    
    if not CODEBASE_PATH.exists():
        errors.append(f"Codebase path does not exist: {CODEBASE_PATH}")
    
    if not ERROR_TRACE_PATH.exists():
        errors.append(f"Error trace file does not exist: {ERROR_TRACE_PATH}")
    
    if errors:
        raise ValueError("Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))
    
    return True

