#!/bin/bash

# Get the App Runner URL
URL=$(aws cloudformation describe-stacks \
    --stack-name algernon \
    --query 'Stacks[0].Outputs[?OutputKey==`AppRunnerURL`].OutputValue' \
    --output text)

if [ -n "$URL" ]; then
    echo "Your application is running at: https://${URL}"
else
    echo "Could not find App Runner URL. Please check if the stack is deployed correctly."
fi 