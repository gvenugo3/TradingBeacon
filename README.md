# Stock EMA Monitor

AWS Lambda function that monitors stocks and sends notifications when they are near their 200-day Exponential Moving Average (EMA).

## Features

- Monitors multiple stocks specified in `tickers.json`
- Calculates 200-day EMA for each stock
- Sends SNS notifications when stocks are within a configurable percentage of their 200 EMA
- Designed for AWS Lambda deployment
- Comprehensive error handling and logging

## Setup

### Prerequisites

- AWS CLI configured with appropriate credentials
- Alpha Vantage API key (free at https://www.alphavantage.co/support/#api-key)
- SNS topic for notifications (optional)

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

- `ALPHA_VANTAGE_API_KEY` (required) - Your Alpha Vantage API key
- `SNS_TOPIC_ARN` (optional) - SNS topic for notifications

## Deployment

### Automatic Deployment

Run the deployment script:

```bash
./deploy.sh
```

This will:
1. Install dependencies
2. Package the function
3. Deploy to AWS Lambda
4. Configure environment variables

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

1. **Data Fetching**: Uses Alpha Vantage API to get daily stock prices
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

## API Limits

- Alpha Vantage free tier: 5 API requests per minute, 500 per day
- Consider upgrading for higher frequency monitoring

## Monitoring

- CloudWatch logs capture all function execution details
- Monitor API usage to avoid rate limits
- Set up CloudWatch alarms for function errors

## Customization

- Modify `threshold_percentage` in `tickers.json` to adjust sensitivity
- Change EMA period by modifying the `calculate_ema` function
- Add additional technical indicators as needed
- Customize notification format in `send_notification` method