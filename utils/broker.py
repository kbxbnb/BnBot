import os, requests

def get_alpaca_keys():
    return os.getenv("ALPACA_API_KEY",""), os.getenv("ALPACA_SECRET_KEY","")

def get_account_balance_alpaca():
    api, secret = get_alpaca_keys()
    if not api or not secret:
        return None
    url = "https://paper-api.alpaca.markets/v2/account"
    headers = {"APCA-API-KEY-ID": api, "APCA-API-SECRET-KEY": secret}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        # 'cash' & 'buying_power' are strings; convert to float
        cash = float(data.get("cash", 0))
        buying_power = float(data.get("buying_power", 0))
        equity = float(data.get("equity", 0))
        return {"cash": cash, "buying_power": buying_power, "equity": equity}
    except Exception:
        return None
