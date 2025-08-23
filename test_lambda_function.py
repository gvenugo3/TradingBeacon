import pytest
import json
import os
from unittest.mock import Mock, patch, MagicMock, mock_open
from moto import mock_sns
import boto3
from datetime import datetime, date
import pandas as pd
import numpy as np

# Import the module to test
import lambda_function
from lambda_function import StockEMAMonitor, lambda_handler


class TestStockEMAMonitor:
    
    def setup_method(self):
        """Set up test fixtures"""
        self.monitor = StockEMAMonitor()
        
    def test_init(self):
        """Test StockEMAMonitor initialization"""
        monitor = StockEMAMonitor()
        assert monitor.sns_client is not None
        
    def test_calculate_ema_insufficient_data(self):
        """Test EMA calculation with insufficient data"""
        prices = [100.0, 101.0, 102.0]  # Only 3 prices, need 200
        result = self.monitor.calculate_ema(prices, 200)
        assert result is None
        
    def test_calculate_ema_exact_period(self):
        """Test EMA calculation with exactly enough data"""
        # Create 200 prices for testing
        prices = list(range(100, 300))  # 100 to 299, exactly 200 prices
        result = self.monitor.calculate_ema(prices, 200)
        assert result is not None
        assert isinstance(result, float)
        
    def test_calculate_ema_more_than_period(self):
        """Test EMA calculation with more data than period"""
        # Create 250 prices
        prices = [100.0] * 200 + [110.0] * 50  # 200 at 100, then 50 at 110
        result = self.monitor.calculate_ema(prices, 200)
        assert result is not None
        assert result > 100.0  # Should be higher due to recent higher prices
        assert result < 110.0  # But not as high as recent prices due to smoothing
        
    def test_calculate_ema_custom_period(self):
        """Test EMA calculation with custom period"""
        prices = list(range(1, 51))  # 1 to 50
        result_20 = self.monitor.calculate_ema(prices, 20)
        result_30 = self.monitor.calculate_ema(prices, 30)
        assert result_20 is not None
        assert result_30 is not None
        assert result_20 != result_30
        
    @patch('yfinance.Ticker')
    def test_fetch_stock_data_success(self, mock_ticker):
        """Test successful stock data fetching with Yahoo Finance"""
        # Create mock data
        dates = pd.date_range('2024-01-01', periods=250, freq='D')
        mock_hist = pd.DataFrame({
            'Close': [150.0 + i * 0.1 for i in range(250)]
        }, index=dates)
        
        mock_ticker_instance = Mock()
        mock_ticker_instance.history.return_value = mock_hist
        mock_ticker.return_value = mock_ticker_instance
        
        result = self.monitor.fetch_stock_data("AAPL")
        
        assert result is not None
        assert result["symbol"] == "AAPL"
        assert isinstance(result["current_price"], float)
        assert len(result["prices"]) == 250
        assert result["prices"][0] > result["prices"][-1]  # Most recent first
        assert isinstance(result["last_updated"], str)
        
        mock_ticker.assert_called_once_with("AAPL")
        mock_ticker_instance.history.assert_called_once_with(period="1y")
        
    @patch('yfinance.Ticker')
    def test_fetch_stock_data_empty_data(self, mock_ticker):
        """Test handling of empty data from Yahoo Finance"""
        mock_ticker_instance = Mock()
        mock_ticker_instance.history.return_value = pd.DataFrame()  # Empty DataFrame
        mock_ticker.return_value = mock_ticker_instance
        
        result = self.monitor.fetch_stock_data("INVALID")
        
        assert result is None
        
    @patch('yfinance.Ticker')
    def test_fetch_stock_data_exception(self, mock_ticker):
        """Test handling of Yahoo Finance exceptions"""
        mock_ticker_instance = Mock()
        mock_ticker_instance.history.side_effect = Exception("Network error")
        mock_ticker.return_value = mock_ticker_instance
        
        result = self.monitor.fetch_stock_data("AAPL")
        
        assert result is None
        
    @patch('yfinance.Ticker')
    def test_fetch_stock_data_no_close_prices(self, mock_ticker):
        """Test handling of data without close prices"""
        dates = pd.date_range('2024-01-01', periods=10, freq='D')
        mock_hist = pd.DataFrame({
            'Close': [np.nan] * 10  # All NaN values
        }, index=dates)
        
        mock_ticker_instance = Mock()
        mock_ticker_instance.history.return_value = mock_hist
        mock_ticker.return_value = mock_ticker_instance
        
        result = self.monitor.fetch_stock_data("AAPL")
        
        assert result is None
        
    def test_check_ema_proximity_near_above(self):
        """Test proximity check when price is near EMA (above)"""
        result = self.monitor.check_ema_proximity("AAPL", 102.0, 100.0, 2.5)
        
        assert result["symbol"] == "AAPL"
        assert result["current_price"] == 102.0
        assert result["ema_200"] == 100.0
        assert result["percentage_diff"] == 2.0
        assert result["is_near_ema"] is True
        assert result["direction"] == "above"
        assert result["threshold_pct"] == 2.5
        
    def test_check_ema_proximity_near_below(self):
        """Test proximity check when price is near EMA (below)"""
        result = self.monitor.check_ema_proximity("MSFT", 98.0, 100.0, 2.5)
        
        assert result["symbol"] == "MSFT"
        assert result["current_price"] == 98.0
        assert result["ema_200"] == 100.0
        assert result["percentage_diff"] == 2.0
        assert result["is_near_ema"] is True
        assert result["direction"] == "below"
        
    def test_check_ema_proximity_far_above(self):
        """Test proximity check when price is far from EMA (above)"""
        result = self.monitor.check_ema_proximity("GOOGL", 105.0, 100.0, 2.0)
        
        assert result["percentage_diff"] == 5.0
        assert result["is_near_ema"] is False
        assert result["direction"] == "above"
        
    def test_check_ema_proximity_far_below(self):
        """Test proximity check when price is far from EMA (below)"""
        result = self.monitor.check_ema_proximity("TSLA", 95.0, 100.0, 2.0)
        
        assert result["percentage_diff"] == 5.0
        assert result["is_near_ema"] is False
        assert result["direction"] == "below"
        
    @mock_sns
    def test_send_notification_success(self):
        """Test successful SNS notification"""
        # Create SNS topic
        sns = boto3.client("sns", region_name="us-east-1")
        topic = sns.create_topic(Name="test-topic")
        topic_arn = topic["TopicArn"]
        
        # Create mock alerts
        alerts = [
            {
                "symbol": "AAPL",
                "current_price": 150.0,
                "ema_200": 148.0,
                "percentage_diff": 1.35,
                "direction": "above"
            },
            {
                "symbol": "MSFT",
                "current_price": 298.0,
                "ema_200": 300.0,
                "percentage_diff": 0.67,
                "direction": "below"
            }
        ]
        
        # Mock the SNS client in our monitor
        with patch.object(self.monitor, 'sns_client', sns):
            self.monitor.send_notification(alerts, topic_arn)
        
        # Verify message was sent (moto doesn't provide easy way to check message content)
        # But we can verify no exceptions were raised
        
    def test_send_notification_no_alerts(self):
        """Test notification with empty alerts list"""
        with patch.object(self.monitor.sns_client, 'publish') as mock_publish:
            self.monitor.send_notification([], "arn:aws:sns:us-east-1:123456789:test")
            mock_publish.assert_not_called()
            
    def test_send_notification_sns_error(self):
        """Test handling of SNS publish error"""
        alerts = [
            {
                "symbol": "AAPL",
                "current_price": 150.0,
                "ema_200": 148.0,
                "percentage_diff": 1.35,
                "direction": "above"
            }
        ]
        
        with patch.object(self.monitor.sns_client, 'publish') as mock_publish:
            mock_publish.side_effect = Exception("SNS Error")
            # Should not raise exception, just log error
            self.monitor.send_notification(alerts, "test-topic-arn")
            
    def test_load_tickers_success(self):
        """Test successful loading of tickers configuration"""
        mock_config = {
            "tickers": ["AAPL", "MSFT", "GOOGL"],
            "threshold_percentage": 2.5
        }
        
        with patch("builtins.open", mock_open(read_data=json.dumps(mock_config))):
            result = self.monitor.load_tickers()
            
        assert result == mock_config
        assert result["tickers"] == ["AAPL", "MSFT", "GOOGL"]
        assert result["threshold_percentage"] == 2.5
        
    def test_load_tickers_file_not_found(self):
        """Test handling of missing tickers file"""
        with patch("builtins.open", side_effect=FileNotFoundError()):
            result = self.monitor.load_tickers()
            
        assert result == {"tickers": [], "threshold_percentage": 2.0}
        
    def test_load_tickers_invalid_json(self):
        """Test handling of invalid JSON in tickers file"""
        with patch("builtins.open", mock_open(read_data="invalid json")):
            result = self.monitor.load_tickers()
            
        assert result == {"tickers": [], "threshold_percentage": 2.0}
        
    @patch('lambda_function.StockEMAMonitor.send_notification')
    @patch('lambda_function.StockEMAMonitor.check_ema_proximity')
    @patch('lambda_function.StockEMAMonitor.calculate_ema')
    @patch('lambda_function.StockEMAMonitor.fetch_stock_data')
    @patch('lambda_function.StockEMAMonitor.load_tickers')
    def test_monitor_stocks_success_with_alerts(self, mock_load_tickers, mock_fetch_data,
                                               mock_calc_ema, mock_check_proximity, mock_send_notification):
        """Test successful monitoring with alerts generated"""
        # Setup mocks
        mock_load_tickers.return_value = {
            "tickers": ["AAPL", "MSFT"],
            "threshold_percentage": 2.0
        }
        
        mock_fetch_data.side_effect = [
            {
                "symbol": "AAPL",
                "current_price": 150.0,
                "prices": [150.0] * 250,
                "last_updated": "2025-01-15"
            },
            {
                "symbol": "MSFT",
                "current_price": 300.0,
                "prices": [300.0] * 250,
                "last_updated": "2025-01-15"
            }
        ]
        
        mock_calc_ema.side_effect = [148.0, 305.0]
        
        mock_check_proximity.side_effect = [
            {
                "symbol": "AAPL",
                "current_price": 150.0,
                "ema_200": 148.0,
                "percentage_diff": 1.35,
                "is_near_ema": True,
                "direction": "above",
                "threshold_pct": 2.0
            },
            {
                "symbol": "MSFT",
                "current_price": 300.0,
                "ema_200": 305.0,
                "percentage_diff": 1.64,
                "is_near_ema": True,
                "direction": "below",
                "threshold_pct": 2.0
            }
        ]
        
        result = self.monitor.monitor_stocks("test-topic-arn")
        
        assert result["alerts_sent"] == 2
        assert result["stocks_processed"] == 2
        assert len(result["errors"]) == 0
        assert len(result["alerts"]) == 2
        assert len(result["all_results"]) == 2
        
        mock_send_notification.assert_called_once()
        
    @patch('lambda_function.StockEMAMonitor.fetch_stock_data')
    @patch('lambda_function.StockEMAMonitor.load_tickers')
    def test_monitor_stocks_fetch_failure(self, mock_load_tickers, mock_fetch_data):
        """Test monitoring when stock data fetch fails"""
        mock_load_tickers.return_value = {
            "tickers": ["INVALID"],
            "threshold_percentage": 2.0
        }
        
        mock_fetch_data.return_value = None
        
        result = self.monitor.monitor_stocks("test-topic-arn")
        
        assert result["alerts_sent"] == 0
        assert result["stocks_processed"] == 0
        assert len(result["errors"]) == 1
        assert "Failed to fetch data for INVALID" in result["errors"][0]
        
    @patch('lambda_function.StockEMAMonitor.calculate_ema')
    @patch('lambda_function.StockEMAMonitor.fetch_stock_data')
    @patch('lambda_function.StockEMAMonitor.load_tickers')
    def test_monitor_stocks_insufficient_ema_data(self, mock_load_tickers, mock_fetch_data, mock_calc_ema):
        """Test monitoring when insufficient data for EMA calculation"""
        mock_load_tickers.return_value = {
            "tickers": ["AAPL"],
            "threshold_percentage": 2.0
        }
        
        mock_fetch_data.return_value = {
            "symbol": "AAPL",
            "current_price": 150.0,
            "prices": [150.0] * 50,  # Only 50 days, need 200
            "last_updated": "2025-01-15"
        }
        
        mock_calc_ema.return_value = None
        
        result = self.monitor.monitor_stocks("test-topic-arn")
        
        assert result["alerts_sent"] == 0
        assert result["stocks_processed"] == 0
        assert len(result["errors"]) == 1
        assert "Insufficient data to calculate 200 EMA for AAPL" in result["errors"][0]


