#!/bin/bash

# AWS Lambda Deployment Script for Stock EMA Monitor (Fixed Version)

set -e

# Configuration
FUNCTION_NAME="stock-ema-monitor"
REGION="us-west-1"
ROLE_NAME="stock-monitor-lambda-role"
ZIP_FILE="stock-monitor-deployment.zip"

# Check if required parameters are provided
if [ $# -lt 1 ]; then
    echo "Usage: $0 <ALPHA_VANTAGE_API_KEY> [SNS_TOPIC_ARN]"
    echo "Example: $0 YOUR_API_KEY_HERE arn:aws:sns:us-west-1:123456789:stock-alerts"
    exit 1
fi

ALPHA_VANTAGE_KEY=$1
SNS_TOPIC_ARN=${2:-}

echo "🚀 Deploying Stock EMA Monitor to AWS Lambda..."
echo "📋 Function: $FUNCTION_NAME"
echo "🌍 Region: $REGION"

# Create IAM role if it doesn't exist
echo "🔐 Checking/Creating IAM role..."
if ! aws iam get-role --role-name $ROLE_NAME >/dev/null 2>&1; then
    echo "📝 Creating IAM role: $ROLE_NAME"
    
    # Create trust policy
    cat > /tmp/lambda-trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

    # Create role
    aws iam create-role \
        --role-name $ROLE_NAME \
        --assume-role-policy-document file:///tmp/lambda-trust-policy.json

    # Attach policies
    aws iam attach-role-policy \
        --role-name $ROLE_NAME \
        --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

    aws iam attach-role-policy \
        --role-name $ROLE_NAME \
        --policy-arn arn:aws:iam::aws:policy/AmazonSNSFullAccess

    # Clean up temp file
    rm -f /tmp/lambda-trust-policy.json
    
    echo "⏳ Waiting for role propagation..."
    sleep 15
else
    echo "✅ IAM role already exists: $ROLE_NAME"
fi

# Get role ARN
ROLE_ARN=$(aws iam get-role --role-name $ROLE_NAME --query 'Role.Arn' --output text)
echo "🔑 Using role: $ROLE_ARN"

# Create deployment package
echo "📦 Creating deployment package..."
rm -f $ZIP_FILE
rm -rf package/

# Create package directory
mkdir -p package

# Install dependencies with better error handling
echo "📥 Installing dependencies..."
pip install requests boto3 -t package/ --no-deps --quiet

# Install specific compatible versions
pip install \
    botocore==1.31.85 \
    jmespath==1.0.1 \
    python-dateutil==2.9.0.post0 \
    s3transfer==0.6.2 \
    urllib3==2.0.7 \
    certifi==2025.8.3 \
    charset-normalizer==3.4.3 \
    idna==3.10 \
    six==1.17.0 \
    -t package/ --no-deps --quiet

# Copy source files
cp lambda_function.py package/
cp tickers.json package/

# Create zip file
echo "🗜️  Creating deployment package..."
cd package
zip -r ../$ZIP_FILE . >/dev/null
cd ..

# Clean up temp directory
rm -rf package

echo "✅ Deployment package created: $ZIP_FILE"

# Deploy or update function
echo "🔍 Checking if Lambda function exists..."
if aws lambda get-function --function-name $FUNCTION_NAME --region $REGION >/dev/null 2>&1; then
    echo "📝 Updating existing Lambda function..."
    aws lambda update-function-code \
        --function-name $FUNCTION_NAME \
        --zip-file fileb://$ZIP_FILE \
        --region $REGION >/dev/null
else
    echo "🆕 Creating new Lambda function..."
    aws lambda create-function \
        --function-name $FUNCTION_NAME \
        --runtime python3.9 \
        --role $ROLE_ARN \
        --handler lambda_function.lambda_handler \
        --zip-file fileb://$ZIP_FILE \
        --timeout 300 \
        --memory-size 256 \
        --region $REGION >/dev/null
fi

# Update environment variables
echo "🔧 Setting environment variables..."
ENV_VARS="ALPHA_VANTAGE_API_KEY=$ALPHA_VANTAGE_KEY"
if [ ! -z "$SNS_TOPIC_ARN" ]; then
    ENV_VARS="$ENV_VARS,SNS_TOPIC_ARN=$SNS_TOPIC_ARN"
    echo "📧 SNS notifications: $SNS_TOPIC_ARN"
fi

aws lambda update-function-configuration \
    --function-name $FUNCTION_NAME \
    --environment "Variables={$ENV_VARS}" \
    --region $REGION >/dev/null

echo "✅ Lambda function deployed successfully!"

# Get function info
FUNCTION_ARN=$(aws lambda get-function --function-name $FUNCTION_NAME --region $REGION --query 'Configuration.FunctionArn' --output text)
echo "🔗 Function ARN: $FUNCTION_ARN"

# Test the function
echo "🧪 Testing function..."
aws lambda invoke \
    --function-name $FUNCTION_NAME \
    --region $REGION \
    /tmp/test-output.json >/dev/null

if [ $? -eq 0 ]; then
    echo "✅ Function test successful!"
    # Show results summary
    python3 -c "
import json
with open('/tmp/test-output.json', 'r') as f:
    result = json.load(f)
    if result.get('statusCode') == 200:
        body = json.loads(result['body'])
        results = body['results']
        print(f'📊 Processed {results[\"stocks_processed\"]} stocks')
        print(f'🚨 Alerts sent: {results[\"alerts_sent\"]}')
        if results['errors']:
            print(f'❌ Errors: {len(results[\"errors\"])}')
    else:
        print('❌ Function returned error')
        print(result.get('body', 'Unknown error'))
"
else
    echo "❌ Function test failed"
fi

# Clean up
rm -f $ZIP_FILE /tmp/test-output.json

echo ""
echo "📋 Next steps:"
echo "1. Set up CloudWatch Events to trigger function on schedule"
echo "2. Create SNS topic for notifications if not done already"
echo "3. Monitor logs: aws logs tail /aws/lambda/$FUNCTION_NAME --follow"
echo "4. Test manually: aws lambda invoke --function-name $FUNCTION_NAME output.json"

echo "🎉 Deployment complete!"