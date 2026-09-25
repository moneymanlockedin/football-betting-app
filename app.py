import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="Football Betting Research Lab",
    page_icon="⚽",
    layout="wide",
)

st.title("⚽ Football Betting Research Lab")
st.write("A transparent research dashboard for exploring football results and prediction ideas.")

st.info(
    "This is a research tool using historical data. It does not place bets or guarantee profit. "
    "Statistics describe past results and are not certain predictions."
)

st.header("1. Upload historical match results")
st.write(
    "Upload a CSV containing match results. The easiest format is the standard football-data format "
    "with these columns: Date, HomeTeam, AwayTeam, FTHG, FTAG, FTR."
)

sample_csv = "Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n2025-08-16,Arsenal,Leeds,2,0,H\n2025-08-17,Chelsea,Fulham,1,1,D\n2025-08-18,Liverpool,Newcastle,3,1,H\n"
st.download_button(
    "Download example CSV template",
    data=sample_csv,
    file_name="football_results_template.csv",
    mime="text/csv",
)

uploaded_file = st.file_uploader("Choose a CSV file", type=["csv"])

if uploaded_file is None:
    st.warning("Upload a CSV file to begin analysing your own historical results.")
    st.subheader("Required columns")
    st.code("Date, HomeTeam, AwayTeam, FTHG, FTAG, FTR")
    st.stop()

try:
    matches = pd.read_csv(uploaded_file)
except Exception as error:
    st.error(f"The CSV could not be read: {error}")
    st.stop()

required_columns = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]
missing_columns = [column for column in required_columns if column not in matches.columns]

if missing_columns:
    st.error("Your CSV is missing these required columns: " + ", ".join(missing_columns))
    st.write("Columns found in your file:", ", ".join(matches.columns.astype(str)))
    st.stop()

matches = matches[required_columns].copy()

matches["Date"] = pd.to_datetime(matches["Date"], errors="coerce", dayfirst=True)
matches["FTHG"] = pd.to_numeric(matches["FTHG"], errors="coerce")
matches["FTAG"] = pd.to_numeric(matches["FTAG"], errors="coerce")
matches["FTR"] = matches["FTR"].astype(str).str.upper().str.strip()

validation_errors = []

if matches["Date"].isna().any():
    validation_errors.append("Some Date values could not be understood.")
if matches[["FTHG", "FTAG"]].isna().any().any():
    validation_errors.append("Some home or away goal values are missing or invalid.")
if (matches[["FTHG", "FTAG"]] < 0).any().any():
    validation_errors.append("Goals cannot be negative.")
if not matches["FTR"].isin(["H", "D", "A"]).all():
    validation_errors.append("FTR must contain only H (home win), D (draw), or A (away win).")
if (matches["HomeTeam"].astype(str).str.strip() == "").any() or (
    matches["AwayTeam"].astype(str).str.strip() == ""
).any():
    validation_errors.append("HomeTeam and AwayTeam cannot be blank.")

if validation_errors:
    st.error("Please fix the following validation issues:")
    for error in validation_errors:
        st.write(f"- {error}")
    st.stop()

matches = matches.dropna(subset=["Date", "FTHG", "FTAG"]).copy()
matches["FTHG"] = matches["FTHG"].astype(int)
matches["FTAG"] = matches["FTAG"].astype(int)
matches["TotalGoals"] = matches["FTHG"] + matches["FTAG"]
matches["BTTS"] = (matches["FTHG"] > 0) & (matches["FTAG"] > 0)

st.success(f"Validation passed: {len(matches):,} matches loaded.")

st.header("2. Dataset overview")
metric_1, metric_2, metric_3, metric_4 = st.columns(4)
metric_1.metric("Matches", f"{len(matches):,}")
metric_2.metric("Teams", f"{pd.unique(matches[['HomeTeam', 'AwayTeam']].values.ravel()).size:,}")
metric_3.metric("Average goals", f"{matches['TotalGoals'].mean():.2f}")
metric_4.metric("Both teams scored", f"{matches['BTTS'].mean() * 100:.1f}%")

st.subheader("Recent uploaded matches")
st.dataframe(
    matches.sort_values("Date", ascending=False).head(25),
    use_container_width=True,
    hide_index=True,
)

st.header("3. Result breakdown")
result_counts = matches["FTR"].value_counts().reindex(["H", "D", "A"], fill_value=0)
result_labels = {
    "H": "Home wins",
    "D": "Draws",
    "A": "Away wins",
}
result_breakdown = pd.DataFrame(
    {
        "Result": [result_labels[key] for key in result_counts.index],
        "Matches": result_counts.values,
        "Percentage": (result_counts.values / len(matches) * 100).round(1),
    }
)
st.dataframe(result_breakdown, use_container_width=True, hide_index=True)

st.header("4. Team summary")
team_names = sorted(pd.unique(matches[["HomeTeam", "AwayTeam"]].values.ravel()))
selected_team = st.selectbox("Choose a team", team_names)

home_matches = matches[matches["HomeTeam"] == selected_team]
away_matches = matches[matches["AwayTeam"] == selected_team]

team_games = len(home_matches) + len(away_matches)
team_wins = int((home_matches["FTR"] == "H").sum() + (away_matches["FTR"] == "A").sum())
team_draws = int((home_matches["FTR"] == "D").sum() + (away_matches["FTR"] == "D").sum())
team_losses = team_games - team_wins - team_draws
team_goals_for = int(home_matches["FTHG"].sum() + away_matches["FTAG"].sum())
team_goals_against = int(home_matches["FTAG"].sum() + away_matches["FTHG"].sum())

team_metric_1, team_metric_2, team_metric_3, team_metric_4 = st.columns(4)
team_metric_1.metric("Games", team_games)
team_metric_2.metric("Wins", team_wins)
team_metric_3.metric("Draws", team_draws)
team_metric_4.metric("Losses", team_losses)

st.write(
    f"**{selected_team} goals:** {team_goals_for} scored, "
    f"{team_goals_against} conceded, "
    f"{team_goals_for / team_games:.2f} scored per game."
)

st.caption("Next stage: add team-form calculations, bookmaker odds, and time-ordered backtesting.")
