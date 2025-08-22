#!/bin/bash

# AWS Lambda Deployment Script for Stock EMA Monitor

set -e

# Configuration
FUNCTION_NAME="stock-ema-monitor"
REGION="us-west-1"
ROLE_NAME="lambda-stock-monitor-role"
ZIP_FILE="stock-monitor-deployment.zip"

echo "🚀 Deploying Stock EMA Monitor to AWS Lambda..."

# Create deployment package
echo "📦 Creating deployment package..."
rm -f $ZIP_FILE

# Install dependencies to a temp directory
mkdir -p package
pip install -r requirements.txt -t package/

# Copy source files
cp lambda_function.py package/
cp tickers.json package/

# Create zip file
cd package
zip -r ../$ZIP_FILE .
cd ..

# Clean up temp directory
rm -rf package

echo "✅ Deployment package created: $ZIP_FILE"

# Check if function exists
echo "🔍 Checking if Lambda function exists..."
if aws lambda get-function --function-name $FUNCTION_NAME --region $REGION >/dev/null 2>&1; then
    echo "📝 Updating existing Lambda function..."
    aws lambda update-function-code \
        --function-name $FUNCTION_NAME \
        --zip-file fileb://$ZIP_FILE \
        --region $REGION
else
    echo "🆕 Creating new Lambda function..."
    echo "⚠️  Make sure you have created the IAM role '$ROLE_NAME' with appropriate permissions"
    echo "   Required permissions: SNS publish, CloudWatch logs, basic Lambda execution"
    
    read -p "Enter your IAM role ARN for Lambda execution: " ROLE_ARN
    
    aws lambda create-function \
        --function-name $FUNCTION_NAME \
        --runtime python3.9 \
        --role $ROLE_ARN \
        --handler lambda_function.lambda_handler \
        --zip-file fileb://$ZIP_FILE \
        --timeout 300 \
        --memory-size 256 \
        --region $REGION
fi

# Update environment variables
echo "🔧 Setting environment variables..."
read -p "Enter your Alpha Vantage API key: " ALPHA_VANTAGE_KEY
read -p "Enter your SNS Topic ARN (optional, press enter to skip): " SNS_TOPIC_ARN

ENV_VARS="ALPHA_VANTAGE_API_KEY=$ALPHA_VANTAGE_KEY"
if [ ! -z "$SNS_TOPIC_ARN" ]; then
    ENV_VARS="$ENV_VARS,SNS_TOPIC_ARN=$SNS_TOPIC_ARN"
fi

aws lambda update-function-configuration \
    --function-name $FUNCTION_NAME \
    --environment "Variables={$ENV_VARS}" \
    --region $REGION

echo "✅ Lambda function deployed successfully!"
echo "🔗 Function ARN:"
aws lambda get-function --function-name $FUNCTION_NAME --region $REGION --query 'Configuration.FunctionArn' --output text

# Clean up
rm -f $ZIP_FILE

echo ""
echo "📋 Next steps:"
echo "1. Set up CloudWatch Events/EventBridge to trigger the function on a schedule"
echo "2. Create an SNS topic if you haven't already and update the environment variable"
echo "3. Test the function: aws lambda invoke --function-name $FUNCTION_NAME --region $REGION output.json"
echo "4. Monitor logs in CloudWatch"