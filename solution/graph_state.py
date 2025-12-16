

from typing import TypedDict, Annotated, Optional
from operator import add
from langchain_core.messages import BaseMessage


class RCAGraphState(TypedDict):
    """
    LangGraph state that mirrors SharedMemory structure.
    This is what i convert to shared_memory.json at the end.
    
    """
   
    messages: Annotated[list[BaseMessage], add]
    
    
    rca: Optional[dict]
    fix_plan: Optional[dict]
    patch_metadata: Optional[dict] 
   
    trace_path: str
    codebase_path: str
    output_dir: str

