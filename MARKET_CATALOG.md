# Football Betting Market Coverage

This document defines the markets the research app should be able to study. It does **not** assume that any market is consistently profitable. Profitability must be measured with time-ordered backtesting, bookmaker margin removal, realistic odds, and out-of-sample testing.

## Market families and required data

### 1. Match result and handicap
- Home/draw/away (1X2)
- Double chance
- Draw no bet
- Asian handicap / European handicap
- Home win to nil / away win to nil
- Winning margin
- Exact score
- Half-time result
- Half-time/full-time

Required inputs: final score, half-time score, team strength, home/away splits, shots, shots on target, xG where available, odds snapshots.

### 2. Goals markets
- Over/under full-match goals: 0.5, 1.5, 2.5, 3.5, 4.5 and Asian lines
- Over/under first-half goals
- Over/under second-half goals
- Team total goals
- Both teams to score (BTTS)
- BTTS + result / BTTS + over-under
- Goal in first 10/15/30 minutes
- Goal in each half
- Clean sheet
- First goal / last goal
- Exact number of goals
- Goal timing bands

Required inputs: goals by minute, half-time score, shots, shots on target, xG, big chances, attacks if available, red cards, substitutions, pre-match and in-play odds.

### 3. Corners markets
- Full-match total corners
- First-half corners
- Second-half corners
- Home-team corners
- Away-team corners
- Corner handicap
- Team to win corners
- Most corners
- Corner bands / exact corner totals

Required inputs: HC, AC, first-half corners, second-half corners, team corner averages, corners for/against, possession, shots, crosses, attacks and match state.

### 4. Cards and discipline
- Total cards
- Home/away team cards
- First-half cards
- Player to be booked
- Player card lines
- Red card yes/no
- Total fouls
- Team fouls
- Player fouls committed/drawn

Required inputs: HY, AY, HR, AR, HF, AF, referee identity, referee card average, referee foul average, team discipline averages, player minutes and starting status.

### 5. Shooting and attacking props
- Total shots
- Team shots
- Shots on target
- Player shots
- Player shots on target
- Player to score
- Player to assist
- Player goal or assist
- First/last/anytime scorer
- Big chances
- Offsides

Required inputs: HS, AS, HST, AST, player shots, player shots on target, xG, xA, touches in box, minutes, starts, penalties and set-piece responsibility.

### 6. Passing, possession and defensive props
- Possession winner / possession totals
- Team passes attempted/completed
- Player passes attempted/completed
- Passing accuracy
- Tackles
- Interceptions
- Clearances
- Blocks
- Recoveries
- Goalkeeper saves
- Goals conceded / clean-sheet props

Required inputs: HPoss, APoss, HPass, APass, pass completion, player passing data, tackles, interceptions, clearances, blocks, saves and goalkeeper status.

### 7. Match-state and live markets
- Result after 15/30/60/75 minutes
- Next goal
- Next corner
- Next card
- Goals/corners/cards in remaining time
- Team to score next
- Draw no bet after a red card

Required inputs: event timestamps, score state, red cards, substitutions, shots, corners, cards, possession, attacks and live odds snapshots. These must be modelled separately from pre-match markets.

## Data quality rules

1. Never use a statistic recorded after kick-off as a pre-match prediction feature.
2. Store the timestamp of every odds snapshot.
3. Keep home and away values separate; do not combine them into one unnamed value.
4. Track missingness by league, season, provider and market.
5. Keep bookmaker, market name, line, selection, decimal odds and timestamp together.
6. Remove or estimate bookmaker margin only with a documented method.
7. Use chronological train/test splits and include a walk-forward backtest.
8. Report calibration, Brier score, log loss, ROI, yield, maximum drawdown, sample size and confidence intervals.
9. Do not call a market profitable based on a small sample or one season.
10. Compare against simple baselines such as bookmaker implied probability and league averages.

## Initial implementation priority

Start with markets that can be supported by widely available historical data:

1. Match result
2. Over/under goals
3. BTTS
4. Team goals
5. Corners
6. Shots and shots on target
7. Cards and fouls
8. First-half goals
9. Clean sheets
10. Player markets only when reliable player-level data and line-up information are available

Research literature has found that shots and corners can add information to goal-total forecasting, but reported historical results depend on data quality, bookmaker prices, market selection and availability of the best odds. The app must test this independently rather than assume it will repeat in the Premier League or in current markets.
