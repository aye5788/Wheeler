import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import time

API_KEY = st.secrets["EODHD_API_KEY"]  # stored in .streamlit/secrets.toml
BASE_URL = "https://eodhd.com/api/mp/unicornbay/options/contracts"

# === Load Tickers ===
@st.cache_data
def load_tickers():
    df = pd.read_csv("filtered_universe_for_csp.csv")
    return df['code'].tolist()

# === API Call ===
def fetch_csp(symbol, limit=20):
    params = {
        "filter[underlying_symbol]": symbol,
        "filter[type]": "put",
        "sort": "exp_date",
        "page[limit]": limit,
        "fields[options-contracts]": (
            "contract,exp_date,strike,bid,ask,last,"
            "delta,volatility,open_interest,volume"
        ),
        "api_token": API_KEY
    }

    try:
        r = requests.get(BASE_URL, params=params)
        r.raise_for_status()
        data = r.json()
        df = pd.json_normalize(data['data'])
        df['symbol'] = symbol
        return df
    except Exception as e:
        st.warning(f"Error fetching {symbol}: {e}")
        return pd.DataFrame()

# === CSP Calculation ===
def calculate_metrics(df):
    today = pd.Timestamp(datetime.utcnow().date())
    df['exp_date'] = pd.to_datetime(df['attributes.exp_date'])
    df['DTE'] = (df['exp_date'] - today).dt.days
    df['mid'] = (df['attributes.bid'] + df['attributes.ask']) / 2
    df['capital_required'] = df['attributes.strike'] * 100
    df['breakeven'] = df['attributes.strike'] - df['mid']
    df['annualized_yield'] = (df['mid'] / df['attributes.strike']) * (365 / df['DTE'])
    df['yield_per_dollar'] = df['mid'] / df['capital_required']
    return df

# === Filter Logic ===
def apply_filters(df, user_settings):
    return df[
        (df['mid'] >= user_settings['min_bid']) &
        (df['DTE'] >= user_settings['min_dte']) &
        (df['DTE'] <= user_settings['max_dte']) &
        (df['attributes.delta'].abs() >= user_settings['min_delta']) &
        (df['attributes.delta'].abs() <= user_settings['max_delta']) &
        (df['capital_required'] <= user_settings['max_capital'])
    ]

# === Streamlit App ===
st.set_page_config("Wheel Strategy CSP Screener", layout="wide")
st.title("💸 Cash-Secured Put Screener (Wheel Strategy)")

tickers = load_tickers()

with st.sidebar:
    st.header("🔧 Filters")
    max_tickers = st.slider("Number of tickers to scan", 5, 50, 10)
    min_bid = st.number_input("Minimum Bid ($)", value=0.30, step=0.05)
    min_delta = st.slider("Min Delta", 0.05, 0.5, 0.15)
    max_delta = st.slider("Max Delta", 0.2, 0.7, 0.4)
    min_dte = st.slider("Min DTE", 5, 30, 10)
    max_dte = st.slider("Max DTE", 15, 90, 60)
    max_capital = st.number_input("Max Capital per Contract ($)", value=1000, step=50)
    sort_by = st.selectbox("Sort by", ["annualized_yield", "yield_per_dollar"])

user_settings = {
    "min_bid": min_bid,
    "min_delta": min_delta,
    "max_delta": max_delta,
    "min_dte": min_dte,
    "max_dte": max_dte,
    "max_capital": max_capital
}

results = []
for i, symbol in enumerate(tickers[:max_tickers]):
    st.write(f"📡 Fetching {symbol}...")
    raw_df = fetch_csp(symbol)
    if not raw_df.empty:
        processed = calculate_metrics(raw_df)
        filtered = apply_filters(processed, user_settings)
        results.append(filtered)
    time.sleep(1.2)

# === Final Output ===
if results:
    df_final = pd.concat(results).reset_index(drop=True)
    df_final = df_final.rename(columns={
        'attributes.contract': 'contract',
        'attributes.strike': 'strike',
        'attributes.delta': 'delta',
        'attributes.volatility': 'iv',
        'attributes.open_interest': 'oi',
        'attributes.volume': 'volume'
    })

    display_cols = [
        'symbol', 'contract', 'strike', 'mid', 'breakeven', 'DTE',
        'delta', 'iv', 'oi', 'volume', 'capital_required',
        'annualized_yield', 'yield_per_dollar'
    ]

    st.dataframe(df_final[display_cols].sort_values(by=sort_by, ascending=False), use_container_width=True)
else:
    st.warning("No results found. Try adjusting your filters.")
