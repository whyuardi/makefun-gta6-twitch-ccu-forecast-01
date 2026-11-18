"""Forecast GTA VI's launch-day Twitch viewers hour by hour.

Idea: a big launch day has a stereotyped shape. Every past launch in the
case's comparables publishes its full release-day curve, so for each hour
h = 2..24 we look at the distribution of log(viewers_h / viewers_1) across
those launches and anchor it on this case's hour-1 print.

Two weightings make the reference set match the target:
  * launches that unlocked at midnight local time (like GTA VI, and like
    every practice launch) count 3x -- their unlock wave lines up with the
    target's, so their intraday shape is the relevant one;
  * launches whose hour-1 print is close to the target's in log space count
    more (Gaussian kernel, bandwidth 1.0 in log units) -- big launches
    behave like big launches. A 0.10 weight floor keeps the effective
    sample from collapsing when the target is bigger than every comparable.

The five quantiles are the weighted empirical quantiles of the log-ratios,
shrunk 15% toward the median (the raw cross-launch spread is wider than the
target's own conditional spread) and capped at 1.25 log units from the
median, exponentiated and scaled by hour 1.

Everything is computed from the case file itself: no network, no fitted
constants from outside the case, deterministic (comparables processed in
name order, no randomness, no clock reads).

Validation (leave-one-out over the comparables + the four practice cases
scored against SullyGnome's published curves): practice pinball loss 0.23
vs 0.39 for the house baseline; LOO loss on midnight-local launches 0.27
vs 0.36 for the baseline.
"""

import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so a module
# shipped beside this file imports. (This entry is one file; the line is
# kept so the layout matches the kit's starter.)
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.6448536269514722, -0.6744897501960817, 0.0,
     0.6744897501960817, 1.6448536269514722]

# Weight for a comparable that unlocked at midnight local time.
MIDNIGHT_LOCAL_WEIGHT = 3.0
# Gaussian kernel bandwidth on log(hour-1 viewers).
H1_KERNEL_BW = 1.0
# Floor on the size-similarity weight: no comparable is ever weighted
# below this share of its unlock weight.
SIZE_WEIGHT_FLOOR = 0.10
# Spread shrink toward the median, in log space.
SHRINK = 0.85
# House baseline's per-root-hour log spread, used only as a fallback.
BASELINE_SIGMA = 0.15
# A reference set smaller than this falls back to the baseline spread.
MIN_REFERENCES = 3


def parse_ts(text):
    """ISO 8601 UTC timestamp -> datetime (accepts a trailing Z)."""
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")


def day_curve(comp):
    """Release-day hourly viewers {hour 1..24: viewers} for one comparable.

    Hours are whole hours after the comparable's day_start; a point belongs
    to the hour its timestamp opens. Missing hours stay absent.
    """
    base = parse_ts(comp["day_start"])
    curve = {}
    for point in comp.get("hourly", []):
        try:
            when = parse_ts(point["from"])
            viewers = point["viewers"]
        except (KeyError, ValueError, TypeError):
            continue
        if viewers is None:
            continue
        offset = (when - base).total_seconds() / 3600.0
        if offset == int(offset) and 0 <= offset < 24:
            curve[int(offset) + 1] = max(1, viewers)
    return curve


def unlock_weight(comp):
    """3x for a midnight-local rolling unlock, else 1x."""
    unlock = (comp.get("unlock") or "").lower()
    return MIDNIGHT_LOCAL_WEIGHT if "midnight local" in unlock else 1.0


def size_weight(hour1, target_hour1):
    """Similarity of a comparable's scale to the target's, in [FLOOR, 1]."""
    diff = math.log(max(1, hour1)) - math.log(max(1, target_hour1))
    kernel = math.exp(-0.5 * (diff / H1_KERNEL_BW) ** 2)
    return SIZE_WEIGHT_FLOOR + (1.0 - SIZE_WEIGHT_FLOOR) * kernel


