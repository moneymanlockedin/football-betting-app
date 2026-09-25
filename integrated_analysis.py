"""Integrated live-fixture analysis using the loaded historical dataset."""

from datetime import date, timedelta
import math

import pandas as pd
import streamlit as st

from live_api import (
    event_rows,
    events_for_fixture,
    fixture_rows,
    fixtures_for_date,
    live_fixtures,
    odds_for_fixture,
    odds_rows,
    prediction_for_fixture,
    prediction_summary,
    statistics_for_fixture,
    statistics_rows,
)


def _pct(value):
    return f"{value * 100:.1f}%" if value is not None else "—"


def _safe_float(value):
    try:
        return float(str(value).replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _poisson_over(mean, line=2.5):
    if mean is None or pd.isna(mean):
        return None
    mean = max(float(mean), 0.01)
    cutoff = int(math.floor(line))
    cumulative = sum(math.exp(-mean) * mean**k / math.factorial(k) for k in range(cutoff + 1))
    return max(0.0, min(1.0, 1.0 - cumulative))


def _team_snapshot(data, team, n=12):
    matches = data[(data["HomeTeam"] == team) | (data["AwayTeam"] == team)].sort_values("Date").tail(n)
    if matches.empty:
        return None
    goals_for, goals_against, wins, draws, losses = [], [], 0, 0, 0
    btts, totals, corners, yellows = [], [], [], []
    for _, row in matches.iterrows():
        home = row["HomeTeam"] == team
        gf = row["FTHG"] if home else row["FTAG"]
        ga = row["FTAG"] if home else row["FTHG"]
        goals_for.append(float(gf)); goals_against.append(float(ga))
        result = row["FTR"]
        team_result = result if home else {"H": "A", "A": "H", "D": "D"}.get(result, result)
        if team_result == "H": wins += 1
        elif team_result == "D": draws += 1
        else: losses += 1
        btts.append(bool(row["BTTS"]))
        totals.append(float(row["TotalGoals"]))
        if all(c in row.index for c in ["HC", "AC"]):
            corners.append(float(row["HC"] if home else row["AC"]))
        if all(c in row.index for c in ["HY", "AY"]):
            yellows.append(float(row["HY"] if home else row["AY"]))
    return {
        "matches": len(matches),
        "gf": sum(goals_for) / len(goals_for),
        "ga": sum(goals_against) / len(goals_against),
        "win": wins / len(matches),
        "draw": draws / len(matches),
        "loss": losses / len(matches),
        "btts": sum(btts) / len(btts),
        "over25": sum(x > 2.5 for x in totals) / len(totals),
        "corners": sum(corners) / len(corners) if corners else None,
        "yellows": sum(yellows) / len(yellows) if yellows else None,
    }


def _historical_probabilities(data, home, away):
    hs, aws = _team_snapshot(data, home), _team_snapshot(data, away)
    league = {
        "over25": float((data["TotalGoals"] > 2.5).mean()),
        "btts": float(data["BTTS"].mean()),
        "corners_over95": None,
        "cards_over35": None,
    }
    if "HC" in data and "AC" in data:
        corners_total = pd.to_numeric(data["HC"], errors="coerce") + pd.to_numeric(data["AC"], errors="coerce")
        league["corners_over95"] = float((corners_total > 9.5).mean())
    if "HY" in data and "AY" in data:
        cards_total = pd.to_numeric(data["HY"], errors="coerce") + pd.to_numeric(data["AY"], errors="coerce")
        league["cards_over35"] = float((cards_total > 3.5).mean())

    if not hs or not aws:
        return {}, hs, aws
    expected_home = (hs["gf"] + aws["ga"]) / 2
    expected_away = (aws["gf"] + hs["ga"]) / 2
    total_expected = expected_home + expected_away
    over25 = (hs["over25"] + aws["over25"] + league["over25"]) / 3
    btts = (hs["btts"] + aws["btts"] + league["btts"]) / 3

    # Transparent, deliberately conservative blend of recent team form and league base rates.
    home_strength = (hs["win"] + (1 - aws["loss"])) / 2
    away_strength = (aws["win"] + (1 - hs["loss"])) / 2
    draw_base = (hs["draw"] + aws["draw"]) / 2
    total_strength = max(home_strength + away_strength + draw_base, 0.001)
    home_p = home_strength / total_strength
    away_p = away_strength / total_strength
    draw_p = draw_base / total_strength

    return {
        "Match winner": {"Home": home_p, "Draw": draw_p, "Away": away_p},
        "Goals": {"Over 2.5": max(over25, _poisson_over(total_expected) or 0), "Under 2.5": 1 - max(over25, _poisson_over(total_expected) or 0)},
        "Both Teams To Score": {"Yes": btts, "No": 1 - btts},
        "Corners": {"Over 9.5": league["corners_over95"], "Under 9.5": 1 - league["corners_over95"] if league["corners_over95"] is not None else None},
        "Cards": {"Over 3.5": league["cards_over35"], "Under 3.5": 1 - league["cards_over35"] if league["cards_over35"] is not None else None},
    }, hs, aws


def _estimate_for_market(market, selection, probabilities):
    market_l = str(market or "").lower()
    selection_l = str(selection or "").lower()
    if any(x in market_l for x in ["match winner", "fulltime result", "1x2", "winner"]):
        key = "Home" if selection_l in {"home", "1"} else "Draw" if selection_l in {"draw", "x"} else "Away" if selection_l in {"away", "2"} else None
        return probabilities.get("Match winner", {}).get(key) if key else None, "historical result blend"
    if "both teams" in market_l or "btts" in market_l:
        key = "Yes" if selection_l in {"yes", "btts - yes"} else "No" if selection_l in {"no", "btts - no"} else None
        return probabilities.get("Both Teams To Score", {}).get(key) if key else None, "historical BTTS rate"
    if "over/under" in market_l or "goals" in market_l or "total goals" in market_l:
        if "over 2.5" in selection_l or selection_l == "over 2.5": key = "Over 2.5"
        elif "under 2.5" in selection_l or selection_l == "under 2.5": key = "Under 2.5"
        else: key = None
        return probabilities.get("Goals", {}).get(key) if key else None, "historical goals blend"
    if "corner" in market_l:
        key = "Over 9.5" if "over 9.5" in selection_l else "Under 9.5" if "under 9.5" in selection_l else None
        return probabilities.get("Corners", {}).get(key) if key else None, "league corner baseline"
    if "card" in market_l:
        key = "Over 3.5" if "over 3.5" in selection_l else "Under 3.5" if "under 3.5" in selection_l else None
        return probabilities.get("Cards", {}).get(key) if key else None, "league card baseline"
    return None, None


def render_integrated_section(data):
    st.header("9. Integrated live fixtures and historical research")
    st.caption("The live fixture, odds, API context and historical dataset are connected here. Outputs are research estimates, not guarantees.")
    c1, c2 = st.columns(2)
    with c1:
        refresh_live = st.button("Refresh live fixtures", type="primary")
    with c2:
        fixture_date = st.date_input("Fixture date", value=date.today(), min_value=date.today() - timedelta(days=7), max_value=date.today() + timedelta(days=30))
    if refresh_live:
        payload, error = live_fixtures()
        if error: st.error(error)
        elif payload: st.dataframe(fixture_rows(payload), use_container_width=True, hide_index=True)
        else: st.info("No live matches returned right now.")
    if st.button("Load fixtures"):
        payload, error = fixtures_for_date(fixture_date)
        if error: st.error(error)
        else: st.session_state["integrated_fixtures"] = payload or []
    payload = st.session_state.get("integrated_fixtures", [])
    if not payload:
        st.info("Load fixtures to begin the connected analysis.")
        return
    options = {}
    for item in payload:
        f, teams = item.get("fixture", {}), item.get("teams", {})
        fid = f.get("id"); home = (teams.get("home") or {}).get("name", "Home"); away = (teams.get("away") or {}).get("name", "Away")
        if fid: options[f"{home} vs {away} (ID {fid})"] = (fid, home, away)
    label = st.selectbox("Choose a fixture", list(options))
    fixture_id, home, away = options[label]
    if st.button("Run complete analysis for this fixture", type="primary"):
        pred, pred_error = prediction_for_fixture(fixture_id)
        odds, odds_error = odds_for_fixture(fixture_id)
        stats, stats_error = statistics_for_fixture(fixture_id)
        events, events_error = events_for_fixture(fixture_id)
        st.session_state["integrated_prediction"] = prediction_summary(pred) if not pred_error else None
        st.session_state["integrated_odds"] = odds_rows(odds) if not odds_error else []
        st.session_state["integrated_stats"] = statistics_rows(stats) if not stats_error else []
        st.session_state["integrated_events"] = event_rows(events) if not events_error else []
        for name, error in [("prediction", pred_error), ("odds", odds_error), ("statistics", stats_error), ("events", events_error)]:
            if error: st.warning(f"{name.title()} unavailable: {error}")
        st.session_state["integrated_fixture_teams"] = (home, away)

    if "integrated_odds" not in st.session_state:
        st.info("Click Run complete analysis for this fixture. It loads all available API context in one action.")
        return
    probs, home_snapshot, away_snapshot = _historical_probabilities(data, home, away)
    st.subheader("Historical team context")
    if home_snapshot and away_snapshot:
        context = pd.DataFrame([
            {"Team": home, "Recent matches": home_snapshot["matches"], "Goals for/game": round(home_snapshot["gf"], 2), "Goals against/game": round(home_snapshot["ga"], 2), "Win rate": _pct(home_snapshot["win"]), "BTTS rate": _pct(home_snapshot["btts"])},
            {"Team": away, "Recent matches": away_snapshot["matches"], "Goals for/game": round(away_snapshot["gf"], 2), "Goals against/game": round(away_snapshot["ga"], 2), "Win rate": _pct(away_snapshot["win"]), "BTTS rate": _pct(away_snapshot["btts"])},
        ])
        st.dataframe(context, use_container_width=True, hide_index=True)
    else:
        st.warning("One or both teams were not found in the imported historical dataset. Historical estimates will be limited.")

    st.subheader("API context")
    if st.session_state.get("integrated_prediction"):
        st.dataframe(pd.DataFrame([st.session_state["integrated_prediction"]]), use_container_width=True, hide_index=True)
    if st.session_state.get("integrated_stats"): st.dataframe(pd.DataFrame(st.session_state["integrated_stats"]), use_container_width=True, hide_index=True)
    if st.session_state.get("integrated_events"): st.dataframe(pd.DataFrame(st.session_state["integrated_events"]), use_container_width=True, hide_index=True)

    st.subheader("11. Connected suggested research candidates")
    st.caption("Candidates combine historical rates from the imported dataset with current API odds. A missing or unsupported market is excluded rather than guessed.")
    min_edge = st.slider("Minimum estimated edge (percentage points)", 0.0, 20.0, 3.0, 0.5, key="integrated_edge")
    min_probability = st.slider("Minimum estimated probability (%)", 0, 90, 50, 5, key="integrated_probability")
    min_history = st.slider("Minimum recent matches per team", 1, 12, 5, key="integrated_history")
    candidates = []
    if home_snapshot and away_snapshot and home_snapshot["matches"] >= min_history and away_snapshot["matches"] >= min_history:
        for row in st.session_state.get("integrated_odds", []):
            odd = _safe_float(row.get("Odd"))
            if odd is None or odd <= 1: continue
            estimate, method = _estimate_for_market(row.get("Market"), row.get("Selection"), probs)
            if estimate is None or estimate < min_probability / 100: continue
            implied = 1 / odd
            edge = estimate - implied
            ev = estimate * odd - 1
            if edge * 100 >= min_edge:
                candidates.append({"Market": row.get("Market"), "Selection": row.get("Selection"), "Bookmaker": row.get("Bookmaker"), "Odds": round(odd, 3), "Estimated probability": _pct(estimate), "Implied probability": _pct(implied), "Estimated edge": f"{edge * 100:+.1f} pp", "Illustrative EV": f"{ev * 100:+.1f}%", "Method": method})
    if candidates:
        result = pd.DataFrame(candidates)
        result["_sort"] = result["Illustrative EV"].str.replace("%", "", regex=False).astype(float)
        st.success(f"{len(result)} research candidate(s) passed your filters.")
        st.dataframe(result.sort_values("_sort", ascending=False).drop(columns=["_sort"]), use_container_width=True, hide_index=True)
    else:
        st.info("No candidate passed the filters. Treat this as PASS rather than forcing a selection.")
    st.warning("These are historical-rate estimates and league baselines, not calibrated predictions for every market. They should not be used as an automatic betting rule.")
