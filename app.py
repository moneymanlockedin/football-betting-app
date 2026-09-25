# Main entrypoint for the Football Betting Research Lab.
# The historical research dashboard remains in app_locked.py.
exec(compile(open("app_locked.py", "r", encoding="utf-8").read(), "app_locked.py", "exec"))

from datetime import date, timedelta

import pandas as pd

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

st.header("9. Live fixtures, markets, and current match context")
st.caption(
    "Live data comes from API-Football. Odds and markets depend on provider coverage and your API plan. "
    "Research context is not a guarantee or a betting instruction."
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
                if summary:
                    st.subheader("API prediction context")
                    st.dataframe(pd.DataFrame([summary]), use_container_width=True, hide_index=True)
                else:
                    st.info("No prediction data was available for this fixture.")

        if load_odds:
            odds_payload, odds_error = odds_for_fixture(selected_id)
            if odds_error:
                st.error(odds_error)
            elif odds_payload:
                parsed_odds = odds_rows(odds_payload)
                st.session_state["selected_fixture_odds"] = parsed_odds
                st.subheader("Available markets and bookmaker odds")
                if parsed_odds:
                    odds_df = pd.DataFrame(parsed_odds)
                    st.dataframe(odds_df, use_container_width=True, hide_index=True)
                    st.caption(
                        "The table displays available selections across markets such as match result, double chance, goals, "
                        "BTTS, corners, cards, and player markets when supplied by the provider."
                    )
                else:
                    st.info("The provider returned the fixture but no market selections were available.")
            else:
                st.info("No odds were returned for this fixture or league.")

        if load_stats:
            stats_payload, stats_error = statistics_for_fixture(selected_id)
            if stats_error:
                st.error(stats_error)
            elif stats_payload:
                rows = statistics_rows(stats_payload)
                st.subheader("Fixture statistics")
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
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

        st.subheader("Research market watchlist")
        st.write(
            "This section surfaces available market prices for inspection. A market is not labelled as a value bet unless "
            "the app has a calibrated, market-specific probability model and an out-of-sample test for it."
        )
        stored_odds = st.session_state.get("selected_fixture_odds", [])
        if stored_odds:
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
            if market_filter:
                view = watch_df[watch_df["Market"].isin(market_filter)].copy()
            else:
                view = watch_df.iloc[0:0]
            st.dataframe(view, use_container_width=True, hide_index=True)
            st.info(
                "Implied probability is calculated from the displayed decimal price only and does not remove bookmaker margin. "
                "It is not the model probability."
            )
        else:
            st.info("Load all odds above to populate the market watchlist.")

st.caption("API responses are cached briefly to reduce unnecessary requests. Refresh the relevant section when you need updated data.")
