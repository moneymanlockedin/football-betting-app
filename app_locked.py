import io
import math
import re

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Football Betting Research Lab", page_icon="⚽", layout="wide")
st.title("⚽ Football Betting Research Lab")
st.write("A transparent dashboard for exploring football results, statistics and historical odds.")
st.info("Research only. This app does not place bets or guarantee profit. Historical patterns are not certain predictions.")

CORE = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]
STAT_PAIRS = {"Corners": ("HC", "AC"), "Shots": ("HS", "AS"), "Shots on target": ("HST", "AST"), "Yellow cards": ("HY", "AY"), "Red cards": ("HR", "AR"), "Fouls": ("HF", "AF"), "Offsides": ("HO", "AO"), "Saves": ("HSave", "ASave"), "Possession %": ("HPoss", "APoss")}
LEAGUES = {"England Premier League": "E0", "England Championship": "E1", "England League One": "E2", "England League Two": "E3", "Scotland Premiership": "SC0", "Germany Bundesliga": "D1", "Spain La Liga": "SP1", "Italy Serie A": "I1", "France Ligue 1": "F1", "Netherlands Eredivisie": "N1"}
SEASONS = ["2026/27", "2025/26", "2024/25", "2023/24", "2022/23", "2021/22", "2020/21", "2019/20", "2018/19"]


def num(x): return pd.to_numeric(x, errors="coerce")
def season_code(s):
    a, b = s.split("/"); return a[-2:] + b[-2:]
def max_dd(p):
    c = p.cumsum(); return float((c.cummax() - c).max()) if len(c) else 0.0
def poisson_over25(g):
    if pd.isna(g): return None
    g = max(float(g), 0.05)
    return 1 - math.exp(-g) * (1 + g + g * g / 2)
def download(code, season):
    url = f"https://www.football-data.co.uk/mmz4281/{season_code(season)}/{code}.csv"
    r = requests.get(url, timeout=30, headers={"User-Agent": "FootballResearchLab/1.0"}); r.raise_for_status()
    return pd.read_csv(io.BytesIO(r.content), encoding="latin1")


def backtest(frame, odds_col, outcome_col, winning_value, minimum, maximum, start, end):
    d = frame[["Date", "HomeTeam", "AwayTeam", odds_col, outcome_col]].copy(); d[odds_col] = num(d[odds_col])
    d = d.dropna(subset=["Date", odds_col, outcome_col]); d = d[(d.Date >= pd.Timestamp(start)) & (d.Date <= pd.Timestamp(end))]
    d = d[(d[odds_col] >= minimum) & (d[odds_col] <= maximum)].copy()
    if d.empty: return None, d
    d["Won"] = d[outcome_col] == winning_value; d["Profit"] = d[odds_col].where(d.Won, 0) - 1; d["CumulativeProfit"] = d.Profit.cumsum()
    average = d[odds_col].mean()
    return {"Bets": len(d), "Wins": int(d.Won.sum()), "Strike rate": d.Won.mean() * 100, "Profit": d.Profit.sum(), "ROI": d.Profit.mean() * 100, "Break-even rate": 100 / average, "Max drawdown": max_dd(d.Profit)}, d


def build_features(frame):
    ordered = frame.sort_values(["Date", "HomeTeam", "AwayTeam"]).reset_index(drop=True); histories = {}; rows = []
    def summary(team):
        h = histories.get(team, [])
        return (0, None, None) if not h else (len(h), sum(x[0] for x in h) / len(h), sum(x[1] for x in h) / len(h))
    for _, m in ordered.iterrows():
        hg, hf, ha = summary(m.HomeTeam); ag, af, aa = summary(m.AwayTeam)
        hp = [x for x in [hf, aa] if x is not None]; ap = [x for x in [af, ha] if x is not None]
        eh = sum(hp) / len(hp) if hp else None; ea = sum(ap) / len(ap) if ap else None; total = eh + ea if eh is not None and ea is not None else None
        rows.append({"Date": m.Date, "HomeTeam": m.HomeTeam, "AwayTeam": m.AwayTeam, "PriorHome": hg, "PriorAway": ag, "ExpectedTotal": total, "ModelProb": poisson_over25(total)})
        histories.setdefault(m.HomeTeam, []).append((float(m.FTHG), float(m.FTAG))); histories.setdefault(m.AwayTeam, []).append((float(m.FTAG), float(m.FTHG)))
    return ordered.merge(pd.DataFrame(rows), on=["Date", "HomeTeam", "AwayTeam"], how="left")


