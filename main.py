"""Forecast GTA VI trophy earn rates on Exophase at 2026-11-26T00:00:00Z.

Model: per-trophy adoption curves fitted at grade time from the history the
program is given. For each trophy the logit of its earn rate is fitted against
log time since release, using only the last read of each Exophase refresh
plateau (rates sit flat between refreshes, so raw reads would overweight the
frozen page). The per-trophy slope is blended with the recent 24-hour slope
and shrunk toward its tier's pooled slope, then anchored on the last observed
rate and read at the target. Quantile spreads widen with the horizon and with
the fit's residuals, so a flat launch-night history still gets a wide,
refresh-aware band. Deterministic: no randomness, no network, stdlib only.
"""

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0, 0.674, 1.645]
RELEASE = datetime(2026, 11, 19, tzinfo=timezone.utc)

# Fallback median rate (percent) per tier when a trophy has no usable history.
TIER_PRIOR = {"platinum": 0.1, "gold": 0.5, "silver": 1.0, "bronze": 2.0}


def parse_time(text):
    """Parse an ISO 8601 UTC timestamp into an aware datetime."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def clamp_pct(x):
    return min(99.99, max(0.01, x))


def logit(pct):
    p = clamp_pct(pct) / 100.0
    return math.log(p / (1.0 - p))


def inv_logit(lg):
    if lg > 20:
        return 99.99
    if lg < -20:
        return 0.01
    return 100.0 / (1.0 + math.exp(-lg))


def round4(x):
    """Round to 4 decimals, half up, matching the house baseline's rounding."""
    scaled = x * 10000
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 10000
    return int(value) if value == int(value) else value


