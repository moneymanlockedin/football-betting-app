import io
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Football Betting Research Lab", page_icon="⚽", layout="wide")

st.title("⚽ Football Betting Research Lab")
st.write("A transparent dashboard for exploring football results, team form and match statistics.")
st.info("Research only: this app does not place bets or guarantee profit. Historical patterns are not certain predictions.")

CORE_COLUMNS = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]
STAT_PAIRS = {
    "Corners": ("HC", "AC"),
    "Shots": ("HS", "AS"),
    "Shots on target": ("HST", "AST"),
    "Yellow cards": ("HY", "AY"),
    "Red cards": ("HR", "AR"),
    "Possession %": ("HPoss", "APoss"),
    "Fouls": ("HF", "AF"),
    "Offsides": ("HO", "AO"),
    "Saves": ("HSave", "ASave"),
    "Passes": ("HPass", "APass"),
    "Expected goals": ("HxG", "AxG"),
}

# Common football-data.co.uk column names are already compatible with the app.
LEAGUES = {
    "England Premier League": "E0",
    "England Championship": "E1",
    "England League One": "E2",
    "England League Two": "E3",
    "Scotland Premiership": "SC0",
    "Germany Bundesliga": "D1",
    "Spain La Liga": "SP1",
    "Italy Serie A": "I1",
    "France Ligue 1": "F1",
    "Netherlands Eredivisie": "N1",
}

st.header("1. Get historical match data")
source = st.radio("Data source", ["Upload CSV", "Import football-data.co.uk CSV"], horizontal=True)

sample_csv = "Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HC,AC,HS,AS,HST,AST,HY,AY,HR,AR,HPoss,APoss,HF,AF\n2025-08-16,Arsenal,Leeds,2,0,H,7,3,15,7,6,2,1,2,0,0,58,42,9,12\n2025-08-17,Chelsea,Fulham,1,1,D,5,4,12,10,4,4,2,3,0,0,54,46,11,10\n2025-08-18,Liverpool,Newcastle,3,1,H,8,2,18,8,8,3,1,1,0,0,61,39,7,14\n"

raw_bytes = None
source_name = "Uploaded CSV"

if source == "Upload CSV":
    st.download_button("Download example CSV template", sample_csv, "football_results_template.csv", "text/csv")
    uploaded_file = st.file_uploader("Choose a CSV file", type=["csv"])
    if uploaded_file is not None:
        raw_bytes = uploaded_file.getvalue()
else:
    col1, col2 = st.columns(2)
    with col1:
        league_name = st.selectbox("League", list(LEAGUES.keys()))
    with col2:
        season = st.selectbox("Season", ["2026/27", "2025/26", "2024/25", "2023/24", "2022/23", "2021/22", "2020/21", "2019/20"])
    season_code = season.replace("20", "", 1).replace("/", "")
    # football-data.co.uk uses two-digit season codes, e.g. 2526 for 2025/26.
    season_code = season.split("/")[0][-2:] + season.split("/")[1][-2:]
    league_code = LEAGUES[league_name]
    data_url = f"https://www.football-data.co.uk/mmz4281/{season_code}/{league_code}.csv"
    st.caption(f"Source URL: {data_url}")
    if st.button("Import selected season"):
        try:
            response = requests.get(data_url, timeout=20, headers={"User-Agent": "FootballResearchLab/1.0"})
            response.raise_for_status()
            if len(response.content) < 100:
                st.error("The source returned an unexpectedly small file. Try another season or league.")
            else:
                raw_bytes = response.content
                source_name = f"football-data.co.uk — {league_name} {season}"
                st.session_state["imported_data"] = raw_bytes
                st.session_state["imported_source"] = source_name
                st.success("Historical CSV downloaded. Processing it below.")
        except requests.RequestException as error:
            st.error(f"Could not download that dataset: {error}")
    raw_bytes = st.session_state.get("imported_data", raw_bytes)
    source_name = st.session_state.get("imported_source", source_name)

if raw_bytes is None:
    st.warning("Choose a CSV upload or import a league and season to begin.")
    st.stop()

try:
    matches = pd.read_csv(io.BytesIO(raw_bytes))
except Exception as error:
    st.error(f"The CSV could not be read: {error}")
    st.stop()

# Normalise common provider naming differences.
rename_map = {
    "Home Team": "HomeTeam", "Away Team": "AwayTeam", "HomeGoals": "FTHG", "AwayGoals": "FTAG",
    "FullTimeHomeGoals": "FTHG", "FullTimeAwayGoals": "FTAG", "FullTimeResult": "FTR",
}
matches = matches.rename(columns={key: value for key, value in rename_map.items() if key in matches.columns})
missing = [column for column in CORE_COLUMNS if column not in matches.columns]
if missing:
    st.error("Missing required columns: " + ", ".join(missing))
    st.write("Columns found:", ", ".join(map(str, matches.columns)))
    st.stop()

available_stats = {label: pair for label, pair in STAT_PAIRS.items() if all(column in matches.columns for column in pair)}
keep_columns = CORE_COLUMNS + [column for pair in available_stats.values() for column in pair]
matches = matches[keep_columns].copy()
matches["Date"] = pd.to_datetime(matches["Date"], errors="coerce", dayfirst=True)
for column in ["FTHG", "FTAG"] + [column for pair in available_stats.values() for column in pair]:
    matches[column] = pd.to_numeric(matches[column], errors="coerce")
matches["FTR"] = matches["FTR"].astype(str).str.upper().str.strip()

