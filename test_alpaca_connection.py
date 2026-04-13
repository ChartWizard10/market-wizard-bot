import requests
import json

ALPACA_BASE_URL = "https://paper-api.alpaca.markets/v2"
ALPACA_API_KEY = "PKFTEQ7ZL36HG5JF653FRDV22W"
ALPACA_SECRET_KEY = "4BxY7Y1endrPKNWtbQtooD9Yibm1CAVzdYKbCZwM4nuD"

HEADERS = {
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
    "Content-Type": "application/json"
}

def get_account():
    resp = requests.get(f"{ALPACA_BASE_URL}/account", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()

def place_order(symbol, qty, side="buy", order_type="market", time_in_force="day"):
    payload = {
        "symbol": symbol,
        "qty": str(qty),
        "side": side,
        "type": order_type,
        "time_in_force": time_in_force
    }
    resp = requests.post(f"{ALPACA_BASE_URL}/orders", headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()

if __name__ == "__main__":
    print("=== Alpaca Paper Trading Connection Test ===\n")

    # Check account
    account = get_account()
    print(f"Account ID:     {account['id']}")
    print(f"Status:         {account['status']}")
    print(f"Buying Power:   ${float(account['buying_power']):,.2f}")
    print(f"Portfolio Value:${float(account['portfolio_value']):,.2f}\n")

    # Place order: 1 share of AAPL
    print("Placing order: BUY 1 share of AAPL (market order)...")
    order = place_order("AAPL", 1)
    print(f"\nOrder placed successfully!")
    print(f"  Order ID:  {order['id']}")
    print(f"  Symbol:    {order['symbol']}")
    print(f"  Side:      {order['side']}")
    print(f"  Qty:       {order['qty']}")
    print(f"  Type:      {order['type']}")
    print(f"  Status:    {order['status']}")
    print(f"  Created:   {order['created_at']}")