def median(values):
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return 0.0
    if n % 2:
        return ordered[n // 2]
    return (ordered[n // 2 - 1] + ordered[n // 2]) / 2.0


def plateaus(history):
    """Collapse the history to one point per refresh plateau.

    Exophase only moves the rates at its own refreshes, so consecutive reads
    with identical rates are one observation. The plateau's time is its last
    read: the refresh happened some time before that read, never after it.
    Returns a list of (time, players_tracked, rates tuple), oldest first.
    """
    out = []
    cur_rates = None
    cur_time = None
    cur_players = None
    for read in history:
        rates = tuple(read.get("rates") or [])
        if rates == cur_rates:
            cur_time = parse_time(read["at"])
            cur_players = read.get("players_tracked")
            continue
        if cur_rates is not None:
            out.append((cur_time, cur_players, cur_rates))
        cur_rates = rates
        cur_time = parse_time(read["at"])
        cur_players = read.get("players_tracked")
    if cur_rates is not None:
        out.append((cur_time, cur_players, cur_rates))
    return out


def wls_line(points):
    """Weighted least squares line y = a + b*x. Points are (x, y, w).

    Returns (a, b, residual_std) or None when the points do not pin a line.
    """
    if len(points) < 2:
        return None
    sw = sum(w for _, _, w in points)
    mx = sum(w * x for x, _, w in points) / sw
    my = sum(w * y for _, y, w in points) / sw
    sxx = sum(w * (x - mx) ** 2 for x, _, w in points)
    if sxx < 1e-9:
        return None
    sxy = sum(w * (x - mx) * (y - my) for x, y, w in points)
    b = sxy / sxx
    a = my - b * mx
    if len(points) >= 3:
        resid = [(y - (a + b * x)) for x, y, _ in points]
        var = sum(r * r for r in resid) / (len(points) - 2)
        std = math.sqrt(max(var, 0.0))
    else:
        std = 0.0
    return (a, b, std)


def trophy_series(plats, index, checkpoint):
    """(x, y, w) points for one trophy from the plateau list.

    x is ln(1 + hours since release), y the logit of the rate, w a recency
    weight that rises from 0.7 for the oldest plateau to 1.0 at the newest.
    """
    pts = []
    span = max(1.0, (checkpoint - plats[0][0]).total_seconds())
    for when, _players, rates in plats:
        if index >= len(rates) or rates[index] is None:
            continue
        rate = rates[index]
        if rate is None:
            continue
        hours = max(0.0, (when - RELEASE).total_seconds() / 3600.0)
        age = (when - plats[0][0]).total_seconds() / span
        pts.append((math.log1p(hours), logit(rate), 0.7 + 0.3 * age))
    return pts


def forecast_case(case, name):
    if case.get("levels", LEVELS) != LEVELS:
        raise ValueError(f"{name} asks for levels {case.get('levels')}, not {LEVELS}")
    trophies = case["trophies"]
    history = case.get("history") or []
    horizon_days = case["horizon_minutes"] / 1440.0
    target = parse_time(case["target"])
    checkpoint = parse_time(case["at"])
    x_target = math.log1p(max(0.0, (target - RELEASE).total_seconds() / 3600.0))

    plats = plateaus(history)
    single_plateau = len(plats) <= 1

    # Dilution flag: Exophase's tracked base can grow much faster than the
    # earners, so the median rate falls from its in-history peak even while
    # players keep earning. When that is happening the median is far less
    # certain than the fit's residuals suggest, so the spread widens below.
    def _med_rate(rates):
        vals = sorted(r for r in rates if r is not None)
        return vals[len(vals) // 2] if vals else 0.0

    dilution = False
    if len(plats) >= 2 and plats[0][1] and plats[-1][1]:
        peak = max(_med_rate(rates) for _w, _p, rates in plats)
        dilution = (plats[-1][1] >= 2 * plats[0][1]
                    and _med_rate(plats[-1][2]) < 0.9 * peak)

    # Last non-null rate per trophy, for anchoring and fallbacks.
    last_rate = []
    for i in range(len(trophies)):
        rate = None
        for _when, _pl, rates in reversed(plats):
            if i < len(rates) and rates[i] is not None:
                rate = rates[i]
                break
        last_rate.append(rate)

    # Per-trophy fits, then tier-pooled slopes for shrinkage.
    fits = []
    for i, trophy in enumerate(trophies):
        pts = trophy_series(plats, i, checkpoint)
        full = wls_line(pts)
        recent = None
        if len(pts) >= 3:
            cut = checkpoint.timestamp() - 24 * 3600
            # Rebuild recent points from plateau times, not from pts (no time kept).
            recent_pts = []
            span = max(1.0, (checkpoint - plats[0][0]).total_seconds())
            for when, _pl, rates in plats:
                if when.timestamp() < cut:
                    continue
                if i >= len(rates) or rates[i] is None:
                    continue
                hours = max(0.0, (when - RELEASE).total_seconds() / 3600.0)
                age = (when - plats[0][0]).total_seconds() / span
                recent_pts.append((math.log1p(hours), logit(rates[i]), 0.7 + 0.3 * age))
            if len(recent_pts) >= 2:
                recent = wls_line(recent_pts)
        slope = None
        resid = 0.0
        if full is not None:
            slope = full[1]
            resid = full[2]
            if recent is not None:
                slope = 0.6 * recent[1] + 0.4 * full[1]
                resid = max(resid, recent[2])
        fits.append({"points": pts, "slope": slope, "resid": resid})

    pooled = {}
    for tier in ("platinum", "gold", "silver", "bronze"):
        slopes = [f["slope"] for f, t in zip(fits, trophies)
                  if t.get("tier") == tier and f["slope"] is not None
                  and len(f["points"]) >= 3]
        pooled[tier] = median(slopes) if slopes else None
    all_slopes = [f["slope"] for f in fits if f["slope"] is not None
                  and len(f["points"]) >= 3]
    global_slope = median(all_slopes) if all_slopes else 0.0

    rows = []
    medians = []
    for i, trophy in enumerate(trophies):
        fit = fits[i]
        rate = last_rate[i]
        tier = trophy.get("tier") or "bronze"
        if rate is None:
            centre = logit(TIER_PRIOR.get(tier, 2.0))
            sigma = 1.2
        elif rate >= 99.99:
            # Everybody tracked already holds it; it stays (nearly) universal.
            centre = logit(99.99)
            sigma = 0.05
        else:
            pool = pooled.get(tier)
            if pool is None:
                pool = global_slope
            if fit["slope"] is None:
                slope = pool
            else:
                n = len(fit["points"])
                slope = (n * fit["slope"] + 3.0 * pool) / (n + 3.0)
            slope = min(2.0, max(-1.5, slope))
            x_last = fit["points"][-1][0] if fit["points"] else 0.0
            y_last = logit(rate)
            if single_plateau:
                # No refresh has been seen in the history, yet one is due:
                # launch night's first refresh cut every rate but the 100%
                # one as the tracked base jumped. Expect that dilution.
                delta = -0.5
                sigma = math.sqrt(0.5 ** 2 + (0.5 * math.sqrt(horizon_days)) ** 2)
            else:
                delta = slope * (x_target - x_last)
                delta = min(3.0, max(-1.5, delta))
                resid = min(0.8, max(0.12, fit["resid"]))
                sigma = math.sqrt(resid ** 2 + (0.45 * math.sqrt(horizon_days)) ** 2
                                  + 0.15 ** 2)
                if dilution:
                    sigma = min(2.0, sigma * 1.5)
                else:
                    sigma = min(1.6, sigma)
            centre = y_last + delta
        medians.append(inv_logit(centre))
        qs = []
        prev = None
        for z in Z:
            q = round4(clamp_pct(inv_logit(centre + z * sigma)))
            if prev is not None and q < prev:
                q = prev
            qs.append(q)
            prev = q
        rows.append({"id": trophy["id"], "q": qs})

    # The platinum requires every other trophy, so its rate cannot exceed
    # any other trophy's rate. Cap each of its quantiles at the lowest of
    # the other trophies' matching quantiles.
    plat_idx = [i for i, t in enumerate(trophies) if t.get("tier") == "platinum"]
    if plat_idx and len(rows) > 1:
        for pi in plat_idx:
            for k in range(5):
                cap = min(rows[i]["q"][k] for i in range(len(rows)) if i != pi)
                if rows[pi]["q"][k] > cap:
                    rows[pi]["q"][k] = cap
            # Re-enforce monotonicity after capping.
            for k in range(1, 5):
                if rows[pi]["q"][k] < rows[pi]["q"][k - 1]:
                    rows[pi]["q"][k] = rows[pi]["q"][k - 1]

    return {"trophies": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