errors = []
if matches["Date"].isna().any(): errors.append("Some dates are invalid.")
if matches[["FTHG", "FTAG"]].isna().any().any(): errors.append("Some goal values are missing or invalid.")
if (matches[["FTHG", "FTAG"]] < 0).any().any(): errors.append("Goals cannot be negative.")
if not matches["FTR"].isin(["H", "D", "A"]).all(): errors.append("FTR must be H, D or A.")
if matches["HomeTeam"].astype(str).str.strip().eq("").any() or matches["AwayTeam"].astype(str).str.strip().eq("").any(): errors.append("Team names cannot be blank.")
for label, (home_col, away_col) in available_stats.items():
    if matches[[home_col, away_col]].isna().any().any(): errors.append(f"Some {label.lower()} values are missing or invalid.")
    if label == "Possession %":
        if ((matches[[home_col, away_col]] < 0) | (matches[[home_col, away_col]] > 100)).any().any(): errors.append("Possession must be between 0 and 100.")
    elif (matches[[home_col, away_col]] < 0).any().any(): errors.append(f"{label} cannot contain negative values.")
if errors:
    st.error("Validation issues found:")
    for error in errors: st.write(f"- {error}")
    st.stop()

matches = matches.dropna(subset=["Date", "FTHG", "FTAG"]).copy()
matches["FTHG"] = matches["FTHG"].astype(int)
matches["FTAG"] = matches["FTAG"].astype(int)
matches["TotalGoals"] = matches["FTHG"] + matches["FTAG"]
matches["BTTS"] = (matches["FTHG"] > 0) & (matches["FTAG"] > 0)
matches = matches.sort_values("Date").reset_index(drop=True)

st.success(f"Validation passed: {len(matches):,} matches loaded from {source_name}.")

st.header("2. Dataset overview")
metrics = st.columns(5)
metrics[0].metric("Matches", f"{len(matches):,}")
metrics[1].metric("Teams", f"{pd.unique(matches[['HomeTeam', 'AwayTeam']].values.ravel()).size:,}")
metrics[2].metric("Average goals", f"{matches['TotalGoals'].mean():.2f}")
metrics[3].metric("Both teams scored", f"{matches['BTTS'].mean() * 100:.1f}%")
metrics[4].metric("Optional stat groups", len(available_stats))
if available_stats:
    st.success("Statistics detected: " + ", ".join(available_stats.keys()))
else:
    st.warning("No optional statistics were detected in this dataset.")

st.subheader("Recent matches")
st.dataframe(matches.sort_values("Date", ascending=False).head(50), use_container_width=True, hide_index=True)

st.header("3. Result breakdown")
counts = matches["FTR"].value_counts().reindex(["H", "D", "A"], fill_value=0)
st.dataframe(pd.DataFrame({"Result": ["Home wins", "Draws", "Away wins"], "Matches": counts.values, "Percentage": (counts.values / len(matches) * 100).round(1)}), use_container_width=True, hide_index=True)

st.header("4. Team form and performance")
teams = sorted(pd.unique(matches[["HomeTeam", "AwayTeam"]].values.ravel()))
selected_team = st.selectbox("Choose a team", teams)
home = matches[matches["HomeTeam"] == selected_team].copy()
away = matches[matches["AwayTeam"] == selected_team].copy()
home["TeamGoalsFor"], home["TeamGoalsAgainst"] = home["FTHG"], home["FTAG"]
home["TeamResult"] = home["FTR"].map({"H": "W", "D": "D", "A": "L"})
away["TeamGoalsFor"], away["TeamGoalsAgainst"] = away["FTAG"], away["FTHG"]
away["TeamResult"] = away["FTR"].map({"A": "W", "D": "D", "H": "L"})
team_matches = pd.concat([home, away], ignore_index=True).sort_values("Date", ascending=False)
wins = int((team_matches["TeamResult"] == "W").sum())
draws = int((team_matches["TeamResult"] == "D").sum())
losses = int((team_matches["TeamResult"] == "L").sum())
team_metrics = st.columns(4)
team_metrics[0].metric("Games", len(team_matches))
team_metrics[1].metric("Wins", wins)
team_metrics[2].metric("Draws", draws)
team_metrics[3].metric("Losses", losses)
if len(team_matches):
    points = wins * 3 + draws
    st.write(f"**{selected_team}:** {points} points · {int(team_matches['TeamGoalsFor'].sum())} scored · {int(team_matches['TeamGoalsAgainst'].sum())} conceded · {team_matches['TeamGoalsFor'].mean():.2f} goals per game.")

st.subheader("Last five matches")
last_five = team_matches.head(5).copy()
last_five["Date"] = last_five["Date"].dt.strftime("%Y-%m-%d")
st.dataframe(last_five[["Date", "HomeTeam", "AwayTeam", "TeamGoalsFor", "TeamGoalsAgainst", "TeamResult"]], use_container_width=True, hide_index=True)

st.subheader("Team statistics")
if available_stats and len(team_matches):
    rows = []
    for label, (home_col, away_col) in available_stats.items():
        values = [row[home_col] if row["HomeTeam"] == selected_team else row[away_col] for _, row in team_matches.iterrows()]
        rows.append({"Statistic": label, "Team average per match": round(pd.Series(values).mean(), 2)})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("Upload a dataset containing optional statistics to see team-level averages.")

st.caption("Next: pre-match features, odds ingestion and time-ordered backtesting. No future information is used in the current summaries.")