def prepared_pool(data, odds, games, minimum, maximum, start, end):
    d = build_features(data); d[odds] = num(d[odds]); d["Implied"] = 1 / d[odds]; d["Actual"] = (d.TotalGoals > 2).astype(int)
    return d[(d.Date >= pd.Timestamp(start)) & (d.Date <= pd.Timestamp(end)) & (d.PriorHome >= games) & (d.PriorAway >= games) & d.ModelProb.notna() & d[odds].notna() & (d[odds] >= minimum) & (d[odds] <= maximum)].copy()


def evaluate_pool(pool, odds, edge):
    d = pool[pool.ModelProb - pool.Implied >= edge].copy()
    if d.empty: return None, d
    d["Won"] = d.Actual.astype(bool); d["Profit"] = d[odds].where(d.Won, 0) - 1; d["CumulativeProfit"] = d.Profit.cumsum()
    return {"Bets": len(d), "Wins": int(d.Won.sum()), "Strike rate": d.Won.mean() * 100, "Profit": d.Profit.sum(), "ROI": d.Profit.mean() * 100, "Max drawdown": max_dd(d.Profit)}, d


def evaluate(data, odds, games, edge, minimum, maximum, start, end):
    return evaluate_pool(prepared_pool(data, odds, games, minimum, maximum, start, end), odds, edge)


def show_metrics(result):
    cols = st.columns(6); labels = ["Bets", "Wins", "Strike rate", "Profit", "ROI", "Max drawdown"]
    values = [result["Bets"], result["Wins"], f"{result['Strike rate']:.1f}%", f"{result['Profit']:+.2f}", f"{result['ROI']:+.2f}%", f"{result['Max drawdown']:.2f}"]
    for col, label, value in zip(cols, labels, values): col.metric(label, value)


# 1. Import
st.header("1. Get historical match data")
source = st.radio("Data source", ["Upload CSV", "Import multiple seasons"], horizontal=True); frames = []; source_name = "Uploaded CSV"
if source == "Upload CSV":
    file = st.file_uploader("Choose CSV", type=["csv"])
    if file: frames = [pd.read_csv(file, encoding="latin1")]
else:
    a, b = st.columns(2)
    with a: league = st.selectbox("League", list(LEAGUES))
    with b: seasons = st.multiselect("Seasons to combine", SEASONS, ["2025/26", "2024/25", "2023/24"])
    if st.button("Import selected seasons", type="primary"):
        errors = []; progress = st.progress(0)
        for i, season in enumerate(seasons):
            try:
                f = download(LEAGUES[league], season); f["ImportedSeason"] = season; frames.append(f)
            except Exception as e: errors.append(f"{season}: {e}")
            progress.progress((i + 1) / max(len(seasons), 1))
        for e in errors: st.warning(e)
        if frames: st.session_state["frames_locked"] = frames; st.session_state["source_locked"] = league
    frames = st.session_state.get("frames_locked", frames); source_name = st.session_state.get("source_locked", source_name)
if not frames: st.warning("Upload or import match data to begin."); st.stop()

