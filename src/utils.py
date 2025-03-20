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
    max_tokens: int = 512,
    temperature: float = 0.7,
    top_p: float = 0.95,
    stream: bool = True
) -> AsyncGenerator[str, None]:
    """
    Create a streaming chat completion using the SambaNova API
    
    Args:
        messages: List of message dictionaries
        max_tokens: Maximum number of tokens to generate
        temperature: Sampling temperature
        top_p: Top-p sampling parameter
        stream: Whether to stream the response
        
    Yields:
        str: Generated text chunks
    """
    try:
        # Get API configuration
        api_key = os.getenv("SAMBANOVA_API_KEY")
        api_url = os.getenv("SAMBANOVA_URL", "https://api.sambanova.ai/v1/chat/completions")
        
        if not api_key:
            raise ValueError("SAMBANOVA_API_KEY environment variable must be set")
        
        # Prepare request payload
        payload = {
            "model": os.getenv("SAMBANOVA_MODEL", "DeepSeek-R1-Distill-Llama-70B"),
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": stream
        }
        
        # Set up headers
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Make request
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, json=payload, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"API request failed: {error_text}")
                
                if stream:
                    # Process streaming response
                    async for line in response.content:
                        if line:
                            try:
                                # Parse SSE data
                                line = line.decode('utf-8').strip()
                                if line.startswith('data: '):
                                    data = line[6:]
                                    if data == '[DONE]':
                                        break
                                    
                                    chunk = parse_chunk(data)
                                    if chunk:
                                        yield chunk
                            except Exception as e:
                                logger.error(f"Error processing chunk: {str(e)}")
                                continue
                else:
                    # Process non-streaming response
                    data = await response.json()
                    if 'choices' in data and len(data['choices']) > 0:
                        yield data['choices'][0]['message']['content']
    
    except Exception as e:
        logger.error(f"Error in create_streaming_chat_completion: {str(e)}")
        raise

def parse_chunk(data: str) -> str:
    """
    Parse a chunk of streaming data
    
    Args:
        data: Raw chunk data
        
    Returns:
        str: Parsed text content
    """
    try:
        # Parse JSON data
        chunk_data = json.loads(data)
        
        # Extract content from chunk
        if 'choices' in chunk_data and len(chunk_data['choices']) > 0:
            delta = chunk_data['choices'][0].get('delta', {})
            return delta.get('content', '')
        
        return ''
        
    except Exception as e:
        logger.error(f"Error parsing chunk: {str(e)}")
        return ''

def validate_sambanova_setup(api_key: str) -> bool:
    """
    Validate the SambaNova API setup
    
    Args:
        api_key (str): The API key to validate
        
    Returns:
        bool: True if setup is valid
    """
    try:
        # Set the API key in environment
        os.environ["SAMBANOVA_API_KEY"] = api_key
        
        # Get API URL from environment
        api_url = os.getenv("SAMBANOVA_URL", "https://api.sambanova.ai/v1/chat/completions")
        
        # Test API connection with a simple completion
        test_messages = [{"role": "user", "content": "Test connection"}]
        response = asyncio.run(create_streaming_chat_completion(
            messages=test_messages,
            model="DeepSeek-R1-Distill-Llama-70B",
            temperature=0.7,
            max_tokens=10,
            stream=False
        ))
        
        if response:
            logger.info("Successfully validated SambaNova API key")
            return True
        else:
            logger.error("Failed to get response from SambaNova API")
            return False
            
    except Exception as e:
        logger.error(f"Error validating SambaNova setup: {str(e)}")
        return False

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