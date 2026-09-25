# Main entrypoint for the Football Betting Research Lab.
# The enhanced dashboard lives in app_locked.py.
exec(compile(open("app_locked.py", "r", encoding="utf-8").read(), "app_locked.py", "exec"))

# Live API section is intentionally kept after the existing dashboard so the
# historical research tools remain unchanged.
from datetime import date, timedelta

from live_api import fixtures_for_date, fixture_rows, live_fixtures, prediction_for_fixture, prediction_summary

st.header("9. Live fixtures and current match context")
st.caption("Live data comes from API-Football. Availability depends on the league and your API plan; predictions are informational, not guarantees.")

live_col, date_col = st.columns(2)
with live_col:
    load_live = st.button("Refresh live fixtures", type="primary")
with date_col:
    fixture_date = st.date_input("Fixture date", value=date.today(), min_value=date.today() - timedelta(days=7), max_value=date.today() + timedelta(days=30))

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
        rows = fixture_rows(daily_payload)
        st.subheader(f"Fixtures on {fixture_date.isoformat()}")
        st.dataframe(rows, use_container_width=True, hide_index=True)
        st.session_state["api_fixture_payload"] = daily_payload
    else:
        st.info("No fixtures were returned for that date.")

fixture_payload = st.session_state.get("api_fixture_payload", [])
if fixture_payload:
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
        st.subheader("Model context for one fixture")
        selected_label = st.selectbox("Choose a fixture", list(fixture_options))
        if st.button("Load prediction context"):
            selected_id = fixture_options[selected_label]
            prediction_payload, prediction_error = prediction_for_fixture(selected_id)
            if prediction_error:
                st.error(prediction_error)
            else:
                summary = prediction_summary(prediction_payload)
                if summary:
                    st.dataframe([summary], use_container_width=True, hide_index=True)
                    st.info("Use this as additional context only. It is not a guaranteed outcome and should not be treated as a standalone decision rule.")
                else:
                    st.info("No prediction data was available for this fixture.")

st.caption("API notes: the app requests fixtures in Europe/London time and caches API responses briefly to reduce unnecessary requests.")
