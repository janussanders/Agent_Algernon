import os
import asyncio
from loguru import logger
import openai
import json
from typing import Iterator, Union, Dict, Tuple, List, AsyncGenerator
import streamlit as st
import sseclient
import requests
from dotenv import load_dotenv
import aiohttp

# Load environment variables from .env file
load_dotenv()

async def create_streaming_chat_completion(
    messages: List[Dict[str, str]],
    model: str = "Meta-Llama-3.3-70B-Instruct",
    max_tokens: int = 512
) -> AsyncGenerator[str, None]:
    """Create a streaming chat completion using SambaNova's API"""
    try:
        api_key = os.getenv("SAMBANOVA_API_KEY")
        base_url = "https://api.sambanova.ai/v1/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Ensure content length is within limits
        for message in messages:
            if len(message['content']) > 4000:  # Conservative limit
                message['content'] = message['content'][:4000] + "..."
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "max_tokens": max_tokens,
            "temperature": 0.7,
            "top_p": 0.9
        }
        
        logger.info(f"Sending request with payload length: {len(str(payload))} bytes")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(base_url, headers=headers, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"API Error: {response.status} - {error_text}")
                    raise Exception(f"API Error: {response.status} - {error_text}")
                
                async for line in response.content:
                    if line:
                        try:
                            # Decode the line and remove the "data: " prefix
                            line_text = line.decode('utf-8').strip()
                            if line_text.startswith('data: '):
                                if line_text == 'data: [DONE]':
                                    break
                                    
                                # Parse the JSON data after "data: "
                                data = json.loads(line_text[6:])
                                if "choices" in data:
                                    delta = data["choices"][0].get("delta", {})
                                    if "content" in delta:
                                        content = delta["content"]
                                        if content:
                                            yield content
                                            
                        except json.JSONDecodeError as e:
                            # Skip JSON decode errors for empty lines
                            if line_text and not line_text.isspace():
                                logger.debug(f"JSON decode error: {e} for line: {line_text}")
                            continue
                            
    except Exception as e:
        logger.error(f"Error in streaming chat completion: {str(e)}")
        raise

def validate_sambanova_setup():
    """Validate SambaNova API setup"""
    api_key = os.getenv("SAMBANOVA_API_KEY")
    if not api_key:
        raise ValueError("SambaNova API key not found in environment variables")
    return True

def get_api_credentials() -> Tuple[str, str]:
    """Get API credentials with priority: ENV > Session State > Default"""
    api_key = (
        os.getenv("SAMBANOVA_API_KEY") or 
        st.session_state.get('sambanova_api_key') or 
        ''
    )
    base_url = (
        os.getenv("SAMBANOVA_URL") or 
        st.session_state.get('sambanova_url') or 
        'https://api.sambanova.ai/v1'
    )
    
    # Store in session state if from environment
    if os.getenv("SAMBANOVA_API_KEY") and not st.session_state.get('sambanova_api_key'):
        st.session_state.sambanova_api_key = api_key
    if os.getenv("SAMBANOVA_URL") and not st.session_state.get('sambanova_url'):
        st.session_state.sambanova_url = base_url
    
    return api_key, base_url

def log_completion_stats(usage):
    """Log completion statistics"""
    if usage:
        stats = {
            "Total tokens": usage.get("total_tokens", 0),
            "Prompt tokens": usage.get("prompt_tokens", 0),
            "Completion tokens": usage.get("completion_tokens", 0),
            "Time to first token": f"{usage.get('time_to_first_token', 0):.3f}s",
            "Total latency": f"{usage.get('total_latency', 0):.3f}s",
            "Tokens per second": usage.get("total_tokens_per_sec", 0)
        }
        logger.info("Completion statistics:")
        for key, value in stats.items():
            logger.info(f"  {key}: {value}") 