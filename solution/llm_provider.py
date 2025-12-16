

import os
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.language_models import BaseChatModel


def get_llm_for_provider(provider: str = "auto") -> BaseChatModel:
    
  
    provider = os.getenv("LLM_PROVIDER", provider).lower()
    
    if provider == "groq":
        if not os.getenv("GROQ_API_KEY"):
            raise ValueError("GROQ_API_KEY required when LLM_PROVIDER=groq")
        
        model_name = os.getenv("GROQ_MODEL", "moonshotai/kimi-k2-instruct-0905")
        print(f"Using Groq LLM service (model: {model_name})")
        
        return ChatGroq(
            model=model_name,
            temperature=0,
            max_retries=2,
        )
    
    elif provider == "google":
        if not os.getenv("GOOGLE_API_KEY"):
            raise ValueError("GOOGLE_API_KEY required when LLM_PROVIDER=google")
        
        model_name = os.getenv("GOOGLE_MODEL", "gemini-2.0-flash-exp")
        print(f"Using Google Gemini LLM service (model: {model_name})")
        
        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=0,
            max_retries=2,
        )
    
    else:  
      
        if os.getenv("GROQ_API_KEY"):
            model_name = os.getenv("GROQ_MODEL", "moonshotai/kimi-k2-instruct-0905")
            print(f"Using Groq LLM service (model: {model_name})")
            
            return ChatGroq(
                model=model_name,
                temperature=0,
                max_retries=2,
            )
        
        
        elif os.getenv("GOOGLE_API_KEY"):
            model_name = os.getenv("GOOGLE_MODEL", "gemini-2.0-flash-exp")
            print(f"Using Google Gemini LLM service (model: {model_name})")
            
            return ChatGoogleGenerativeAI(
                model=model_name,
                temperature=0,
                max_retries=2,
            )
        
        else:
            raise ValueError(
                "No LLM provider available. Set GROQ_API_KEY or GOOGLE_API_KEY"
            )

