#!/usr/bin/env python3

from typing import List, Optional, Dict
from pathlib import Path
from loguru import logger
import requests
import json
import os
import asyncio
import aiohttp
import sseclient

class SambanovaClient:
    def __init__(self):
        self.api_key = os.getenv("SAMBANOVA_API_KEY")
        self.base_url = "https://api.sambanova.ai/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
    async def chat_completion(self, user_message: str, system_message: str = "Answer the question in a couple sentences.") -> str:
        """Get chat completion from SambaNova API"""
        payload = {
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            "stop": ["<|eot_id|>"],
            "model": "Meta-Llama-3.1-405B-Instruct",
            "stream": True,
            "stream_options": {"include_usage": True}
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.base_url,
                    headers=self.headers,
                    json=payload
                ) as response:
                    full_response = ""
                    async for line in response.content:
                        if line:
                            try:
                                data = json.loads(line)
                                if "choices" in data:
                                    content = data["choices"][0].get("delta", {}).get("content", "")
                                    full_response += content
                            except json.JSONDecodeError:
                                continue
                    
                    return full_response.strip()
                    
        except Exception as e:
            logger.error(f"Error in chat completion: {str(e)}")
            raise

class DocumentQuerier:
    def __init__(self, docs_dir: Path, collection_name: str):
        self.docs_dir = docs_dir
        self.collection_name = collection_name
        self.sambanova = SambanovaClient()
        
    async def aquery(self, query_text: str) -> str:
        """Async query method"""
        try:
            response = await self.sambanova.chat_completion(
                user_message=query_text,
                system_message="You are a helpful assistant. Answer questions based on the provided context."
            )
            return response
            
        except Exception as e:
            logger.error(f"Query error: {str(e)}")
            raise
            
    def query(self, query_text: str) -> str:
        """Synchronous query wrapper"""
        return asyncio.run(self.aquery(query_text))