data = pd.concat(frames, ignore_index=True, sort=False)
data = data.rename(columns={k: v for k, v in {"Home Team": "HomeTeam", "Away Team": "AwayTeam", "HomeGoals": "FTHG", "AwayGoals": "FTAG", "FullTimeHomeGoals": "FTHG", "FullTimeAwayGoals": "FTAG", "FullTimeResult": "FTR"}.items() if k in data.columns})
missing = [c for c in CORE if c not in data.columns]
if missing: st.error("Missing columns: " + ", ".join(missing)); st.stop()
data["Date"] = pd.to_datetime(data.Date, errors="coerce", dayfirst=True); data["FTHG"] = num(data.FTHG); data["FTAG"] = num(data.FTAG); data["FTR"] = data.FTR.astype(str).str.upper().str.strip()
for pair in STAT_PAIRS.values():
    for col in pair:
        if col in data: data[col] = num(data[col])
data = data.dropna(subset=["Date", "FTHG", "FTAG"]); data = data[data.FTR.isin(["H", "D", "A"])].copy(); data["FTHG"] = data.FTHG.astype(int); data["FTAG"] = data.FTAG.astype(int)
data["TotalGoals"] = data.FTHG + data.FTAG; data["BTTS"] = (data.FTHG > 0) & (data.FTAG > 0); data = data.sort_values(["Date", "HomeTeam", "AwayTeam"]).reset_index(drop=True)
available_stats = {k: v for k, v in STAT_PAIRS.items() if all(c in data.columns for c in v)}
odds_cols = [c for c in data.columns if re.search(r"(^B365|^BW|^IW|^PS|^WH|^VC|^Max|^Avg|Odds|odds)", str(c))]
over_options = [c for c in ["B365>2.5", "Avg>2.5", "Max>2.5", "P>2.5"] if c in data.columns]
st.success(f"Validation passed: {len(data):,} matches loaded from {source_name}.")

# 2. Overview
st.header("2. Dataset overview")
metrics = st.columns(6)
for col, label, value in zip(metrics, ["Matches", "Teams", "Average goals", "BTTS", "Stat groups", "Odds columns"], [len(data), pd.unique(data[["HomeTeam", "AwayTeam"]].values.ravel()).size, f"{data.TotalGoals.mean():.2f}", f"{data.BTTS.mean() * 100:.1f}%", len(available_stats), len(odds_cols)]): col.metric(label, value)
if available_stats: st.success("Statistics detected: " + ", ".join(available_stats))
if odds_cols: st.success(f"Historical odds detected: {len(odds_cols)} columns.")
else: st.warning("No odds columns detected.")
st.download_button("Download combined dataset", data.to_csv(index=False), "combined_football_dataset.csv", "text/csv")
st.subheader("Recent matches"); st.dataframe(data.sort_values("Date", ascending=False).head(100), use_container_width=True, hide_index=True)

# 3. Results
st.header("3. Result breakdown")
counts = data.FTR.value_counts().reindex(["H", "D", "A"], fill_value=0)
st.dataframe(pd.DataFrame({"Result": ["Home wins", "Draws", "Away wins"], "Matches": counts.values, "Percentage": (counts.values / len(data) * 100).round(1)}), use_container_width=True, hide_index=True)

