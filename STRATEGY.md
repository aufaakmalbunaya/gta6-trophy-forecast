# Strategy

## What the program does

`main.py` reads one case file (`<id>.in`) and writes `<id>.out` with five
quantiles of each trophy's earn rate at the case target.

1. **Refresh plateaus.** Exophase only moves the rates at its own refreshes,
   so consecutive reads with identical rates are one observation. The history
   is collapsed to the last read of each plateau; raw reads would overweight
   the frozen page.
2. **Per-trophy curve fit.** For each trophy, the logit of its earn rate is
   fitted by weighted least squares against `ln(1 + hours since release)`.
   The slope is a blend of the full-history fit (40%) and the last-24-hour
   fit (60%), then shrunk toward the trophy tier's pooled slope (platinum,
   gold, silver, bronze). The forecast is anchored on the last observed rate
   and read at the target, with the total logit move capped to [-1.5, +3.0].
3. **Flat-history case.** When the history holds a single plateau (no refresh
   seen yet, like the practice cases), the median is shifted down 0.5 logit:
   launch night's first refresh cut every rate but the 100% one as the
   tracked base jumped 638 to 3,868 players.
4. **Spreads.** The logit spread combines the fit's residual spread with a
   random-walk term that grows with the square root of the horizon in days.
   When dilution is detected (tracked players grew 2x or more while the
   median rate fell from its in-history peak), the spread widens 1.5x, up to
   2.0 logit units.
5. **Caps.** The platinum is capped at the lowest of the other trophies'
   matching quantiles (it requires every other trophy). A trophy at 99.99%
   stays near-universal with a narrow spread. All quantiles are monotone and
   inside [0.01, 99.99].

The program is deterministic (no randomness), runs in about 0.05 s per case,
and uses only the Python standard library.

## Validation

- **Practice cases p00/p01:** valid JSON shape, all 55 trophy ids, monotone
  quantiles, under 65,536 bytes, byte-identical across two runs.
- **Synthetic backtests** (fake histories with known logistic adoption curves
  in log time plus Exophase-style step refreshes; 5 seeds each, mean pinball
  loss on the logit scale, lower is better):

  | window | this entry | house baseline |
  | --- | --- | --- |
  | 48h history, forecast 168h (final-like) | 0.298 | 0.795 |
  | 24h history, forecast 48h (split-half) | 0.254 | 0.543 |
  | 12h history, forecast 36h | 0.533 | 0.973 |

- **Dilution stress test** (rates = earners / tracked, tracked growing fast
  early so rates first fall then rise): final-like window 3.72 vs baseline
  3.85; both models struggle there because the true rates swing by orders of
  magnitude, and the entry is honest about that limit. The widening spread
  under dilution is the mitigation.
- **Edge cases:** a single read, all-identical reads, null rates (including
  a trophy null in every read), and a two-read history all produce a valid
  file without crashing.
