#!/usr/bin/env python3

import boto3
import json
import sys
import time
from datetime import datetime

def create_websocket_api(region="us-west-2"):
    """Create a WebSocket API Gateway for the RAG app."""
    client = boto3.client('apigatewayv2', region_name=region)
    
    try:
        # Create the WebSocket API
        response = client.create_api(
            Name='rag-app-websocket',
            ProtocolType='WEBSOCKET',
            RouteSelectionExpression='$request.body.action'
        )
        
        api_id = response['ApiId']
        print(f"Created WebSocket API with ID: {api_id}")
        
        # Create routes
        routes = [
            ('$connect', 'Connect route'),
            ('$disconnect', 'Disconnect route'),
            ('$default', 'Default route for messages'),
            ('send_message', 'Route for sending messages')
        ]
        
        for route_key, description in routes:
            route_response = client.create_route(
                ApiId=api_id,
                RouteKey=route_key,
                OperationName=description
            )
            print(f"Created route: {route_key}")
        
        # Create stage
        stage_response = client.create_stage(
            ApiId=api_id,
            StageName='prod'
        )
        print(f"Created stage: prod")
        
        return api_id
        
    except Exception as e:
        print(f"Error creating WebSocket API: {str(e)}")
        return None

def create_iam_policy(api_id, region="us-west-2"):
    """Create IAM policy for WebSocket API access."""
    iam = boto3.client('iam', region_name=region)
    
    policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "execute-api:Invoke",
                    "execute-api:ManageConnections"
                ],
                "Resource": [
                    f"arn:aws:execute-api:{region}:*:{api_id}/prod/*",
                    f"arn:aws:execute-api:{region}:*:{api_id}/prod/@connections/*"
                ]
            }
        ]
    }
    
    try:
        response = iam.create_policy(
            PolicyName='rag-app-websocket-policy',
            PolicyDocument=json.dumps(policy_document),
            Description='Policy for RAG app WebSocket API access'
        )
        print(f"Created IAM policy: {response['Policy']['PolicyName']}")
        return response['Policy']['Arn']
    except Exception as e:
        print(f"Error creating IAM policy: {str(e)}")
        return None

def get_websocket_url(api_id, region="us-west-2"):
    """Get the WebSocket URL for the API."""
    client = boto3.client('apigatewayv2', region_name=region)
    
    try:
        response = client.get_api(ApiId=api_id)
        return response['ApiEndpoint']
    except Exception as e:
        print(f"Error getting WebSocket URL: {str(e)}")
        return None

def main():
    if len(sys.argv) < 2:
        print("Usage: python deploy_websocket_api.py <action>")
        print("Actions: create, get-url")
        sys.exit(1)
    
    action = sys.argv[1]
    region = "us-west-2"  # Get from config if needed
    
    if action == "create":
        api_id = create_websocket_api(region)
        if api_id:
            policy_arn = create_iam_policy(api_id, region)
            if policy_arn:
                print(f"\nWebSocket API created successfully!")
                print(f"API ID: {api_id}")
                print(f"IAM Policy ARN: {policy_arn}")
                print(f"WebSocket URL: {get_websocket_url(api_id, region)}")
    elif action == "get-url":
        # Get API ID from config or environment
        api_id = "YOUR_API_ID"  # Replace with actual API ID
        url = get_websocket_url(api_id, region)
        if url:
            print(f"WebSocket URL: {url}")
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)

if __name__ == "__main__":
    main() 