# 4. Market backtesting
st.header("4. Market backtesting")
min_date, max_date = data.Date.min().date(), data.Date.max().date(); a, b, c = st.columns(3)
with a: start = st.date_input("Start date", min_date, min_value=min_date, max_value=max_date)
with b: end = st.date_input("End date", max_date, min_value=min_date, max_value=max_date)
with c: max_odds = st.number_input("Maximum odds", 1.01, 20.0, 10.0, 0.25)
one_x_two = [x for x in ["B365H", "AvgH", "MaxH", "BWH", "IWH", "PSH", "WH", "VCH"] if x in data]; draw_options = [x for x in ["B365D", "AvgD", "MaxD", "BWD", "IWD", "PSD", "WD", "VCD"] if x in data]; away_options = [x for x in ["B365A", "AvgA", "MaxA", "BWA", "IWA", "PSA", "WA", "VCA"] if x in data]
tab1, tab2, tab3 = st.tabs(["1X2", "Goals totals", "Threshold comparison"])
with tab1:
    choice = st.selectbox("1X2 selection", ["Home win", "Draw", "Away win"]); opts, outcome = {"Home win": (one_x_two, "H"), "Draw": (draw_options, "D"), "Away win": (away_options, "A")} [choice]; odds = st.selectbox("Odds source", opts) if opts else None; minimum = st.slider("Minimum odds", 1.01, 5.0, 1.50, 0.05)
    if odds:
        result, tested = backtest(data, odds, "FTR", outcome, minimum, max_odds, start, end)
        if result: show_metrics(result); st.line_chart(tested.set_index("Date").CumulativeProfit); st.dataframe(tested.head(100), use_container_width=True, hide_index=True)
        else: st.warning("No qualifying bets found.")
    else: st.info("No compatible 1X2 odds columns found.")
with tab2:
    choice = st.selectbox("Goals market", ["Over 2.5 goals", "Under 2.5 goals"]); opts = over_options if choice.startswith("Over") else [x for x in ["B365<2.5", "Avg<2.5", "Max<2.5", "P<2.5"] if x in data]; odds = st.selectbox("Totals odds source", opts) if opts else None; minimum = st.slider("Minimum totals odds", 1.01, 5.0, 1.50, 0.05)
    if odds:
        frame = data.copy(); frame["TotalOutcome"] = frame.TotalGoals > 2 if choice.startswith("Over") else frame.TotalGoals < 3; result, tested = backtest(frame, odds, "TotalOutcome", True, minimum, max_odds, start, end)
        if result: show_metrics(result); st.line_chart(tested.set_index("Date").CumulativeProfit); st.dataframe(tested.head(100), use_container_width=True, hide_index=True)
        else: st.warning("No qualifying bets found.")
    else: st.info("No compatible totals odds columns found.")
with tab3:
    market = st.selectbox("Comparison market", ["Over 2.5 goals", "Under 2.5 goals", "Home win", "Draw", "Away win"])
    if market == "Over 2.5 goals": opts, frame, outcome, winning = over_options, data.copy(), "TotalOutcome", True; frame["TotalOutcome"] = frame.TotalGoals > 2
    elif market == "Under 2.5 goals": opts, frame, outcome, winning = [x for x in ["B365<2.5", "Avg<2.5", "Max<2.5", "P<2.5"] if x in data], data.copy(), "TotalOutcome", True; frame["TotalOutcome"] = frame.TotalGoals < 3
    else: opts = {"Home win": one_x_two, "Draw": draw_options, "Away win": away_options}[market]; frame, outcome, winning = data, "FTR", {"Home win": "H", "Draw": "D", "Away win": "A"}[market]
    if opts:
        odds = st.selectbox("Comparison odds source", opts); rows = []
        for threshold in [1.25, 1.50, 1.75, 2.00, 2.25, 2.50, 3.00]:
            result, _ = backtest(frame, odds, outcome, winning, threshold, max_odds, start, end)
            if result: rows.append({"Minimum odds": threshold, "Bets": result["Bets"], "Strike rate %": round(result["Strike rate"], 2), "ROI %": round(result["ROI"], 2), "Profit units": round(result["Profit"], 2), "Max drawdown": round(result["Max drawdown"], 2)})
        if rows: st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else: st.warning("No comparison results.")
    else: st.info("No compatible odds columns found.")

