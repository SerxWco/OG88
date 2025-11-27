# OG88 Telegram Bot

A Telegram bot dedicated to OG88 (a.k.a. ANDA), the original meme coin on W Chain. The bot exposes quick chat commands for price, supply, and holder stats, and it can broadcast automated alerts when the burn wallet receives tokens or when whales scoop large buys.

## Features
- **Live price snapshot** – `/price` returns USD + WCO pricing plus the latest timestamp
- **Supply + burn overview** – `/supply` summarizes total minted, burned forever, and circulating OG88
- **Holder stats** – `/holders` displays the on-chain holder and transfer counts straight from W-Scan
- **Burn alerts** – `/burnwatch` lets chats subscribe/unsubscribe from OG88 burn events (with optional animation/video attachments)
- **Big buy alerts** – `/buys` subscribes chats to whale alerts when purchases exceed the configured ANDA threshold; `/buys latest` shows recent qualifying buys on demand

## Commands at a Glance
```
/start      # Welcome message + quick links
/help       # Command reference and tips
/price      # OG88 price in USD and WCO
/supply     # Total vs burned vs circulating OG88
/holders    # Total holder count + transfer count
/burnwatch  # Manage burn alert subscriptions (status/off)
/buys       # Manage big-buy alerts (> threshold)
```

## Alert Subscriptions
- `/burnwatch` – toggles OG88 burn notifications sent whenever the configured burn wallet receives tokens. Use `/burnwatch status` or `/burnwatch off` to manage the subscription.
- `/buys` – toggles whale alerts whenever a transfer *from* one of the configured liquidity pool contracts to a buyer wallet exceeds the threshold (default: 100 ANDA). Supports `/buys status`, `/buys off`, and `/buys latest`.

## Configuration
Create a `.env` file (or set environment variables) with at least the Telegram token. Optional values let you tune the alert system.

| Variable | Required | Description |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | ✅ | Token from @BotFather |
| `OG88_LIQUIDITY_ADDRESSES` | ⚙️ | Comma-separated list of pool addresses treated as sellers (defaults to the WLP V2 contract) |
| `OG88_BIG_BUY_THRESHOLD` | ⚙️ | Minimum ANDA amount (Decimal) that triggers a whale alert (default `100`) |
| `OG88_BUY_MONITOR_POLL_SECONDS` | ⚙️ | Poll frequency for whale alerts (defaults to `BURN_MONITOR_POLL_SECONDS`) |
| `BURN_WALLET_ADDRESS` | ⚙️ | Burn wallet to monitor (defaults to `0x0000…dEaD`) |
| `BURN_MONITOR_POLL_SECONDS` | ⚙️ | Poll frequency for burn alerts (default `60`) |
| `BURN_ALERT_ANIMATION_URL` | ⚙️ | Optional GIF/animation URL appended to burn alerts |
| `BURN_ALERT_VIDEO_PATH` | ⚙️ | Optional local video sent with burn alerts (`Assets/burn.mp4` by default) |
| `BIG_BUY_ALERT_VIDEO_PATH` | ⚙️ | Optional local video sent with big buy alerts (`Assets/buy.mp4` by default) |

All other endpoints (price oracle, explorer API, etc.) are configured in `config.py` but can be overridden via environment variables if needed.

## Setup
1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
2. **Create the `.env` file**
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token
   # Optional overrides
   # OG88_LIQUIDITY_ADDRESSES=0xPool1,0xPool2
   # OG88_BIG_BUY_THRESHOLD=250
   # BURN_ALERT_ANIMATION_URL=https://...
   ```
3. **Start the bot**
   ```bash
   python bot.py
   ```

## Data Sources
- **OG88 price** – Railway-hosted OG88 price API (USD + WCO quotes)
- **Supply + holders** – W-Chain explorer (via the Blockscout-compatible API)
- **Burn + buy alerts** – Direct explorer polling of the burn wallet and OG88 liquidity pool transfers

## File Overview
```
bot.py         # Telegram command handlers + alert jobs
wchain_api.py  # HTTP helpers and lightweight caching
config.py      # Environment/config parsing helpers
requirements.txt
README.md
```

## Troubleshooting
- **Bot silent?** Double-check `TELEGRAM_BOT_TOKEN` and ensure the process is running (`python bot.py`).
- **No whale alerts?** Confirm `OG88_LIQUIDITY_ADDRESSES` contains the active pool address and that the threshold is realistic relative to current trading volume.
- **Missing burn animations?** Ensure the URL/path defined in `BURN_ALERT_ANIMATION_URL` or `BURN_ALERT_VIDEO_PATH` is reachable/readable by the bot.
- **Missing buy videos?** Confirm `BIG_BUY_ALERT_VIDEO_PATH` points to an accessible file (defaults to `Assets/buy.mp4`).

Feel free to open issues or PRs to extend the bot (e.g., adding new OG88 data sources or more alert types).