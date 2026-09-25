# Main entrypoint for the Football Betting Research Lab.
# The historical research dashboard remains in app_locked.py.
exec(compile(open("app_locked.py", "r", encoding="utf-8").read(), "app_locked.py", "exec"))

from datetime import date, timedelta
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


def _load_prediction_and_odds(fixture_id):
    prediction_payload, prediction_error = prediction_for_fixture(fixture_id)
    odds_payload, odds_error = odds_for_fixture(fixture_id)
    prediction = prediction_summary(prediction_payload) if not prediction_error else None
    odds = odds_rows(odds_payload) if not odds_error else []
    st.session_state["selected_prediction_summary"] = prediction
    st.session_state["selected_fixture_odds"] = odds
    return prediction, odds, prediction_error, odds_error


def _build_suggestions(prediction, odds, edge_threshold, probability_floor):
    if not prediction or not odds:
        return []
    probability_map = {
        "home": prediction.get("Home probability"),
        "draw": prediction.get("Draw probability"),
        "away": prediction.get("Away probability"),
    }
    selection_map = {"home": "Home", "draw": "Draw", "away": "Away"}
    candidates = []
    for row in odds:
        market = str(row.get("Market") or "").strip().lower()
        selection = str(row.get("Selection") or "").strip().lower()
        if not any(term in market for term in ("match winner", "fulltime result", "1x2", "winner")):
            continue
        if selection in {"home", "1"}:
            key = "home"
        elif selection in {"draw", "x"}:
            key = "draw"
        elif selection in {"away", "2"}:
            key = "away"
        else:
            continue
        try:
            model_probability = float(str(probability_map[key]).replace("%", "")) / 100
            odd = float(row.get("Odd"))
        except (TypeError, ValueError):
            continue
        if odd <= 1 or model_probability < probability_floor / 100:
            continue
        implied_probability = 1 / odd
        edge = model_probability - implied_probability
        expected_value = model_probability * odd - 1
        if edge * 100 >= edge_threshold:
            candidates.append({
                "Market": row.get("Market"),
                "Selection": selection_map[key],
                "Bookmaker": row.get("Bookmaker"),
                "Odds": round(odd, 3),
                "Model probability": f"{model_probability * 100:.1f}%",
                "Implied probability": f"{implied_probability * 100:.1f}%",
                "Estimated edge": f"{edge * 100:+.1f} pp",
                "Illustrative expected value": f"{expected_value * 100:+.1f}%",
                "Status": "Research candidate",
                "_sort": expected_value,
            })
    return sorted(candidates, key=lambda x: x["_sort"], reverse=True)


st.header("9. Live fixtures, markets, and current match context")
st.caption(
    "Live data comes from API-Football. Availability depends on the league and API plan. "
    "All outputs are research context, not guarantees."
)

live_col, date_col = st.columns(2)
with live_col:
    load_live = st.button("Refresh live fixtures", type="primary")
with date_col:
    fixture_date = st.date_input(
        "Fixture date",
        value=date.today(),
        min_value=date.today() - timedelta(days=7),
        max_value=date.today() + timedelta(days=30),
    )

if load_live:
    live_payload, live_error = live_fixtures()
    if live_error:
        st.error(live_error)
    elif live_payload:
        st.subheader("Matches currently live")
        st.dataframe(fixture_rows(live_payload), use_container_width=True, hide_index=True)
    else:
        st.info("No live matches were returned right now.")

if st.button("Load fixtures for selected date"):
    daily_payload, daily_error = fixtures_for_date(fixture_date)
    if daily_error:
        st.error(daily_error)
    elif daily_payload:
        st.session_state["api_fixture_payload"] = daily_payload
        st.session_state.pop("selected_prediction_summary", None)
        st.session_state.pop("selected_fixture_odds", None)
        st.success(f"Loaded {len(daily_payload)} fixtures.")
    else:
        st.session_state["api_fixture_payload"] = []
        st.info("No fixtures were returned for that date.")

