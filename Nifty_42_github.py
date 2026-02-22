import telebot
import pandas as pd
import yfinance as yf
import requests
import time
import os
from datetime import datetime
import pytz

# ─── CONFIG — Reads from GitHub Secrets automatically ───
BOT_TOKEN = os.environ.get("8024029263:AAFr7KRKABPSRNynvaKwL-RBlp4X4hJtOyA")
CHAT_ID   = os.environ.get("663364539")
# ────────────────────────────────────────────────────────

IST = pytz.timezone("Asia/Kolkata")
bot = telebot.TeleBot(BOT_TOKEN)

# ── 1. MARKET HOURS CHECK ────────────────────────────
def is_market_open():
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    start = now.replace(hour=9,  minute=30, second=0, microsecond=0)
    end   = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return start <= now <= end

# ── 2. NSE OPTION CHAIN ──────────────────────────────
def get_oi_levels():
    try:
        headers = {
            "User-Agent"     : "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer"        : "https://www.nseindia.com/"
        }
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        time.sleep(2)

        url  = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
        resp = session.get(url, headers=headers, timeout=10)
        data = resp.json()

        records = data['records']['data']
        df      = pd.DataFrame(records)

        df['CE_OI'] = df['CE'].apply(
            lambda x: x.get('openInterest', 0) if isinstance(x, dict) else 0
        )
        df['PE_OI'] = df['PE'].apply(
            lambda x: x.get('openInterest', 0) if isinstance(x, dict) else 0
        )

        support    = int(df.loc[df['PE_OI'].idxmax(), 'strikePrice'])
        resistance = int(df.loc[df['CE_OI'].idxmax(), 'strikePrice'])
        return support, resistance

    except Exception as e:
        print(f"OI error: {e}")
        return None, None

# ── 3. PRICE + 42 EMA ────────────────────────────────
def get_price_and_ema():
    try:
        data  = yf.download('^NSEI', interval='15m', period='5d', progress=False)
        close = data['Close'].dropna()
        open_ = data['Open'].dropna()

        price  = round(float(close.iloc[-1]), 1)
        open_p = round(float(open_.iloc[-1]),  1)
        high   = round(float(data['High'].dropna().iloc[-1]), 1)
        low    = round(float(data['Low'].dropna().iloc[-1]),  1)
        ema42  = round(float(close.ewm(span=42, adjust=False).mean().iloc[-1]), 1)

        return price, open_p, high, low, ema42

    except Exception as e:
        print(f"Price error: {e}")
        return None, None, None, None, None

# ── 4. MAIN — RUN ONCE AND EXIT ──────────────────────
def main():
    if not is_market_open():
        print(f"Market closed at {datetime.now(IST).strftime('%H:%M')} — exiting.")
        return   # ← just exit, no message sent on weekends/after hours

    support, resistance             = get_oi_levels()
    price, open_p, high, low, ema42 = get_price_and_ema()

    if None in [support, resistance, price, ema42]:
        bot.send_message(CHAT_ID, "⚠️ Data fetch failed. Will retry in 15 min.")
        return

    candle    = "🟩 Bullish" if price >= open_p else "🟥 Bearish"
    open_sig  = "🟢 Opened ABOVE" if open_p > ema42 else "🔴 Opened BELOW"
    price_sig = "🟢 Price ABOVE"  if price  > ema42 else "🔴 Price BELOW"
    now       = datetime.now(IST).strftime("%H:%M")

    msg = f"""
📊 *NIFTY 50 | {now} IST (15 Min)*
━━━━━━━━━━━━━━━━━━━━

🕯 Candle  : {candle}
🔓 Open    : {open_p}
📈 High    : {high}
📉 Low     : {low}
💰 Close   : {price}

📌 *OI Based Levels*
🛡 Support    : *{support}*  (Max PE OI)
🧱 Resistance : *{resistance}*  (Max CE OI)

📐 *42 EMA* : {ema42}
{open_sig} 42 EMA at open
{price_sig} 42 EMA now
━━━━━━━━━━━━━━━━━━━━
"""
    bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
    print(f"[{now}] ✅ Alert sent! Script exiting now.")

# Script runs once and exits automatically
main()
