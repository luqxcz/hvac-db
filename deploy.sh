#!/bin/bash

# HVAC Heartbeat Lambda Deployment Script
# This script packages and deploys the Lambda function to AWS

set -e  # Exit on any error

# Configuration - Update these values for your environment
FUNCTION_NAME="hvac-heartbeat-updater"
REGION="us-east-1"  # Change to your preferred region
RUNTIME="python3.9"
HANDLER="lambda_function.lambda_handler"
ROLE_ARN=""  # Set this to your Lambda execution role ARN

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Starting HVAC Heartbeat Lambda Deployment${NC}"

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI is not installed. Please install it first.${NC}"
    exit 1
fi

# Check if we're authenticated
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}❌ AWS CLI is not configured. Please run 'aws configure' first.${NC}"
    exit 1
fi

echo -e "${YELLOW}📦 Creating deployment package...${NC}"

# Clean up any existing deployment artifacts
rm -rf package/
rm -f heartbeat-lambda.zip

# Create package directory
mkdir -p package

# Install dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt -t package/

# Copy Lambda function code
cp lambda_function.py package/

# Create deployment zip
cd package
zip -r ../heartbeat-lambda.zip . -q
cd ..

echo -e "${GREEN}✅ Deployment package created: heartbeat-lambda.zip${NC}"

# Check if function exists
if aws lambda get-function --function-name "$FUNCTION_NAME" --region "$REGION" &> /dev/null; then
    echo -e "${YELLOW}🔄 Function exists. Updating code...${NC}"
    
    # Update existing function
    aws lambda update-function-code \
        --function-name "$FUNCTION_NAME" \
        --zip-file fileb://heartbeat-lambda.zip \
        --region "$REGION"
    
    echo -e "${GREEN}✅ Function code updated successfully!${NC}"
    
else
    echo -e "${YELLOW}🆕 Function doesn't exist. Creating new function...${NC}"
    
    # Check if ROLE_ARN is set
    if [ -z "$ROLE_ARN" ]; then
        echo -e "${RED}❌ ROLE_ARN is not set. Please set the Lambda execution role ARN in this script.${NC}"
        echo "You can create a role with the following policy:"
        echo "- AWSLambdaBasicExecutionRole"
        echo "- AWSLambdaVPCAccessExecutionRole (if using VPC)"
        exit 1
    fi
    
    # Create new function
    aws lambda create-function \
        --function-name "$FUNCTION_NAME" \
        --runtime "$RUNTIME" \
        --role "$ROLE_ARN" \
        --handler "$HANDLER" \
        --zip-file fileb://heartbeat-lambda.zip \
        --timeout 30 \
        --memory-size 128 \
        --region "$REGION" \
        --description "HVAC device heartbeat updater"
    
    echo -e "${GREEN}✅ Function created successfully!${NC}"
fi

# Set environment variables (you'll need to update these)
echo -e "${YELLOW}⚙️  Setting environment variables...${NC}"
echo "Note: You'll need to set these manually in the AWS Console or update this script:"
echo "- DB_HOST: Your RDS endpoint"
echo "- DB_PORT: 5432"
echo "- DB_NAME: hvac_db"
echo "- DB_USER: Your database username"
echo "- DB_PASSWORD: Your database password"

# Clean up
rm -rf package/
rm -f heartbeat-lambda.zip

echo -e "${GREEN}🎉 Deployment complete!${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Set environment variables in AWS Lambda console"
echo "2. Configure VPC settings if your RDS is in a VPC"
echo "3. Set up EventBridge rule for scheduling (if needed)"
echo "4. Test the function with a sample event"
echo ""
echo "Function ARN:"
aws lambda get-function --function-name "$FUNCTION_NAME" --region "$REGION" --query 'Configuration.FunctionArn' --output text
