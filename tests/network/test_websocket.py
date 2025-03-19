import asyncio
import websockets
import sys
import json
from datetime import datetime

async def test_websocket():
    # Use the most recent WebSocket API Gateway URL
    uri = "wss://0ew0okbrmk.execute-api.us-west-2.amazonaws.com/prod"
    print(f"\nTesting WebSocket connection to: {uri}")
    print("=" * 50)
    
    try:
        # Connect with the required headers
        async with websockets.connect(
            uri,
            origin="https://0ew0okbrmk.execute-api.us-west-2.amazonaws.com",
            subprotocols=["rag-app"],
            additional_headers={
                "Connection": "Upgrade",
                "Upgrade": "websocket",
                "Host": "0ew0okbrmk.execute-api.us-west-2.amazonaws.com",
                "Sec-WebSocket-Version": "13",
                "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ=="
            }
        ) as websocket:
            print("Connected to WebSocket API")
            
            # Test message with minimal data
            test_message = {
                "action": "send_message",
                "data": {
                    "message": "Hello from test client",
                    "timestamp": datetime.now().isoformat()
                }
            }
            
            print(f"\nSending test message: {json.dumps(test_message, indent=2)}")
            await websocket.send(json.dumps(test_message))
            
            # Wait for response
            response = await websocket.recv()
            print(f"\nReceived response: {response}")
            
            # Keep the connection open for a few seconds
            print("\nTesting connection stability...")
            for i in range(3):
                await asyncio.sleep(1)
                print(f"Connection still active... ({i+1}/3)")
            
            print("\nWebSocket test completed successfully")
            return True
            
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"\nWebSocket connection rejected with status code {e.status_code}")
        if e.status_code == 403:
            print("This might be due to:")
            print("1. Missing or invalid authentication")
            print("2. CORS restrictions")
            print("3. VPC or security group settings")
        return False
    except Exception as e:
        print(f"\nError during WebSocket test: {str(e)}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_websocket())
    sys.exit(0 if success else 1) 