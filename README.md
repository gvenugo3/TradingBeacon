# Stock EMA Monitor

AWS Lambda function that monitors stocks and sends notifications when they are near their 200-day Exponential Moving Average (EMA).

## Features

- Monitors multiple stocks specified in `tickers.json`
- Calculates 200-day EMA for each stock
- Sends SNS notifications when stocks are within a configurable percentage of their 200 EMA
- Uses Yahoo Finance (free, no API key required)
- Supports batch processing of 100+ stocks
- Designed for AWS Lambda deployment
- Comprehensive error handling and logging

## Setup

### Prerequisites

- AWS CLI configured with appropriate credentials
- SNS topic for notifications (optional)

**No API key required!** - Uses Yahoo Finance free data source

### Configuration Files

1. **tickers.json** - Configure which stocks to monitor:
```json
{
  "tickers": ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA"],
  "threshold_percentage": 2.0
}
```

2. **requirements.txt** - Python dependencies for Lambda

### Environment Variables

Set these in your Lambda function configuration:

- `SNS_TOPIC_ARN` (optional) - SNS topic for notifications

**Note:** No API key environment variables required with Yahoo Finance

## Deployment

### Automatic Deployment

Run the deployment script:

```bash
# Deploy without notifications
./deploy.sh

# Deploy with SNS notifications
./deploy.sh arn:aws:sns:us-west-1:123456789:your-topic
```

This will:
1. Create IAM role with required permissions
2. Install dependencies (yfinance, boto3)
3. Package the function
4. Deploy to AWS Lambda
5. Configure environment variables (if SNS topic provided)
6. Test the deployment

### Manual Deployment

1. Install dependencies:
```bash
pip install -r requirements.txt -t package/
```

2. Package the function:
```bash
cp lambda_function.py tickers.json package/
cd package && zip -r ../deployment.zip . && cd ..
```

3. Deploy to Lambda:
```bash
aws lambda create-function \
    --function-name stock-ema-monitor \
    --runtime python3.9 \
    --role arn:aws:iam::YOUR-ACCOUNT:role/lambda-execution-role \
    --handler lambda_function.lambda_handler \
    --zip-file fileb://deployment.zip \
    --timeout 300
```

## Usage

### Schedule with EventBridge

Create a CloudWatch Events rule to run the function daily:

```bash
aws events put-rule \
    --name stock-ema-daily-check \
    --schedule-expression "cron(0 21 * * MON-FRI *)"
```

### Manual Testing

Test the function locally or via AWS CLI:

```bash
aws lambda invoke --function-name stock-ema-monitor output.json
```

## How It Works

1. **Data Fetching**: Uses Yahoo Finance to get 1 year of daily stock prices
2. **EMA Calculation**: Computes 200-day exponential moving average
3. **Proximity Check**: Determines if current price is within threshold of 200 EMA
4. **Notification**: Sends SNS alert for stocks meeting criteria

### EMA Calculation

The function uses the standard EMA formula:
- α = 2 / (N + 1) where N = 200 (period)
- EMA = α × Current Price + (1 - α) × Previous EMA

### Notification Format

Notifications include:
- Stock symbol
- Current price
- 200 EMA value
- Percentage difference
- Whether price is above/below EMA

## Performance

- **No API limits**: Yahoo Finance has no request restrictions
- **Batch processing**: Can monitor 100+ stocks in a single Lambda execution
- **Fast execution**: Typical runtime 30-60 seconds for 100 stocks
- **Cost effective**: No API subscription fees

## Monitoring

- CloudWatch logs capture all function execution details
- No API rate limits to monitor with Yahoo Finance
- Set up CloudWatch alarms for function errors
- Monitor Lambda duration and memory usage for large stock lists

## Customization

- Modify `threshold_percentage` in `tickers.json` to adjust sensitivity
- Change EMA period by modifying the `calculate_ema` function
- Add additional technical indicators as needed
- Customize notification format in `send_notification` method