# 5. Team form
st.header("5. Team form and performance")
teams = sorted(pd.unique(data[["HomeTeam", "AwayTeam"]].values.ravel())); team = st.selectbox("Choose a team", teams)
home = data[data.HomeTeam == team].copy(); away = data[data.AwayTeam == team].copy(); home["TeamGoalsFor"], home["TeamGoalsAgainst"], home["TeamResult"] = home.FTHG, home.FTAG, home.FTR.map({"H": "W", "D": "D", "A": "L"}); away["TeamGoalsFor"], away["TeamGoalsAgainst"], away["TeamResult"] = away.FTAG, away.FTHG, away.FTR.map({"A": "W", "D": "D", "H": "L"})
team_matches = pd.concat([home, away], ignore_index=True).sort_values("Date", ascending=False); wins = int((team_matches.TeamResult == "W").sum()); draws_count = int((team_matches.TeamResult == "D").sum()); losses = int((team_matches.TeamResult == "L").sum())
cols = st.columns(4)
for col, label, value in zip(cols, ["Games", "Wins", "Draws", "Losses"], [len(team_matches), wins, draws_count, losses]): col.metric(label, value)
st.write(f"**{team}:** {wins * 3 + draws_count} points · {int(team_matches.TeamGoalsFor.sum())} scored · {int(team_matches.TeamGoalsAgainst.sum())} conceded · {team_matches.TeamGoalsFor.mean():.2f} goals per game.")
st.subheader("Last five matches"); last = team_matches.head(5).copy(); last["Date"] = last.Date.dt.strftime("%Y-%m-%d"); st.dataframe(last[["Date", "HomeTeam", "AwayTeam", "TeamGoalsFor", "TeamGoalsAgainst", "TeamResult"]], use_container_width=True, hide_index=True)
if available_stats:
    rows = []
    for label, (hc, ac) in available_stats.items():
        vals = [row[hc] if row.HomeTeam == team else row[ac] for _, row in team_matches.iterrows()]; rows.append({"Statistic": label, "Team average per match": round(pd.Series(vals).dropna().mean(), 2)})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# 6. Walk-forward
st.header("6. Walk-forward research")
if over_options:
    a, b, c = st.columns(3)
    with a: wf_odds = st.selectbox("Walk-forward odds source", over_options)
    with b: wf_games = st.number_input("Minimum prior games per team", 1, 20, 5)
    with c: wf_edge = st.slider("Minimum model edge", 0.00, 0.20, 0.05, 0.01)
    wf_min_odds = st.number_input("Walk-forward minimum odds", 1.01, 10.0, 1.50, 0.05)
    if st.button("Run walk-forward evaluation", type="primary"):
        result, tested = evaluate(data, wf_odds, int(wf_games), float(wf_edge), float(wf_min_odds), float(max_odds), start, end)
        if result: show_metrics(result); st.line_chart(tested.set_index("Date").CumulativeProfit); st.dataframe(tested.head(200), use_container_width=True, hide_index=True)
        else: st.warning("No qualifying selections.")
else: st.warning("No Over 2.5 odds columns available.")

