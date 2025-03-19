#!/usr/bin/env python3

import websockets
import asyncio
import json
import sys
import time
from datetime import datetime

async def test_websocket_connection(url):
    """Test WebSocket connection through API Gateway."""
    print(f"\nTesting WebSocket connection to: {url}")
    print("=" * 50)
    
    try:
        async with websockets.connect(url) as websocket:
            print("Connected to WebSocket API")
            
            # Test message
            test_message = {
                "action": "send_message",
                "data": {
                    "message": "Hello from test client",
                    "timestamp": datetime.now().isoformat()
                }
            }
            
            # Send message
            print("\nSending test message...")
            await websocket.send(json.dumps(test_message))
            
            # Wait for response
            response = await websocket.recv()
            print(f"\nReceived response: {response}")
            
            # Keep connection open for a few seconds to test stability
            print("\nTesting connection stability...")
            for i in range(3):
                await asyncio.sleep(1)
                print(f"Connection still active... ({i+1}/3)")
            
            print("\nWebSocket test completed successfully")
            
    except Exception as e:
        print(f"\nError during WebSocket test: {str(e)}")
        return False
    
    return True

def main():
    if len(sys.argv) < 2:
        print("Usage: python test_websocket_gateway.py <websocket-url>")
        print("Example: python test_websocket_gateway.py wss://abc123.execute-api.us-west-2.amazonaws.com/prod")
        sys.exit(1)
    
    url = sys.argv[1]
    
    # Run the WebSocket test
    success = asyncio.run(test_websocket_connection(url))
    
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main() 