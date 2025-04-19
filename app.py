import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import time

# Custom logic from utils.py
from utils import calculate_pop, calculate_ev, generate_pl_chart

API_KEY = st.secrets["EODHD_API_KEY"]
BASE_URL = "https://eodhd.com/api/mp/unicornbay/options/contracts"

@st.cache_data
def load_tickers():
    df = pd.read_csv("filtered_universe_for_csp.csv")
    return df['code'].tolist()

def fetch_options(symbol, opt_type="put", limit=20):
    params = {
        "filter[underlying_symbol]": symbol,
        "filter[type]": opt_type,
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

def calculate_metrics(df):
    today = pd.Timestamp(datetime.utcnow().date())
    df['exp_date'] = pd.to_datetime(df['attributes.exp_date'])
    df['DTE'] = (df['exp_date'] - today).dt.days
    df['mid'] = (df['attributes.bid'] + df['attributes.ask']) / 2
    df['capital_required'] = df['attributes.strike'] * 100
    df['breakeven'] = df['attributes.strike'] - df['mid'] if df['attributes.type'][0] == 'put' else df['attributes.strike'] + df['mid']
    df['annualized_yield'] = (df['mid'] / df['attributes.strike']) * (365 / df['DTE'])
    df['yield_per_dollar'] = df['mid'] / df['capital_required']
    return df

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
st.set_page_config("Wheel Strategy Screener", layout="wide")
st.title("🔄 Wheel Strategy Screener")

tickers = load_tickers()

# Toggle between PUT and CALL mode
selected_tab = st.radio("📌 Select Strategy", ["Cash-Secured Puts", "Covered Calls"], horizontal=True)
opt_type = "put" if selected_tab == "Cash-Secured Puts" else "call"

# Sidebar filters — rendered once and uniquely keyed
with st.sidebar:
    st.header("🔧 Filters")
    max_tickers = st.slider("Number of tickers to scan", 5, 50, 10, key=f"max_tickers_{opt_type}")
    min_bid = st.number_input("Minimum Bid ($)", value=0.30, step=0.05, key=f"min_bid_{opt_type}")
    min_delta = st.slider("Min Delta", 0.05, 0.5, 0.15, key=f"min_delta_{opt_type}")
    max_delta = st.slider("Max Delta", 0.2, 0.7, 0.4, key=f"max_delta_{opt_type}")
    min_dte = st.slider("Min DTE", 5, 30, 10, key=f"min_dte_{opt_type}")
    max_dte = st.slider("Max DTE", 15, 90, 60, key=f"max_dte_{opt_type}")
    max_capital = st.number_input("Max Capital per Contract ($)", value=1000.0, min_value=0.0, step=1.0,
                                  format="%.2f", key=f"max_cap_{opt_type}")

    sort_options = {
        "Highest Annualized Yield": "annualized_yield",
        "Most Yield per Dollar": "yield_per_dollar",
        "Lowest Breakeven": "breakeven",
        "Soonest Expiration": "DTE",
        "Smallest Capital Required": "capital_required",
        "Highest Open Interest": "oi",
        "Highest Volume": "volume",
        "Closest to ATM (Delta)": "delta"
    }
    sort_label = st.selectbox("Sort by", list(sort_options.keys()), key=f"sort_{opt_type}")
    sort_by = sort_options[sort_label]

user_settings = {
    "min_bid": min_bid,
    "min_delta": min_delta,
    "max_delta": max_delta,
    "min_dte": min_dte,
    "max_dte": max_dte,
    "max_capital": max_capital
}

# UI and logic
st.markdown(f"### {'📉' if opt_type == 'put' else '📈'} {selected_tab}")
single_ticker = st.text_input("📍 Scan a single ticker (optional)", placeholder="e.g. AAPL",
                              key=f"single_ticker_{opt_type}").strip().upper()

if st.button(f"📡 Run {opt_type.upper()} Screener", key=f"run_btn_{opt_type}"):
    results = []
    symbols_to_scan = [single_ticker] if single_ticker else tickers[:max_tickers]

    if single_ticker and single_ticker not in tickers:
        st.warning(f"{single_ticker} is not in your filtered universe.")
    else:
        for symbol in symbols_to_scan:
            st.write(f"📡 Fetching {symbol}...")
            raw_df = fetch_options(symbol, opt_type=opt_type)
            if not raw_df.empty:
                processed = calculate_metrics(raw_df)
                filtered = apply_filters(processed, user_settings)
                results.append(filtered)
            else:
                st.caption(f"⚠️ No option data for {symbol}")
            time.sleep(1.2)

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

            ascending = sort_by in ['breakeven', 'DTE', 'capital_required']
            st.subheader(f"✅ Screened {opt_type.upper()} Opportunities")
            st.dataframe(
                df_final[display_cols].sort_values(by=sort_by, ascending=ascending),
                use_container_width=True
            )

            st.subheader("📊 Trade Analysis (Top 5 Results)")
            for _, row in df_final.head(5).iterrows():
                with st.expander(f"{row['symbol']} {row['strike']} @ ${row['mid']:.2f}"):
                    pop = calculate_pop(row['delta'])
                    ev = calculate_ev(row['mid'], row['capital_required'], pop)

                    st.write(f"**PoP**: `{pop * 100:.1f}%`")
                    st.write(f"**Expected Value (EV)**: `${ev}`")

                    st.pyplot(generate_pl_chart(row['strike'], row['mid'], opt_type=opt_type))
        else:
            st.warning(f"No {opt_type.upper()} candidates met your filter criteria.")


