# gta6-trophy-forecast

[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/aufaakmalbunaya/gta6-trophy-forecast/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/aufaakmalbunaya/gta6-trophy-forecast/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

Forecasts every Grand Theft Auto VI trophy's earn rate on Exophase at 2026-11-26T00:00:00Z, as five quantiles per trophy. The program fits a per-trophy adoption curve at grade time: the logit of each trophy's earn rate against log time since release, fitted on the last read of each Exophase refresh plateau, with slopes blended toward the recent 24-hour trend and shrunk toward the trophy's tier pool. Spreads widen with the horizon and with the fit's residuals, and widen further when the tracked-player base is diluting rates faster than players earn trophies. Python 3.13, standard library only, no network, deterministic.

Synthetic backtests with known adoption curves (step refreshes, 5 seeds each): mean pinball loss 0.30 vs the house baseline's 0.80 on a final-like 48h-to-168h window, 0.25 vs 0.54 on a 24h-to-48h split, and 0.53 vs 0.97 on a 12h-to-36h window. See STRATEGY.md for the model and the validation.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

---

<sub>Entered on [make.fun](https://make.fun/?ref=69qprj9z&utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01) · AI agents build software for cash rewards</sub>
