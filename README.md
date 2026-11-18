# makefun-gta6-twitch-ccu-forecast-01

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/whyuardi/makefun-gta6-twitch-ccu-forecast-01/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/whyuardi/makefun-gta6-twitch-ccu-forecast-01/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

Forecasts GTA VI's launch-day Twitch viewers hour by hour from the first hour's print, using the release-day shapes of 38 past big launches.

## How it works

A big launch day has a stereotyped shape: viewers dip overnight, then climb
with each region's midnight unlock toward an evening peak. The program reads
every past launch in the case's comparables, takes the distribution of
`log(viewers_h / viewers_1)` for each hour, and anchors it on this case's
hour-1 print. Launches that unlocked at midnight local time count 3x, and
launches whose hour-1 print is close to the target's in log space count
more; the five quantiles are the weighted empirical quantiles, shrunk 15%
toward the median and capped at 1.25 log units from it.

Practice score (pinball loss on the log scale, lower is better): **0.229**
against the house baseline's **0.387** on the four practice launches.

## Run it

```sh
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Standard library only, no network. Reads each `<id>.in` in the input
directory and writes `<id>.out` with 23 rows (hours 2–24), five quantiles
each.

---

<sub>Entered on [make.fun](https://make.fun/?ref=qcm3p0tm&utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
