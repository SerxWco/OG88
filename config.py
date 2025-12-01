import os
from decimal import Decimal, InvalidOperation
from typing import List, Optional

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


def _get_env_list(key: str, default: Optional[str] = None) -> List[str]:
    """Return a normalized list parsed from a comma-separated environment entry."""
    raw_value = _get_env(key, default)
    if not raw_value:
        return []
    return [item.strip().lower() for item in raw_value.split(',') if item.strip()]


def _get_decimal_env(key: str, default: str) -> Decimal:
    """Parse a Decimal from the environment or fall back to the provided default."""
    raw_value = _get_env(key)
    if raw_value is None:
        return Decimal(default)
    try:
        return Decimal(raw_value)
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _get_decimal_env_any(keys: List[str], default: str) -> Decimal:
    """Parse a Decimal using the first valid environment key in the provided list."""
    for key in keys:
        raw_value = _get_env(key)
        if raw_value is None:
            continue
        try:
            return Decimal(raw_value)
        except (InvalidOperation, ValueError):
            continue
    return Decimal(default)


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
BURN_MONITOR_POLL_SECONDS = int(_get_env('BURN_MONITOR_POLL_SECONDS', '60'))
BURN_ALERT_ANIMATION_URL = (_get_env('BURN_ALERT_ANIMATION_URL', '') or '').strip() or None
BURN_ALERT_VIDEO_PATH = (_get_env('BURN_ALERT_VIDEO_PATH', 'Assets/burn.mp4') or '').strip() or None
BIG_BUY_ALERT_ANIMATION_URL = (_get_env('BIG_BUY_ALERT_ANIMATION_URL', '') or '').strip() or None
BIG_BUY_ALERT_VIDEO_PATH = (_get_env('BIG_BUY_ALERT_VIDEO_PATH', 'Assets/buy.mp4') or '').strip() or None

OG88_TOKEN_ADDRESS = _get_env('OG88_TOKEN_ADDRESS', '0xD1841fC048b488d92fdF73624a2128D10A847E88').lower()
BURN_WALLET_ADDRESS = _get_env('BURN_WALLET_ADDRESS', '0x000000000000000000000000000000000000dEaD').lower()
OG88_LIQUIDITY_ADDRESSES = set(_get_env_list('OG88_LIQUIDITY_ADDRESSES', '0xC61856cdf226645eaB487352C031Ec4341993F87'))
# Interpreted in USD so we can convert to tokens at runtime; support legacy env name
OG88_BIG_BUY_THRESHOLD_USD = _get_decimal_env_any(
    ['OG88_BIG_BUY_THRESHOLD_USD', 'OG88_BIG_BUY_THRESHOLD'],
    '50'
)
OG88_BUY_MONITOR_POLL_SECONDS = int(
    _get_env('OG88_BUY_MONITOR_POLL_SECONDS', str(BURN_MONITOR_POLL_SECONDS))
)

# Cache settings
CACHE_TTL = 120  # 2 minutes for supply info
PRICE_CACHE_TTL = 60  # 1 minute for price data
