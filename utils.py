import numpy as np
import matplotlib.pyplot as plt

def calculate_pop(delta):
    return round(1 - abs(delta), 4)

def calculate_ev(premium, capital, pop):
    max_loss = capital - (premium * 100)
    max_gain = premium * 100
    ev = (pop * max_gain) - ((1 - pop) * max_loss)
    return round(ev, 2)

def generate_pl_chart(strike, premium, opt_type="put"):
    prices = np.linspace(strike * 0.8, strike * 1.2, 100)
    if opt_type == "put":
        pl = np.where(prices < strike, (strike - prices) * 100 + premium * 100, premium * 100)
    else:  # call
        pl = np.where(prices > strike, (prices - strike) * 100 + premium * 100, premium * 100)

    fig, ax = plt.subplots()
    ax.plot(prices, pl, label='P/L')
    ax.axhline(0, color='black', linestyle='--', linewidth=1)
    ax.axvline(strike, color='red', linestyle='--', label='Strike Price')
    ax.set_title(f"Profit/Loss Diagram ({opt_type.upper()})")
    ax.set_xlabel("Stock Price at Expiration")
    ax.set_ylabel("Profit / Loss ($)")
    ax.legend()
    ax.grid(True)
    return fig
