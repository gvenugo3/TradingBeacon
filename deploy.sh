#!/bin/bash

# AWS Lambda Deployment Script for Stock EMA Monitor (Fixed Version)

set -e

# Configuration
FUNCTION_NAME="stock-ema-monitor"
REGION="us-west-1"
ROLE_NAME="stock-monitor-lambda-role"
ZIP_FILE="stock-monitor-deployment.zip"

# Check if SNS topic ARN is provided (optional)
SNS_TOPIC_ARN=${1:-}

if [ ! -z "$SNS_TOPIC_ARN" ]; then
    echo "📧 SNS notifications will be sent to: $SNS_TOPIC_ARN"
else
    echo "📧 No SNS topic provided - notifications disabled"
fi

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

# Install minimal dependencies
echo "📥 Installing minimal dependencies..."
pip install --target package/ --no-deps boto3==1.28.25
pip install --target package/ --no-deps botocore==1.31.85
pip install --target package/ --no-deps requests==2.31.0
pip install --target package/ --no-deps urllib3==1.26.16
pip install --target package/ --no-deps certifi==2023.7.22
pip install --target package/ --no-deps charset-normalizer==3.2.0
pip install --target package/ --no-deps idna==3.4
pip install --target package/ --no-deps jmespath==1.0.1
pip install --target package/ --no-deps s3transfer==0.6.2
pip install --target package/ --no-deps python-dateutil==2.8.2
pip install --target package/ --no-deps six==1.16.0

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
        --runtime python3.11 \
        --role $ROLE_ARN \
        --handler lambda_function.lambda_handler \
        --zip-file fileb://$ZIP_FILE \
        --timeout 300 \
        --memory-size 512 \
        --region $REGION >/dev/null
fi

# Update environment variables (only SNS topic if provided)
if [ ! -z "$SNS_TOPIC_ARN" ]; then
    echo "🔧 Setting SNS topic environment variable..."
    aws lambda update-function-configuration \
        --function-name $FUNCTION_NAME \
        --environment "Variables={SNS_TOPIC_ARN=$SNS_TOPIC_ARN}" \
        --region $REGION >/dev/null
    echo "📧 SNS notifications: $SNS_TOPIC_ARN"
else
    echo "🔧 No environment variables to set (Yahoo Finance needs no API key!)"
fi

# Remove unnecessary files to reduce size
echo "🧹 Optimizing package size..."
cd package
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
find . -name "*.pyo" -delete 2>/dev/null || true
cd ..

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