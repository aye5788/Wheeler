import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
from utils import calculate_pop, calculate_ev, generate_pl_chart

# === Load Filtered Ticker Universe ===
@st.cache_data
def load_filtered_tickers():
    return pd.read_csv("filtered_universe_for_csp.csv")

# === API Setup ===
API_KEY = st.secrets["EODHD_API_KEY"]
BASE_URL = "https://eodhd.com/api/mp/unicornbay/options/contracts"

# === UI Layout ===
st.set_page_config(page_title="Wheel Strategy Screener", layout="wide")
st.title("📉 Wheel Strategy Screener")

# === Strategy Selection ===
opt_type = st.radio("🔘 Select Strategy", ["Cash-Secured Puts", "Covered Calls"], horizontal=True)
opt_type = "put" if "Put" in opt_type else "call"

# === Sidebar Filters ===
st.sidebar.header("🔧 Filters")
min_bid = st.sidebar.number_input("Minimum Bid ($)", value=0.30, step=0.01)
min_delta = st.sidebar.slider("Min Delta", 0.05, 0.50, 0.15)
max_delta = st.sidebar.slider("Max Delta", 0.20, 0.70, 0.40)
min_dte = st.sidebar.slider("Min DTE", 5, 30, 10)
max_dte = st.sidebar.slider("Max DTE", 15, 90, 60)
max_capital = st.sidebar.number_input("Max Capital per Contract ($)", value=1000.0, step=50.0)
sort_key = st.sidebar.selectbox("Sort by", ["Highest Annualized Yield", "Lowest EV", "Highest PoP"])

# === Ticker Input ===
single_ticker = st.text_input("🔐 Scan a single ticker (optional)", placeholder="e.g. AAPL")

if opt_type == "put":
    st.subheader("💰 Cash-Secured Puts")
else:
    st.subheader("📈 Covered Calls")

scan = st.button(f"▶️ Run {opt_type.upper()} Screener")

# === Fetch Function ===
def fetch_options_data(symbol, opt_type):
    params = {
        "filter[underlying_symbol]": symbol,
        "filter[type]": opt_type,
        "sort": "-exp_date",
        "page[limit]": 100,
        "fields[options-contracts]": "contract,strike,bid,ask,exp_date,delta,volatility,open_interest,volume,last",
        "api_token": API_KEY
    }
    try:
        response = requests.get(BASE_URL, params=params)
        if response.status_code != 200:
            return pd.DataFrame()
        data = response.json().get("data", [])
        df = pd.json_normalize(data)
        df["symbol"] = symbol
        return df
    except Exception:
        return pd.DataFrame()

# === Screener Logic ===
def screen_options(df, opt_type):
    df['attributes.bid'] = df['attributes.bid'].fillna(0)
    df['attributes.ask'] = df['attributes.ask'].fillna(0)
    df['mid'] = (df['attributes.bid'] + df['attributes.ask']) / 2
    df['capital_required'] = df['attributes.strike'] * 100

    df['DTE'] = (pd.to_datetime(df['attributes.exp_date']) - datetime.utcnow()).dt.days
    df['breakeven'] = df['attributes.strike'] - df['mid'] if opt_type == "put" else df['attributes.strike'] + df['mid']
    df['annualized_yield'] = (df['mid'] * 100) / df['capital_required'] * (365 / df['DTE'])
    df['yield_per_dollar'] = df['mid'] / df['attributes.strike']
    df['pop'] = df['attributes.delta'].apply(calculate_pop)
    df['ev'] = df.apply(lambda x: calculate_ev(x['mid'], x['capital_required'], x['pop']), axis=1)
    return df

# === Scan Handler ===
if scan:
    all_results = []
    tickers_df = load_filtered_tickers()
    if single_ticker:
        tickers_to_scan = [single_ticker] if single_ticker in tickers_df["code"].values else []
    else:
        tickers_to_scan = tickers_df["code"].tolist()[:10]

    for symbol in tickers_to_scan:
        with st.spinner(f"🔍 Fetching {symbol}..."):
            raw = fetch_options_data(symbol, opt_type)
            if raw.empty:
                continue
            processed = screen_options(raw, opt_type)

            filtered = processed[
                (processed['mid'] >= min_bid) &
                (processed['DTE'] >= min_dte) &
                (processed['DTE'] <= max_dte) &
                (processed['attributes.delta'].abs() >= min_delta) &
                (processed['attributes.delta'].abs() <= max_delta) &
                (processed['capital_required'] <= max_capital)
            ]
            if not filtered.empty:
                all_results.append(filtered)

    if all_results:
        result_df = pd.concat(all_results).reset_index(drop=True)
        display_cols = ["symbol", "contract", "strike", "mid", "breakeven", "DTE", "delta",
                        "iv", "oi", "volume", "capital_required", "annualized_yield", "yield_per_dollar"]
        st.success(f"✅ Screened {opt_type.upper()} Opportunities")
        st.dataframe(result_df[display_cols].sort_values(
            by="annualized_yield" if "Yield" in sort_key else "ev" if "EV" in sort_key else "pop",
            ascending=False
        ).head(15))

        st.subheader("📊 Trade Analysis (Top 5 Results)")
        for i, row in result_df.head(5).iterrows():
            fig = generate_pl_chart(row["strike"], row["mid"], opt_type)
            st.pyplot(fig)
            st.caption(f"PoP: {row['pop']}, EV: ${row['ev']}")
    else:
        st.warning("⚠️ No trades met the filter criteria.")

