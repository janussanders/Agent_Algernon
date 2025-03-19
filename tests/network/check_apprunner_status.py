#!/usr/bin/env python3

import boto3
import sys
import time
import subprocess
from datetime import datetime

def get_service_arn(service_name, region="us-west-2"):
    """Get the service ARN from AWS App Runner."""
    client = boto3.client('apprunner', region_name=region)
    
    try:
        # List services and find the one matching our name
        response = client.list_services()
        for service in response['ServiceSummaryList']:
            if service['ServiceName'] == service_name:
                return service['ServiceArn']
        return None
    except Exception as e:
        print(f"Error getting service ARN: {str(e)}")
        return None

def get_service_status(service_arn, region="us-west-2"):
    """Get the status of an App Runner service."""
    client = boto3.client('apprunner', region_name=region)
    
    try:
        # Get service details using ARN
        response = client.describe_service(ServiceArn=service_arn)
        service = response['Service']
        
        # Get detailed status information
        status = service['Status']
        last_updated = service['UpdatedAt']
        service_url = service.get('ServiceUrl', 'N/A')
        
        # Get the latest operation if any
        operations = client.list_operations(ServiceArn=service_arn)
        latest_operation = None
        if operations['OperationSummaryList']:
            latest_operation = operations['OperationSummaryList'][0]
        
        return {
            'status': status,
            'last_updated': last_updated,
            'service_url': service_url,
            'latest_operation': latest_operation
        }
    except Exception as e:
        print(f"Error getting status for service ARN: {str(e)}")
        return None

def monitor_service_status(service_arn, check_interval=10, max_checks=60):
    """Monitor service status until it's stable or max checks reached."""
    print(f"\nMonitoring App Runner service: {service_arn}")
    print("=" * 50)
    
    check_count = 0
    last_status = None
    
    while check_count < max_checks:
        status_info = get_service_status(service_arn)
        if not status_info:
            print("Failed to get service status")
            return False
        
        current_status = status_info['status']
        last_updated = status_info['last_updated']
        
        # Print status if it changed
        if current_status != last_status:
            print(f"\nStatus: {current_status}")
            print(f"Last Updated: {last_updated}")
            print(f"Service URL: {status_info['service_url']}")
            
            if status_info['latest_operation']:
                operation = status_info['latest_operation']
                print("Latest Operation Details:")
                for key, value in operation.items():
                    if key not in ['OperationId']:  # Skip internal fields
                        print(f"  {key}: {value}")
            
            print("-" * 50)
        
        # Check if service is in a stable state
        if current_status in ['RUNNING', 'PAUSED', 'STOPPED']:
            if status_info['latest_operation'] and status_info['latest_operation'].get('Status') == 'SUCCEEDED':
                print(f"\nService is now stable with status: {current_status}")
                return True
            elif status_info['latest_operation'] and status_info['latest_operation'].get('Status') == 'FAILED':
                print(f"\nService update failed")
                return False
        
        last_status = current_status
        check_count += 1
        time.sleep(check_interval)
    
    print(f"\nMonitoring timed out after {max_checks * check_interval} seconds")
    return False

def get_config_value(key):
    """Get a value from aws/config.sh using source and echo."""
    try:
        cmd = f"source aws/config.sh && echo ${key}"
        result = subprocess.run(['bash', '-c', cmd], capture_output=True, text=True)
        return result.stdout.strip()
    except Exception as e:
        print(f"Error getting config value for {key}: {str(e)}")
        return None

def main():
    if len(sys.argv) < 2:
        print("Usage: python check_apprunner_status.py <service-name>")
        print("Example: python check_apprunner_status.py rag-app")
        sys.exit(1)
    
    service_name = sys.argv[1]
    
    # Get AWS region from config
    region = get_config_value('AWS_REGION')
    if not region:
        print("Error: Could not get AWS region from config")
        sys.exit(1)
    
    # Get service ARN
    service_arn = get_service_arn(service_name, region)
    if not service_arn:
        print(f"Error: Could not find service ARN for {service_name}")
        sys.exit(1)
    
    success = monitor_service_status(service_arn)
    
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main() 