import json
import requests
import boto3
from datetime import datetime
from typing import List, Dict, Optional
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

class StockEMAMonitor:
    def __init__(self):
        self.sns_client = boto3.client('sns')
        self.alpha_vantage_api_key = None  # Set via environment variable
        
    def calculate_ema(self, prices: List[float], period: int = 200) -> Optional[float]:
        """Calculate Exponential Moving Average"""
        if len(prices) < period:
            return None
            
        alpha = 2 / (period + 1)
        
        # Initialize EMA with SMA of first 'period' values
        sma = sum(prices[:period]) / period
        ema = sma
        
        # Calculate EMA for remaining values
        for price in prices[period:]:
            ema = alpha * price + (1 - alpha) * ema
            
        return ema
    
    def fetch_stock_data(self, symbol: str) -> Optional[Dict]:
        """Fetch daily stock data from Alpha Vantage API"""
        try:
            url = f'https://www.alphavantage.co/query'
            params = {
                'function': 'TIME_SERIES_DAILY',
                'symbol': symbol,
                'outputsize': 'full',
                'apikey': self.alpha_vantage_api_key
            }
            
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if 'Error Message' in data:
                logger.error(f"API Error for {symbol}: {data['Error Message']}")
                return None
                
            if 'Note' in data:
                logger.warning(f"API Rate limit reached: {data['Note']}")
                return None
                
            time_series = data.get('Time Series (Daily)', {})
            if not time_series:
                logger.error(f"No time series data found for {symbol}")
                return None
                
            # Convert to list of closing prices (most recent first)
            sorted_dates = sorted(time_series.keys(), reverse=True)
            prices = []
            for date in sorted_dates:
                close_price = float(time_series[date]['4. close'])
                prices.append(close_price)
                
            return {
                'symbol': symbol,
                'current_price': prices[0],
                'prices': prices[:250],  # Get last 250 days to ensure we have enough for 200 EMA
                'last_updated': sorted_dates[0]
            }
            
        except requests.RequestException as e:
            logger.error(f"Network error fetching data for {symbol}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {str(e)}")
            return None
    
    def check_ema_proximity(self, symbol: str, current_price: float, ema_200: float, threshold_pct: float = 2.0) -> Dict:
        """Check if stock price is near 200 EMA"""
        percentage_diff = abs((current_price - ema_200) / ema_200) * 100
        is_near_ema = percentage_diff <= threshold_pct
        
        direction = "above" if current_price > ema_200 else "below"
        
        return {
            'symbol': symbol,
            'current_price': current_price,
            'ema_200': ema_200,
            'percentage_diff': round(percentage_diff, 2),
            'is_near_ema': is_near_ema,
            'direction': direction,
            'threshold_pct': threshold_pct
        }
    
    def send_notification(self, alerts: List[Dict], topic_arn: str):
        """Send SNS notification for stocks near 200 EMA"""
        if not alerts:
            return
            
        message_lines = ["🔔 Stock EMA Alert 🔔\n"]
        message_lines.append("The following stocks are near their 200-day EMA:\n")
        
        for alert in alerts:
            symbol = alert['symbol']
            current_price = alert['current_price']
            ema_200 = alert['ema_200']
            percentage_diff = alert['percentage_diff']
            direction = alert['direction']
            
            message_lines.append(
                f"📈 {symbol}: ${current_price:.2f} ({percentage_diff}% {direction} 200 EMA: ${ema_200:.2f})"
            )
        
        message_lines.append(f"\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        message = "\n".join(message_lines)
        
        try:
            self.sns_client.publish(
                TopicArn=topic_arn,
                Message=message,
                Subject="Stock 200 EMA Alert"
            )
            logger.info(f"Notification sent for {len(alerts)} stocks")
        except Exception as e:
            logger.error(f"Failed to send notification: {str(e)}")
    
    def load_tickers(self) -> Dict:
        """Load ticker configuration"""
        try:
            with open('tickers.json', 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load tickers.json: {str(e)}")
            return {"tickers": [], "threshold_percentage": 2.0}
    
    def monitor_stocks(self, sns_topic_arn: str) -> Dict:
        """Main monitoring function"""
        config = self.load_tickers()
        tickers = config.get('tickers', [])
        threshold_pct = config.get('threshold_percentage', 2.0)
        
        alerts = []
        processed = []
        errors = []
        
        for ticker in tickers:
            logger.info(f"Processing {ticker}")
            
            stock_data = self.fetch_stock_data(ticker)
            if not stock_data:
                errors.append(f"Failed to fetch data for {ticker}")
                continue
                
            ema_200 = self.calculate_ema(stock_data['prices'], 200)
            if ema_200 is None:
                errors.append(f"Insufficient data to calculate 200 EMA for {ticker}")
                continue
                
            proximity_check = self.check_ema_proximity(
                ticker, 
                stock_data['current_price'], 
                ema_200, 
                threshold_pct
            )
            
            processed.append(proximity_check)
            
            if proximity_check['is_near_ema']:
                alerts.append(proximity_check)
        
        # Send notifications if there are alerts
        if alerts and sns_topic_arn:
            self.send_notification(alerts, sns_topic_arn)
        
        return {
            'alerts_sent': len(alerts),
            'stocks_processed': len(processed),
            'errors': errors,
            'alerts': alerts,
            'all_results': processed
        }

def lambda_handler(event, context):
    """AWS Lambda handler function"""
    try:
        # Get environment variables
        import os
        alpha_vantage_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
        sns_topic_arn = os.environ.get('SNS_TOPIC_ARN')
        
        if not alpha_vantage_key:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'ALPHA_VANTAGE_API_KEY environment variable not set'})
            }
        
        # Initialize monitor
        monitor = StockEMAMonitor()
        monitor.alpha_vantage_api_key = alpha_vantage_key
        
        # Run monitoring
        results = monitor.monitor_stocks(sns_topic_arn)
        
        logger.info(f"Monitoring complete: {results['alerts_sent']} alerts sent, {results['stocks_processed']} stocks processed")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Stock monitoring completed successfully',
                'results': results
            })
        }
        
    except Exception as e:
        logger.error(f"Lambda execution failed: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

if __name__ == "__main__":
    # For local testing
    import os
    os.environ['ALPHA_VANTAGE_API_KEY'] = 'your_api_key_here'
    os.environ['SNS_TOPIC_ARN'] = 'your_sns_topic_arn_here'
    
    result = lambda_handler({}, {})
    print(json.dumps(result, indent=2))