fixture_payload = st.session_state.get("api_fixture_payload", [])
if fixture_payload:
    st.subheader("Fixtures")
    st.dataframe(fixture_rows(fixture_payload), use_container_width=True, hide_index=True)
    fixture_options = {}
    for item in fixture_payload:
        fixture = item.get("fixture", {})
        teams = item.get("teams", {})
        fixture_id = fixture.get("id")
        home = (teams.get("home") or {}).get("name", "Home")
        away = (teams.get("away") or {}).get("name", "Away")
        if fixture_id:
            fixture_options[f"{home} vs {away} (ID {fixture_id})"] = fixture_id

    if fixture_options:
        st.subheader("Full match analysis")
        selected_label = st.selectbox("Choose a fixture", list(fixture_options))
        selected_id = fixture_options[selected_label]
        a, b, c, d = st.columns(4)
        with a:
            load_context = st.button("Load prediction")
        with b:
            load_odds = st.button("Load all odds")
        with c:
            load_stats = st.button("Load statistics")
        with d:
            load_events = st.button("Load events")

        if load_context:
            prediction_payload, prediction_error = prediction_for_fixture(selected_id)
            if prediction_error:
                st.error(prediction_error)
            else:
                summary = prediction_summary(prediction_payload)
                st.session_state["selected_prediction_summary"] = summary
                if summary:
                    st.subheader("API prediction context")
                    st.dataframe(pd.DataFrame([summary]), use_container_width=True, hide_index=True)
                else:
                    st.info("No prediction data was available for this fixture.")

        if load_odds:
            odds_payload, odds_error = odds_for_fixture(selected_id)
            if odds_error:
                st.error(odds_error)
            else:
                parsed_odds = odds_rows(odds_payload)
                st.session_state["selected_fixture_odds"] = parsed_odds
                if parsed_odds:
                    st.subheader("Available markets and bookmaker odds")
                    st.dataframe(pd.DataFrame(parsed_odds), use_container_width=True, hide_index=True)
                else:
                    st.info("No odds were returned for this fixture or league.")

        if load_stats:
            stats_payload, stats_error = statistics_for_fixture(selected_id)
            if stats_error:
                st.error(stats_error)
            elif stats_payload:
                st.subheader("Fixture statistics")
                st.dataframe(pd.DataFrame(statistics_rows(stats_payload)), use_container_width=True, hide_index=True)
            else:
                st.info("No statistics were available for this fixture yet.")

        if load_events:
            events_payload, events_error = events_for_fixture(selected_id)
            if events_error:
                st.error(events_error)
            elif events_payload:
                st.subheader("Match events")
                st.dataframe(pd.DataFrame(event_rows(events_payload)), use_container_width=True, hide_index=True)
            else:
                st.info("No events were returned for this fixture yet.")

        stored_odds = st.session_state.get("selected_fixture_odds", [])
        if stored_odds:
            st.subheader("Research market watchlist")
            watch_df = pd.DataFrame(stored_odds).copy()
            watch_df["Decimal odd"] = pd.to_numeric(watch_df["Odd"], errors="coerce")
            watch_df["Implied probability %"] = (100 / watch_df["Decimal odd"]).round(2)
            watch_df = watch_df.dropna(subset=["Decimal odd"])
            watch_df = watch_df[watch_df["Decimal odd"] > 1]
            market_filter = st.multiselect(
                "Markets to inspect",
                sorted(watch_df["Market"].dropna().unique().tolist()),
                default=sorted(watch_df["Market"].dropna().unique().tolist())[:8],
            )
            view = watch_df[watch_df["Market"].isin(market_filter)] if market_filter else watch_df.iloc[0:0]
            st.dataframe(view, use_container_width=True, hide_index=True)
            st.info("Implied probability is based on the displayed odds and does not remove bookmaker margin.")

        st.header("10. Suggested bets research shortlist")
        st.caption(
            "Use the one-click generator below. It loads both prediction data and odds automatically, then compares API-supplied 1X2 probabilities with available prices."
        )
        edge_threshold = st.slider("Minimum estimated edge (percentage points)", 0.0, 20.0, 3.0, 0.5, key="suggest_edge")
        probability_floor = st.slider("Minimum model probability (%)", 0, 90, 45, 5, key="suggest_probability")
        generate = st.button("Generate suggested bets", type="primary")
        if generate:
            with st.spinner("Loading prediction and odds, then analysing available 1X2 prices..."):
                prediction, fresh_odds, prediction_error, odds_error = _load_prediction_and_odds(selected_id)
            if prediction_error:
                st.error(f"Prediction request: {prediction_error}")
            if odds_error:
                st.error(f"Odds request: {odds_error}")
            if not prediction:
                st.warning("No usable prediction was returned for this fixture.")
            elif not fresh_odds:
                st.warning("No usable odds were returned for this fixture or league.")
            else:
                candidates = _build_suggestions(prediction, fresh_odds, edge_threshold, probability_floor)
                if candidates:
                    result = pd.DataFrame(candidates).drop(columns=["_sort"])
                    st.success(f"{len(result)} research candidate(s) passed your filters.")
                    st.dataframe(result, use_container_width=True, hide_index=True)
                else:
                    st.info("No 1X2 candidate passed these filters. PASS for this fixture under the selected settings.")
        else:
            st.info("Click Generate suggested bets. You no longer need to load prediction and odds separately.")
        st.warning(
            "This version is an API-based 1X2 research filter, not a validated all-market model. It does not claim calibrated predictions for corners, cards, passes or player markets."
        )

st.caption("API responses are cached briefly to reduce unnecessary requests. Refresh the relevant section when you need updated data.")
