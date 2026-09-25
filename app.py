import streamlit as st
import pandas as pd

st.set_page_config(page_title="Football Betting Research Lab", page_icon="⚽", layout="wide")

st.title("⚽ Football Betting Research Lab")
st.write("A transparent research dashboard for testing football prediction ideas.")

st.info("This first version is a safe demo using sample data. It does not place bets or guarantee profit.")

sample_data = pd.DataFrame(
    {
        "Home Team": ["Team A", "Team C", "Team E"],
        "Away Team": ["Team B", "Team D", "Team F"],
        "Home Win Probability": [0.52, 0.44, 0.61],
        "Draw Probability": [0.26, 0.30, 0.22],
        "Away Win Probability": [0.22, 0.26, 0.17],
    }
)

st.subheader("Sample probability estimates")
st.dataframe(sample_data, use_container_width=True, hide_index=True)

st.subheader("Next development stages")
st.markdown(
    """
    1. Add historical match results.
    2. Build a transparent baseline model.
    3. Add bookmaker odds and implied probabilities.
    4. Run time-ordered backtests.
    5. Measure calibration, ROI, variance, and drawdown.
    """
)
