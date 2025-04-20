import streamlit as st
import pandas as pd
import requests
import math
import time
from utils import (
    get_filtered_universe,
    fetch_option_chain,
    apply_filters,
    calculate_metrics,
    plot_trade_pnl_chart
)

st.set_page_config(page_title="Wheel Strategy Screener", layout="wide")
st.title("📊 Wheel Strategy Screener")

# Strategy selection
opt_type = st.radio("Select Strategy", ["Cash-Secured Puts", "Covered Calls"], horizontal=True)
opt_type = "put" if opt_type == "Cash-Secured Puts" else "call"

# Ticker override
single_ticker = st.text_input("🔐 Scan a single ticker (optional)", placeholder="e.g. AAPL")

# Sidebar Filters
with st.sidebar:
    st.header("🛠 Filters")
    max_tickers = st.slider("Number of tickers to scan", 5, 50, 10, key="max_tickers")
    min_bid = st.number_input("Minimum Bid ($)", value=0.30, step=0.01, key="min_bid")
    min_delta = st.slider("Min Delta", 0.05, 0.50, 0.15, key="min_delta")
    max_delta = st.slider("Max Delta", 0.20, 0.70, 0.40, key="max_delta")
    min_dte = st.slider("Min DTE", 5, 30, 10, key="min_dte")
    max_dte = st.slider("Max DTE", 15, 90, 60, key="max_dte")
    max_capital = st.number_input("Max Capital per Contract ($)", value=1000.0, step=50.0, key="max_capital")
    sort_by = st.selectbox("Sort by", ["Highest Annualized Yield", "Highest Yield per Dollar"], key="sort_by")

# Run Screener
btn_label = "Run PUT Screener" if opt_type == "put" else "Run CALL Screener"
if st.button(f"🚀 {btn_label}"):
    with st.spinner(f"📡 Fetching {single_ticker or 'tickers'}..."):
        tickers = [single_ticker.upper()] if single_ticker else get_filtered_universe(max_tickers)
        results = []

        for i, ticker in enumerate(tickers, 1):
            st.write(f"📈 [{i}/{len(tickers)}] Fetching {ticker}...")
            try:
                raw_df = fetch_option_chain(ticker, opt_type)
                if raw_df.empty:
                    continue

                processed = calculate_metrics(raw_df, opt_type=opt_type)
                processed['symbol'] = ticker
                results.append(processed)
                time.sleep(1.2)  # throttle to stay API-safe

            except Exception as e:
                st.warning(f"⚠️ Error with {ticker}: {e}")

        if results:
            df_final = pd.concat(results).reset_index(drop=True)
            df_final = df_final.rename(columns={
                'attributes.contract': 'contract',
                'attributes.strike': 'strike',
                'attributes.delta': 'delta',
                'attributes.volatility': 'iv',
                'attributes.open_interest': 'oi',
                'attributes.volume': 'volume',
            })

            df_final['delta'] = df_final['delta'].fillna(0)
            df_final['capital_required'] = df_final['strike'] * 100
            df_final['mid'] = (df_final['attributes.bid'].fillna(0) + df_final['attributes.ask'].fillna(0)) / 2
            df_final['breakeven'] = (
                df_final['strike'] - df_final['mid']
                if opt_type == 'put'
                else df_final['strike'] + df_final['mid']
            )
            df_final['annualized_yield'] = (df_final['mid'] / df_final['capital_required']) * (365 / df_final['DTE']) * 100
            df_final['yield_per_dollar'] = df_final['mid'] / df_final['capital_required']

            user_filters = {
                "min_bid": min_bid,
                "min_delta": min_delta,
                "max_delta": max_delta,
                "min_dte": min_dte,
                "max_dte": max_dte,
                "max_capital": max_capital
            }

            df_filtered = apply_filters(df_final, user_filters)

            if not df_filtered.empty:
                sort_col = "annualized_yield" if sort_by == "Highest Annualized Yield" else "yield_per_dollar"
                df_filtered = df_filtered.sort_values(by=sort_col, ascending=False)

                st.success(f"✅ Screened {len(df_filtered)} {opt_type.upper()} Opportunities")
                st.dataframe(df_filtered[[
                    "symbol", "contract", "strike", "mid", "breakeven", "DTE",
                    "delta", "iv", "oi", "volume", "capital_required",
                    "annualized_yield", "yield_per_dollar"
                ]])

                st.subheader("📊 Trade Analysis (Top 5 Results)")
                for _, row in df_filtered.head(5).iterrows():
                    st.markdown(f"**{row['symbol']} - {row['contract']}**")
                    plot_trade_pnl_chart(
                        option_type=opt_type,
                        strike=row['strike'],
                        premium=row['mid'],
                        underlying_price=row['breakeven'] if opt_type == 'put' else row['strike'],
                        capital_required=row['capital_required'],
                        DTE=row['DTE'],
                        iv=row.get('iv', 0.3),
                        delta=row.get('delta', 0.0)
                    )
                    st.markdown("---")

            else:
                st.warning("⚠️ No trades passed the filters. Try adjusting bid, delta, or capital limits.")
        else:
            st.error("❌ No valid contracts fetched. Try a different ticker or less restrictive filters.")
