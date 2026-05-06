from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
import os

api_key = os.popen("grep ALPACA_API_KEY /root/hermes/.env | cut -d'=' -f2").read().strip()
api_secret = os.popen("grep ALPACA_API_SECRET /root/hermes/.env | cut -d'=' -f2").read().strip()
client = TradingClient(api_key, api_secret, paper=True)

# Get BTC position
try:
    pos = client.get_open_position("BTCUSD")
    qty = float(pos.qty)
    print(f"BTC position: {qty} shares")
    
    # Sell in chunks of 2 BTC
    chunk = 2.0
    while qty > 0:
        sell_qty = min(chunk, qty)
        print(f"  Selling {sell_qty} BTC...")
        order = MarketOrderRequest(
            symbol="BTCUSD",
            qty=sell_qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC
        )
        client.submit_order(order)
        qty -= sell_qty
    
    print("✅ BTC fully closed")
except Exception as e:
    print(f"No BTC position or error: {e}")