class TestLambdaHandler:
    
    @patch('lambda_function.StockEMAMonitor.monitor_stocks')
    def test_lambda_handler_success(self, mock_monitor_stocks):
        """Test successful Lambda handler execution"""
        mock_monitor_stocks.return_value = {
            "alerts_sent": 2,
            "stocks_processed": 5,
            "errors": [],
            "alerts": [],
            "all_results": []
        }
        
        result = lambda_handler({}, {})
        
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["message"] == "Stock monitoring completed successfully"
        assert body["results"]["alerts_sent"] == 2
        assert body["results"]["stocks_processed"] == 5
        
    @patch('lambda_function.StockEMAMonitor.monitor_stocks')
    def test_lambda_handler_monitoring_exception(self, mock_monitor_stocks):
        """Test Lambda handler when monitoring raises exception"""
        mock_monitor_stocks.side_effect = Exception("Monitoring failed")
        
        result = lambda_handler({}, {})
        
        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "Monitoring failed" in body["error"]
        
    @patch.dict(os.environ, {"SNS_TOPIC_ARN": "test_arn"})
    @patch('lambda_function.StockEMAMonitor')
    def test_lambda_handler_with_sns_topic(self, mock_monitor_class):
        """Test Lambda handler with SNS topic configured"""
        mock_monitor_instance = Mock()
        mock_monitor_class.return_value = mock_monitor_instance
        mock_monitor_instance.monitor_stocks.return_value = {
            "alerts_sent": 0,
            "stocks_processed": 0,
            "errors": [],
            "alerts": [],
            "all_results": []
        }
        
        lambda_handler({}, {})
        
        mock_monitor_instance.monitor_stocks.assert_called_once_with("test_arn")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=lambda_function", "--cov-report=html", "--cov-report=term-missing"])