# 7. Robustness
st.header("7. Robustness and stability checks")
if over_options:
    a, b, c = st.columns(3)
    with a: rb_odds = st.selectbox("Robustness odds source", over_options, key="rb_odds")
    with b: rb_games = st.number_input("Robustness minimum prior games", 1, 20, 5, key="rb_games")
    with c: rb_min_odds = st.number_input("Robustness minimum odds", 1.01, 10.0, 1.50, 0.05, key="rb_min_odds")
    if st.button("Run robustness checks"):
        rows = []
        for minimum_edge in [0.0, 0.03, 0.05, 0.07, 0.10]:
            for ceiling in [1.75, 2.0, 2.5, 3.0, 5.0]:
                result, tested = evaluate(data, rb_odds, int(rb_games), minimum_edge, float(rb_min_odds), ceiling, start, end)
                if result:
                    low, high = None, None
                    if len(tested) > 1:
                        import numpy as np
                        samples = np.random.default_rng(42).choice(tested.Profit.to_numpy(), size=(500, len(tested)), replace=True).mean(axis=1) * 100
                        low, high = np.percentile(samples, 2.5), np.percentile(samples, 97.5)
                    rows.append({"Minimum edge": minimum_edge, "Max odds": ceiling, "Bets": result["Bets"], "ROI %": round(result["ROI"], 2), "Profit": round(result["Profit"], 2), "Max drawdown": round(result["Max drawdown"], 2), "Bootstrap ROI low %": round(low, 2) if low is not None else None, "Bootstrap ROI high %": round(high, 2) if high is not None else None})
        if rows:
            table = pd.DataFrame(rows).sort_values(["ROI %", "Bets"], ascending=[False, False]); st.subheader("Sensitivity grid"); st.dataframe(table, use_container_width=True, hide_index=True)
            best = table.iloc[0]; _, season_test = evaluate(data, rb_odds, int(rb_games), float(best["Minimum edge"]), float(rb_min_odds), float(best["Max odds"]), start, end)
            if season_test is not None and not season_test.empty:
                st.subheader("Season-by-season breakdown")
                st.dataframe(season_test.groupby("ImportedSeason", dropna=False).agg(Bets=("Won", "size"), Wins=("Won", "sum"), Profit=("Profit", "sum")).reset_index() if "ImportedSeason" in season_test else pd.DataFrame(), use_container_width=True, hide_index=True)
                st.warning("The highest-ROI row is descriptive only and was selected after comparing settings.")
        else: st.warning("No robustness configurations produced results.")

# 8. Holdout plus calibration and benchmark
st.header("8. Locked final holdout test")
st.write("Choose a development cutoff. The holdout is evaluated separately and should not be repeatedly tuned after inspection.")
cutoff = st.date_input("Development cutoff", max_date - pd.Timedelta(days=365), min_value=min_date, max_value=max_date)
if st.button("Run locked holdout test", type="primary"):
    holdout_start = (pd.Timestamp(cutoff) + pd.Timedelta(days=1)).date()
    if holdout_start > end:
        st.warning("Move the cutoff earlier so a holdout period remains.")
    else:
        pool = prepared_pool(data, wf_odds, int(wf_games), float(wf_min_odds), float(max_odds), holdout_start, end)
        result, holdout = evaluate_pool(pool, wf_odds, float(wf_edge))
        st.subheader("Untouched holdout results")
        if result:
            show_metrics(result); st.line_chart(holdout.set_index("Date").CumulativeProfit); st.dataframe(holdout, use_container_width=True, hide_index=True)
            st.subheader("Probability calibration")
            st.write({"Observations": len(pool), "Model Brier score": round(((pool.ModelProb - pool.Actual) ** 2).mean(), 4), "Odds-implied Brier score": round(((pool.Implied - pool.Actual) ** 2).mean(), 4), "Mean model probability": round(pool.ModelProb.mean() * 100, 2), "Actual Over 2.5 rate": round(pool.Actual.mean() * 100, 2)})
            st.subheader("Benchmark comparison")
            baseline = pool.copy(); baseline["Won"] = baseline.Actual.astype(bool); baseline["Profit"] = baseline[wf_odds].where(baseline.Won, 0) - 1
            benchmark = {"Bets": len(baseline), "Wins": int(baseline.Won.sum()), "Strike rate": baseline.Won.mean() * 100, "Profit": baseline.Profit.sum(), "ROI": baseline.Profit.mean() * 100}
            st.dataframe(pd.DataFrame([{"Strategy": "All eligible holdout matches", **benchmark}, {"Strategy": "Model-selected holdout matches", "Bets": result["Bets"], "Wins": result["Wins"], "Strike rate": result["Strike rate"], "Profit": result["Profit"], "ROI": result["ROI"]}]), use_container_width=True, hide_index=True)
        else: st.warning("No qualifying holdout selections.")

st.caption("Safeguards: chronological features, explicit holdout, sensitivity diagnostics, calibration checks, and warnings against selecting settings after seeing holdout results.")