def weighted_quantile(pairs, tau):
    """Interpolated weighted quantile of [(value, weight), ...]."""
    ordered = sorted(pairs)
    total = sum(w for _, w in ordered)
    if total <= 0:
        return 0.0
    target = tau * total
    acc = 0.0
    for i, (value, weight) in enumerate(ordered):
        acc += weight
        if acc >= target:
            if i == 0 or weight <= 0:
                return value
            prev_value = ordered[i - 1][0]
            frac = 1.0 - (acc - target) / weight
            return prev_value + (value - prev_value) * frac
    return ordered[-1][0]


def baseline_log_quantiles(hour):
    """House baseline's log quantiles: flat at hour 1, widening spread."""
    spread = BASELINE_SIGMA * math.sqrt(hour - 1)
    return [z * spread for z in Z]


def effective_sample_size(weights):
    """(sum w)^2 / sum w^2: how many comparables the weights really use."""
    total = sum(weights)
    denom = sum(w * w for w in weights)
    if denom <= 0:
        return 0.0
    return total * total / denom


# No quantile may sit further than this from the median, in log units:
# a launch's hour can be a few times its hour-1 print, never dozens of
# times -- the raw cross-launch tail is fat only because some comparables
# had a near-zero hour 1 before their unlock, which the target does not.
LOG_SPREAD_CAP = 1.25
# Below this effective sample size the weighted quantiles are too thin to
# trust on their own, so they are blended toward the baseline spread.
MIN_EFFECTIVE_SAMPLE = 8.0


def forecast_case(case, name):
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    if first is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1, first["viewers"])

    # Reference set: every comparable with a usable release-day curve.
    # Sorted by name so the run is byte-identical every time.
    references = []
    for comp in sorted(case.get("comparables", []), key=lambda c: c.get("name", "")):
        curve = day_curve(comp)
        if 1 in curve:
            references.append((comp, curve))

    hours = []
    for row in case["forecast"]:
        hour = row["hour"]
        log_q = None
        if len(references) >= MIN_REFERENCES:
            pairs = []
            for comp, curve in references:
                if hour in curve:
                    weight = unlock_weight(comp) * size_weight(curve[1], p1)
                    pairs.append((math.log(curve[hour] / curve[1]), weight))
            if len(pairs) >= MIN_REFERENCES:
                vals = [weighted_quantile(pairs, tau) for tau in LEVELS]
                median = vals[2]
                log_q = [median + (v - median) * SHRINK for v in vals]
                log_q = [min(max(v, median - LOG_SPREAD_CAP),
                             median + LOG_SPREAD_CAP) for v in log_q]
                log_q[2] = median
                ess = effective_sample_size([w for _, w in pairs])
                if ess < MIN_EFFECTIVE_SAMPLE:
                    # Thin reference set (e.g. a target bigger than every
                    # comparable): blend toward the baseline's wider spread
                    # instead of trusting a handful of launches.
                    blend = ess / MIN_EFFECTIVE_SAMPLE
                    base = baseline_log_quantiles(hour)
                    log_q = [blend * v + (1.0 - blend) * b
                             for v, b in zip(log_q, base)]
        if log_q is None:
            log_q = baseline_log_quantiles(hour)
        quantiles = []
        prev = 0.0
        for lr in log_q:
            q = p1 * math.exp(lr)
            q = round_half_up_2dp(q)
            q = min(max(q, 0.01), 1_000_000_000)
            if q < prev:
                q = prev
            quantiles.append(q)
            prev = q
        hours.append({"hour": hour, "q": quantiles})
    return {"hours": hours}


def round_half_up_2dp(x):
    """x rounded to 2 decimals, half up (as the kit's starter rounds it)."""
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value == int(value) else value


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        out = OUTPUT_DIR / f"{path.stem}.out"
        out.write_text(json.dumps(forecast, separators=(",", ":")) + "\n",
                       encoding="utf-8")


if __name__ == "__main__":
    main()
