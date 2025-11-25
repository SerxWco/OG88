import os
from typing import Optional

# Basic .env parsing so we can re-use values throughout the config file
_ENV_CACHE = {}
try:
    with open('.env', 'r', encoding='utf-8') as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            _ENV_CACHE[key.strip()] = value.strip()
except FileNotFoundError:
    pass


def _get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """Read configuration values with precedence: .env cache -> environment -> default."""
    return _ENV_CACHE.get(key) or os.getenv(key) or default


# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = _get_env('TELEGRAM_BOT_TOKEN')

# W-Chain API Endpoints
WCO_PRICE_API = "https://oracle.w-chain.com/api/price/wco"
WAVE_PRICE_API = "https://oracle.w-chain.com/api/price/wave"
WCO_SUPPLY_API = "https://oracle.w-chain.com/api/wco/supply-info"
HOLDERS_API = "https://scan.w-chain.com/api/v2/addresses"
OG88_PRICE_API = "https://og88-price-api-production.up.railway.app/price"
OG88_COUNTERS_API = "https://scan.w-chain.com/api/v2/tokens/0xD1841fC048b488d92fdF73624a2128D10A847E88/counters"
WAVE_COUNTERS_API = "https://scan.w-chain.com/api/v2/tokens/0x42AbfB13B4E3d25407fFa9705146b7Cb812404a0/counters"

# Block explorer / monitoring settings
BLOCKSCOUT_API_BASE = _get_env('BLOCKSCOUT_API_BASE', 'https://scan.w-chain.com/api/v2')
OG88_TOKEN_ADDRESS = _get_env('OG88_TOKEN_ADDRESS', '0xD1841fC048b488d92fdF73624a2128D10A847E88').lower()
BURN_WALLET_ADDRESS = _get_env('BURN_WALLET_ADDRESS', '0x000000000000000000000000000000000000dEaD').lower()
BURN_MONITOR_POLL_SECONDS = int(_get_env('BURN_MONITOR_POLL_SECONDS', '60'))
BURN_ALERT_ANIMATION_URL = (_get_env('BURN_ALERT_ANIMATION_URL', '') or '').strip() or None

# Cache settings
CACHE_TTL = 120  # 2 minutes for supply info
PRICE_CACHE_TTL = 60  # 1 minute for price data
