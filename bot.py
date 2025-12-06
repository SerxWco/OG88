import json
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from collections import deque
from pathlib import Path
from typing import Deque, Optional, Set
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.error import Forbidden
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from wchain_api import WChainAPI
from config import (
    TELEGRAM_BOT_TOKEN,
    BURN_WALLET_ADDRESS,
    OG88_TOKEN_ADDRESS,
    BURN_MONITOR_POLL_SECONDS,
    BURN_ALERT_ANIMATION_URL,
    BURN_ALERT_VIDEO_PATH,
    BIG_BUY_ALERT_ANIMATION_URL,
    BIG_BUY_ALERT_VIDEO_PATH,
    OG88_BIG_BUY_THRESHOLD_USD,
    OG88_BUY_MONITOR_POLL_SECONDS,
    OG88_LIQUIDITY_ADDRESSES,
    OG88_WEBAPP_URL,
)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize W-Chain API
wchain_api = WChainAPI()

# Burn addresses to include wherever aggregate burn totals are required
BURN_ADDRESSES: Set[str] = {BURN_WALLET_ADDRESS}
SCAN_BASE_URL = "https://scan.w-chain.com"
OG88_CONTRACT_ADDRESS = "0xD1841fC048b488d92fdF73624a2128D10A847E88"
WEBAPP_HISTORY_KEY = "webapp_results"
WEBAPP_HISTORY_LIMIT = 25

def format_number(num: float, decimals: int = 2) -> str:
    """Format large numbers with appropriate suffixes"""
    if num >= 1e9:
        return f"{num/1e9:.{decimals}f}B"
    elif num >= 1e6:
        return f"{num/1e6:.{decimals}f}M"
    elif num >= 1e3:
        return f"{num/1e3:.{decimals}f}K"
    else:
        return f"{num:.{decimals}f}"

def format_price(price: float) -> str:
    """Format price with appropriate decimal places"""
    if price >= 1:
        return f"${price:,.4f}"
    elif price >= 0.01:
        return f"${price:,.6f}"
    else:
        return f"${price:,.8f}"

def format_wco_price(price: float) -> str:
    """Format WCO price without $ symbol"""
    if price >= 1:
        return f"{price:,.4f}"
    elif price >= 0.01:
        return f"{price:,.6f}"
    else:
        return f"{price:,.8f}"


def format_timestamp(timestamp: str) -> str:
    """Convert API timestamp into a user-friendly UTC string."""
    if not timestamp:
        return "Unknown"
    try:
        ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        return ts.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    except ValueError:
        return timestamp


def ensure_burn_state(bot_data: dict) -> dict:
    """Ensure burn monitoring state exists in bot_data."""
    if "burn_watch_state" not in bot_data:
        bot_data["burn_watch_state"] = {"last_hash": None}
    return bot_data["burn_watch_state"]


def ensure_burn_subscribers(bot_data: dict) -> Set[int]:
    """Ensure subscriber set exists in bot_data."""
    if "burn_watch_subscribers" not in bot_data:
        bot_data["burn_watch_subscribers"] = set()
    return bot_data["burn_watch_subscribers"]


def ensure_big_buy_state(bot_data: dict) -> dict:
    """Ensure the big buy monitoring cursor exists."""
    if "big_buy_state" not in bot_data:
        bot_data["big_buy_state"] = {"last_hash": None}
    return bot_data["big_buy_state"]


def ensure_big_buy_subscribers(bot_data: dict) -> Set[int]:
    """Ensure the big buy subscriber set exists."""
    if "big_buy_subscribers" not in bot_data:
        bot_data["big_buy_subscribers"] = set()
    return bot_data["big_buy_subscribers"]


def ensure_webapp_history(bot_data: dict) -> Deque[dict]:
    """Keep a rolling log of webapp payloads for future tournaments."""
    if WEBAPP_HISTORY_KEY not in bot_data:
        bot_data[WEBAPP_HISTORY_KEY] = deque(maxlen=WEBAPP_HISTORY_LIMIT)
    history = bot_data[WEBAPP_HISTORY_KEY]
    if isinstance(history, deque):
        return history
    # In case something else stored a different type, reset it
    bot_data[WEBAPP_HISTORY_KEY] = deque(history, maxlen=WEBAPP_HISTORY_LIMIT) if isinstance(history, list) else deque(maxlen=WEBAPP_HISTORY_LIMIT)
    return bot_data[WEBAPP_HISTORY_KEY]


def build_webapp_markup() -> Optional[InlineKeyboardMarkup]:
    """Return the inline keyboard that launches the OG88 WebApp."""
    if not OG88_WEBAPP_URL:
        return None
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text="🎮 Launch OG88 Bamboo Bash",
                    web_app=WebAppInfo(url=OG88_WEBAPP_URL)
                )
            ]
        ]
    )


def format_recent_webapp_results(history: Deque[dict], limit: int = 5) -> str:
    """Summarize the latest WebApp submissions."""
    if not history:
        return "ℹ️ No OG88 Bamboo Bash sessions recorded yet. Launch the WebApp with /play."
    rows = []
    for idx, entry in enumerate(list(history)[:limit], start=1):
        display_name = entry.get("display_name") or entry.get("username") or f"User {entry.get('user_id')}"
        score_value = entry.get("score")
        if score_value is None:
            payload = entry.get("payload")
            if isinstance(payload, dict):
                score_value = payload.get("score") or payload.get("points")
        score_display = str(score_value) if score_value not in (None, "") else "data received"
        timestamp_display = entry.get("timestamp", "recently")
        rows.append(f"{idx}. {display_name} — {score_display} ({timestamp_display})")
    leaderboard = "\n".join(rows)
    return f"🏆 **Latest OG88 Bamboo Bash submissions**\n\n{leaderboard}\n\nSubmit a new run via /play."


async def ensure_channel_admin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    action_description: str
) -> bool:
    """
    Ensure the user invoking a command is allowed to manage chat-level settings.
    Non-admins in group chats cannot enable or disable shared alerts.
    """
    chat = update.effective_chat
    user = update.effective_user
    message = update.effective_message

    if not chat or not user or not message:
        return False

    if chat.type == "private":
        return True

    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
    except Exception as exc:
        logger.warning(
            "Unable to verify admin status for user %s in chat %s: %s",
            user.id,
            chat.id,
            exc
        )
        await message.reply_text("⚠️ I couldn't verify your admin status. Please try again.")
        return False

    if getattr(member, "status", "") not in {"administrator", "creator"}:
        await message.reply_text(f"❌ Only channel admins can {action_description}.")
        return False

    return True


def normalize_token_amount(raw_value: str, decimals: int) -> Decimal:
    """Return a Decimal token amount given raw blockchain value and decimals."""
    try:
        value = Decimal(raw_value or "0")
    except (InvalidOperation, TypeError):
        return Decimal("0")
    try:
        precision = Decimal(10) ** int(decimals)
    except (InvalidOperation, TypeError, ValueError):
        precision = Decimal(10) ** 18
    return value / precision


def format_token_amount(amount: Decimal) -> str:
    """Format token amount removing trailing zeros."""
    formatted = f"{amount:,.4f}"
    return formatted.rstrip('0').rstrip('.') if '.' in formatted else formatted

def format_supply_value(amount: Optional[Decimal]) -> str:
    """Return a human-friendly supply string or N/A if missing."""
    if amount is None:
        return "N/A"
    return format_token_amount(amount)


def format_usd_threshold() -> str:
    """Return the configured USD buy threshold with two decimal places."""
    return f"${float(OG88_BIG_BUY_THRESHOLD_USD):,.2f}"


def compute_big_buy_token_threshold(price_data: Optional[dict]) -> Optional[Decimal]:
    """Convert the USD big buy threshold into OG88 units using the latest price."""
    if not price_data:
        return None
    price_value = price_data.get("price_usd")
    if price_value in (None, "", 0):
        return None
    try:
        price_decimal = Decimal(str(price_value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if price_decimal <= 0:
        return None
    return OG88_BIG_BUY_THRESHOLD_USD / price_decimal


def format_buy_threshold_summary(token_amount: Optional[Decimal]) -> str:
    """Describe the buy alert threshold in USD and approximate OG88."""
    usd_display = format_usd_threshold()
    if token_amount is None:
        return f"{usd_display} (awaiting price feed for OG88 amount)"
    return f"{usd_display} (~{format_token_amount(token_amount)} OG88)"


def format_buy_event_summary(event: dict) -> str:
    """Return a Markdown snippet describing a big buy event."""
    amount = event.get("amount") or Decimal("0")
    amount_str = format_token_amount(amount)
    buyer = event.get("to", {}).get("hash") or "Unknown"
    timestamp = format_timestamp(event.get("timestamp"))
    tx_hash = event.get("transaction_hash", "")
    tx_url = f"{SCAN_BASE_URL}/tx/{tx_hash}" if tx_hash else SCAN_BASE_URL

    summary = (
        f"• `{buyer}` scooped *{amount_str} OG88*\n"
        f"  🕒 {timestamp}\n"
    )
    if tx_hash:
        summary += f"  🔗 [Transaction]({tx_url})\n"
    return summary

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    message = update.effective_message
    if not message:
        return
    welcome_message = f"""
🐼 **OG88 Meme Bot**

Welcome to the OG88 panda command center. This bot now focuses 100% on the
original meme coin of W Chain.

**Commands**
/price - OG88 spot price in USD + WCO
/supply - Current total vs burned supply
/holders - Wallet count pulled from W-Scan
/burnwatch - Toggle burn alerts for the panda furnace
/buys - Subscribe to >{format_usd_threshold()} buy alerts
/ca - OG88 contract address
/play - Launch OG88 Bamboo Bash WebApp

Use /price or /supply for the fastest status check. 🔥
"""
    reply_kwargs = {'parse_mode': 'Markdown'}
    markup = build_webapp_markup()
    if markup:
        reply_kwargs['reply_markup'] = markup
    await message.reply_text(welcome_message, **reply_kwargs)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    message = update.effective_message
    if not message:
        return
    help_message = f"""
📖 **OG88 Meme Bot Help**

**Core Commands**
/start - Quick intro and command list
/price - Spot price (USD + WCO) with timestamp
/supply - Total / burned / circulating snapshot
/holders - Total OG88 holder count
/burnwatch - Subscribe/unsubscribe from burn alerts
/buys - Subscribe/unsubscribe from big buy alerts (>{format_usd_threshold()})
/ca - Quick access to the OG88 contract
/play - Open the OG88 Bamboo Bash WebApp inside Telegram

**Data Sources**
• OG88 price feed (Railway OG88 API)
• W-Chain explorer counters & transfers
• Direct burn wallet + liquidity pool monitoring

**Tips**
• Use `/buys status` or `/burnwatch status` to confirm subscriptions
• Configure OG88 liquidity pool addresses via `OG88_LIQUIDITY_ADDRESSES`
• Use `/play recent` to review the last few recorded WebApp scores
    """
    await message.reply_text(help_message, parse_mode='Markdown')

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return a consolidated OG88 overview with key metrics and links."""
    message = update.effective_message
    if not message:
        return

    price_data = wchain_api.get_og88_price() or {}
    supply_info = wchain_api.get_og88_supply_overview(burn_addresses=BURN_ADDRESSES)
    counters = wchain_api.get_og88_counters() or {}

    price_display = "N/A"
    price_usd_value = price_data.get("price_usd")
    if price_usd_value not in (None, "", 0):
        try:
            price_display = format_price(float(price_usd_value))
        except (ValueError, TypeError):
            price_display = "N/A"

    wco_display = "N/A"
    price_wco_value = price_data.get("price_wco")
    if price_wco_value not in (None, "", 0):
        try:
            wco_display = f"{format_wco_price(float(price_wco_value))} WCO"
        except (ValueError, TypeError):
            wco_display = "N/A"

    market_cap_display = "N/A"
    market_cap_value = price_data.get("market_cap")
    if market_cap_value not in (None, "", 0):
        try:
            market_cap_display = f"${format_number(float(market_cap_value), 2)}"
        except (ValueError, TypeError):
            market_cap_display = "N/A"

    total_supply_display = "N/A"
    burned_display = "N/A"
    circulating_display = "N/A"
    if supply_info:
        total_supply_display = format_supply_value(supply_info.get("total_supply"))
        burned_display = format_supply_value(supply_info.get("burned"))
        circulating_display = format_supply_value(supply_info.get("circulating_supply"))

    holders_display = "N/A"
    transfers_display = "N/A"
    try:
        holders_count = counters.get("token_holders_count")
        if holders_count not in (None, ""):
            holders_display = f"{int(holders_count):,}"
        transfers_count = counters.get("transfers_count")
        if transfers_count not in (None, ""):
            transfers_display = f"{int(transfers_count):,}"
    except (ValueError, TypeError):
        pass

    timestamp_display = format_timestamp(price_data.get("last_updated"))
    if timestamp_display == "Unknown":
        timestamp_display = None

    response = (
        "🐼 **OG88 Quick Info**\n\n"
        f"💰 Price: {price_display} | {wco_display}\n"
        f"🏦 Market Cap: {market_cap_display}\n"
        f"📦 Total Supply: {total_supply_display} OG88\n"
        f"🔥 Burned: {burned_display} OG88\n"
        f"🚀 Circulating: {circulating_display} OG88\n"
        f"👥 Holders: {holders_display}\n"
        f"🔁 Transfers: {transfers_display}\n"
    )

    if timestamp_display:
        response += f"🕒 Updated: {timestamp_display}\n"

    response += (
        f"📜 Contract: `{OG88_CONTRACT_ADDRESS}`\n"
        "🌐 Site: [og88.meme](https://og88.meme)\n"
    )

    await message.reply_text(
        response,
        parse_mode='Markdown',
        disable_web_page_preview=True
    )

async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return OG88 price information in USD and WCO."""
    message = update.effective_message
    if not message:
        return
    await message.reply_text("🔄 Fetching OG88 price data...")

    price_data = wchain_api.get_og88_price()

    if not price_data:
        await message.reply_text("❌ Unable to fetch OG88 price. Please try again later.")
        return

    price_usd = float(price_data.get("price_usd") or 0)
    market_cap = price_data.get("market_cap")
    last_updated = format_timestamp(price_data.get("last_updated"))

    price_display = format_price(price_usd)

    cap_display = "N/A"
    if market_cap not in (None, "", 0):
        try:
            cap_value = float(market_cap)
            cap_display = f"${format_number(cap_value, 2)}"
        except (ValueError, TypeError):
            pass

    timestamp_display = last_updated if last_updated and last_updated != "Unknown" else None

    response = "🚨 OG88 JUST WOKE UP HUNGRY AF 🐼🔥\n"
    response += f"💰 Price: {price_display} – still stupid cheap, fix that\n"
    response += f"💥 Market Cap: ONLY {cap_display} – about to get wrecked upwards\n"
    if timestamp_display:
        response += f"🕒 {timestamp_display}\n"
    else:
        response += "🕒 Timestamp unavailable\n"
    response += "Buyback burns + panda army loading…"

    await message.reply_text(response, parse_mode='Markdown')

async def supply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get OG88 supply and burn information."""
    message = update.effective_message
    if not message:
        return
    await message.reply_text("🔄 Fetching OG88 supply data...")

    supply_info = wchain_api.get_og88_supply_overview(burn_addresses=BURN_ADDRESSES)

    if not supply_info:
        await message.reply_text("❌ Unable to fetch OG88 supply data. Please try again later.")
        return

    total_display = format_supply_value(supply_info.get("total_supply"))
    burned_display = format_supply_value(supply_info.get("burned"))
    circulating_display = format_supply_value(supply_info.get("circulating_supply"))

    response = "🐼 OG88 SUPPLY IS INSANE RIGHT NOW\n"
    response += f"✅ Circulating: {circulating_display} ANDA (basically maxed)\n"
    response += f"🔥 Burned: {burned_display} OG88 sent to hell forever\n"
    response += f"📦 Total ever: ONLY {total_display} OG88\n"
    response += "Fixed supply + buybacks eating the rest = your bags about to get thicc 🚀\n"
    response += "#OG88 #PandaPrinter"

    await message.reply_text(response, parse_mode='Markdown')


async def contract_address_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Share the OG88 contract address."""
    message = update.effective_message
    if not message:
        return
    response = (
        "📜 **OG88 Contract Address**\n\n"
        f"`{OG88_CONTRACT_ADDRESS}`\n\n"
        "Add it to your wallet or share with fellow pandas."
    )
    await message.reply_text(response, parse_mode='Markdown')


async def holders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get OG88 holder and transfer counts."""
    message = update.effective_message
    if not message:
        return
    await message.reply_text("🔄 Fetching OG88 holders...")

    counters = wchain_api.get_og88_counters()
    if not counters:
        await message.reply_text("❌ Unable to fetch holder information. Please try again later.")
        return

    holders_count = int(counters.get('token_holders_count', 0))
    transfers_count = int(counters.get('transfers_count', 0))

    response = "👥 **OG88 Holders**\n\n"
    response += f"Total Holders: {holders_count:,}\n"
    response += f"Transfers Recorded: {transfers_count:,}\n"
    response += "\n📊 *Source: W-Chain Explorer Counters*"

    await message.reply_text(response, parse_mode='Markdown')


async def play_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Launch the OG88 Bamboo Bash Telegram WebApp or show recent scores."""
    message = update.effective_message
    if not message:
        return

    if not OG88_WEBAPP_URL:
        await message.reply_text(
            "⚠️ The OG88 WebApp URL is not configured. Set OG88_WEBAPP_URL in your environment."
        )
        return

    request = (context.args[0].lower() if context.args else "").strip()
    if request in {"recent", "scores", "leaderboard"}:
        history = ensure_webapp_history(context.application.bot_data)
        summary = format_recent_webapp_results(history)
        await message.reply_text(summary, parse_mode='Markdown', disable_web_page_preview=True)
        return

    markup = build_webapp_markup()
    description = (
        "🎮 **OG88 Bamboo Bash**\n\n"
        "Tap the button below to open the official OG88 mini-game directly inside Telegram. "
        "Your session automatically includes Telegram user context so we can track scores "
        "and organize tournaments later on.\n\n"
        "Use `/play recent` anytime to see the latest submissions."
    )
    await message.reply_text(
        description,
        parse_mode='Markdown',
        reply_markup=markup
    )


async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Capture payloads sent from the Telegram WebApp and acknowledge receipt."""
    message = update.effective_message
    web_app_payload = message.web_app_data if message else None
    if not message or not web_app_payload:
        return

    user = update.effective_user
    raw_data = web_app_payload.data or ""
    try:
        parsed_data = json.loads(raw_data) if raw_data else {}
    except json.JSONDecodeError:
        parsed_data = raw_data

    score_value = None
    if isinstance(parsed_data, dict):
        for key in ("score", "points", "value", "bestScore", "highscore"):
            if key in parsed_data:
                score_value = parsed_data[key]
                break

    timestamp_display = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    history = ensure_webapp_history(context.application.bot_data)
    display_name = user.full_name if user and user.full_name else (
        user.username if user and user.username else "Unknown player"
    )
    history.appendleft(
        {
            "user_id": user.id if user else None,
            "username": user.username if user else None,
            "display_name": display_name,
            "score": score_value,
            "payload": parsed_data,
            "raw": raw_data,
            "timestamp": timestamp_display,
        }
    )

    if score_value not in (None, ""):
        reply_text = (
            f"🏁 Recorded {display_name}'s score: *{score_value}*.\n"
            "We'll use this data to seed OG88 tournaments soon!"
        )
    else:
        reply_text = (
            "✅ Received your OG88 Bamboo Bash data. Stay tuned for tournament brackets!"
        )
    await message.reply_text(reply_text, parse_mode='Markdown')


async def burnwatch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manage OG88 burn alert subscriptions."""
    message = update.effective_message
    if not update.effective_chat or not message:
        return
    chat_id = update.effective_chat.id
    subscribers = ensure_burn_subscribers(context.application.bot_data)
    burn_state = ensure_burn_state(context.application.bot_data)
    action = (context.args[0].lower() if context.args else "").strip()
    manage_description = "enable or disable burn alerts"
    if action in {"off", "stop", "unsubscribe"}:
        if not await ensure_channel_admin(update, context, manage_description):
            return
        if chat_id in subscribers:
            subscribers.remove(chat_id)
            await message.reply_text("🛑 Burn alerts disabled for this chat.")
        else:
            await message.reply_text("ℹ️ Burn alerts are already disabled here.")
        return
    if action == "status":
        count = len(subscribers)
        status = "subscribed" if chat_id in subscribers else "not subscribed"
        await message.reply_text(
            f"📊 Burn alert status: {status}. Total subscribers: {count}."
        )
        return

    if not await ensure_channel_admin(update, context, manage_description):
        return

    if chat_id in subscribers:
        await message.reply_text("✅ Burn alerts already enabled for this chat.")
        return
    subscribers.add(chat_id)
    await message.reply_text(
        "🔥 Burn alerts enabled! You'll be notified whenever OG88 tokens reach "
        f"the burn wallet `{BURN_WALLET_ADDRESS}`.",
        parse_mode='Markdown'
    )
    if burn_state.get("last_hash") is None:
        recent_burns = wchain_api.get_recent_og88_burns(limit=1)
        if recent_burns:
            burn_state["last_hash"] = recent_burns[0].get("transaction_hash")
        else:
            logger.warning("Burn watch initialization failed: no recent burns found.")


async def buys_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manage OG88 big buy alert subscriptions."""
    message = update.effective_message
    if not update.effective_chat or not message:
        return

    if not OG88_LIQUIDITY_ADDRESSES:
        await message.reply_text(
            "⚠️ Big buy alerts require OG88 liquidity pool addresses. "
            "Please set OG88_LIQUIDITY_ADDRESSES in your environment."
        )
        return

    chat_id = update.effective_chat.id
    subscribers = ensure_big_buy_subscribers(context.application.bot_data)
    buy_state = ensure_big_buy_state(context.application.bot_data)
    action = (context.args[0].lower() if context.args else "").strip()
    price_data = wchain_api.get_og88_price()
    token_threshold = compute_big_buy_token_threshold(price_data)
    threshold_summary = format_buy_threshold_summary(token_threshold)
    manage_description = "enable or disable big buy alerts"

    if action in {"off", "stop", "unsubscribe"}:
        if not await ensure_channel_admin(update, context, manage_description):
            return
        if chat_id in subscribers:
            subscribers.remove(chat_id)
            await message.reply_text("🛑 Big buy alerts disabled for this chat.")
        else:
            await message.reply_text("ℹ️ Big buy alerts are already disabled here.")
        return

    if action == "status":
        count = len(subscribers)
        status = "subscribed" if chat_id in subscribers else "not subscribed"
        await message.reply_text(
            f"📊 Big buy alerts are {status}. Threshold: {threshold_summary}. "
            f"Total subscribers: {count}."
        )
        return

    if action in {"latest", "recent"}:
        if token_threshold is None:
            await message.reply_text(
                f"❌ Unable to convert the {format_usd_threshold()} buy threshold into OG88 right now. "
                "Please try again shortly."
            )
            return
        events = wchain_api.get_recent_og88_buys(
            min_amount=token_threshold,
            limit=3
        )
        if events is None:
            await message.reply_text("❌ Unable to fetch recent buys. Please try again later.")
            return
        if not events:
            await message.reply_text(
                f"ℹ️ No OG88 buys above {threshold_summary} in the latest blocks."
            )
            return
        response = "🐋 **Latest Big Buys**\n\n"
        response += "\n".join(format_buy_event_summary(event) for event in events)
        await message.reply_text(response, parse_mode='Markdown')
        return

    if not await ensure_channel_admin(update, context, manage_description):
        return

    if chat_id in subscribers:
        await message.reply_text(
            f"✅ Big buy alerts already enabled for buys above {threshold_summary}."
        )
        return

    subscribers.add(chat_id)
    await message.reply_text(
        "🐼 Panda scouts activated! You'll be pinged whenever "
        f"buys exceed {threshold_summary}."
    )

    if buy_state.get("last_hash") is None:
        if token_threshold is None:
            logger.info("Skipping big buy initialization because OG88 price is unavailable.")
            return
        recent_buys = wchain_api.get_recent_og88_buys(
            min_amount=token_threshold,
            limit=1
        )
        if recent_buys:
            buy_state["last_hash"] = recent_buys[0].get("transaction_hash")
        else:
            logger.info("Big buy watch initialized but no prior transactions were found.")


async def monitor_burn_wallet(context: ContextTypes.DEFAULT_TYPE):
    """Periodic job that checks the burn wallet for new OG88 transfers."""
    subscribers = ensure_burn_subscribers(context.application.bot_data)
    if not subscribers:
        return
    burn_state = ensure_burn_state(context.application.bot_data)
    recent_burns = wchain_api.get_recent_og88_burns(limit=5)
    if recent_burns is None:
        logger.warning("Unable to fetch recent OG88 burns.")
        return
    if not recent_burns:
        return
    last_seen_hash = burn_state.get("last_hash")
    if last_seen_hash is None:
        burn_state["last_hash"] = recent_burns[0].get("transaction_hash")
        logger.info("Initialized burn watch with tx %s", burn_state["last_hash"])
        return
    new_events = []
    for tx in recent_burns:
        tx_hash = tx.get("transaction_hash")
        if not tx_hash or tx_hash == last_seen_hash:
            break
        new_events.append(tx)
    if not new_events:
        return
    burn_state["last_hash"] = new_events[0].get("transaction_hash") or last_seen_hash
    for tx in reversed(new_events):
        await broadcast_burn_alert(tx, subscribers, context)


async def broadcast_burn_alert(transaction: dict, subscribers: Set[int], context: ContextTypes.DEFAULT_TYPE):
    """Send a burn alert message (and optional animation) to all subscribers."""
    total = transaction.get("total", {})
    token = transaction.get("token", {})
    decimals = total.get("decimals") or token.get("decimals") or 18
    amount = normalize_token_amount(total.get("value"), decimals)
    amount_str = format_token_amount(amount)
    price_data = wchain_api.get_og88_price() or {}
    price = price_data.get("price_usd")
    usd_display = "N/A"
    try:
        if price not in (None, "", 0):
            usd_value = amount * Decimal(str(price))
            usd_display = f"${usd_value:,.2f}"
    except (InvalidOperation, TypeError, ValueError):
        pass
    message = (
        f"🚨🚨 PANDA JUST ATE {amount_str} OG88 AND SPIT OUT THE ASHES 🔥🐼\n"
        f"{amount_str} OG88 ({usd_display}) PERMANENTLY DELETED FOREVER\n"
        "Supply just got even tighter while you were scrolling\n"
        "Every burn = richer holders 😈\n"
        "#OG88 #BurnPrinterGoBrrrrr"
    )
    local_video_path = Path(BURN_ALERT_VIDEO_PATH) if BURN_ALERT_VIDEO_PATH else None
    local_video_available = bool(local_video_path and local_video_path.is_file())
    if BURN_ALERT_VIDEO_PATH and not local_video_available:
        logger.warning("Burn alert video not found at %s", BURN_ALERT_VIDEO_PATH)
    for chat_id in list(subscribers):
        try:
            if local_video_available and local_video_path:
                with local_video_path.open("rb") as animation_file:
                    await context.bot.send_animation(
                        chat_id=chat_id,
                        animation=animation_file,
                        caption=message,
                        parse_mode='Markdown'
                    )
                continue
            if BURN_ALERT_ANIMATION_URL:
                await context.bot.send_animation(
                    chat_id=chat_id,
                    animation=BURN_ALERT_ANIMATION_URL,
                    caption=message,
                    parse_mode='Markdown'
                )
                continue
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
        except Forbidden:
            subscribers.remove(chat_id)
            logger.warning("Removed chat %s from burn alerts (forbidden).", chat_id)
        except Exception as exc:
            logger.warning("Unable to send burn alert to %s: %s", chat_id, exc)


async def monitor_big_buys(context: ContextTypes.DEFAULT_TYPE):
    """Periodic job that checks for OG88 buys above the configured threshold."""
    subscribers = ensure_big_buy_subscribers(context.application.bot_data)
    if not subscribers or not OG88_LIQUIDITY_ADDRESSES:
        return

    price_data = wchain_api.get_og88_price()
    token_threshold = compute_big_buy_token_threshold(price_data)
    if token_threshold is None:
        logger.warning("Skipping big buy scan: unable to convert USD threshold into OG88.")
        return

    buy_state = ensure_big_buy_state(context.application.bot_data)
    events = wchain_api.get_recent_og88_buys(
        min_amount=token_threshold,
        limit=5
    )
    if events is None:
        logger.warning("Unable to fetch recent OG88 buys.")
        return
    if not events:
        return

    last_seen_hash = buy_state.get("last_hash")
    if last_seen_hash is None:
        buy_state["last_hash"] = events[0].get("transaction_hash")
        logger.info("Initialized big buy watch with tx %s", buy_state["last_hash"])
        return

    new_events = []
    for event in events:
        tx_hash = event.get("transaction_hash")
        if not tx_hash or tx_hash == last_seen_hash:
            break
        new_events.append(event)

    if not new_events:
        return

    buy_state["last_hash"] = new_events[0].get("transaction_hash") or last_seen_hash

    for event in reversed(new_events):
        await broadcast_big_buy_alert(event, subscribers, context)


async def broadcast_big_buy_alert(event: dict, subscribers: Set[int], context: ContextTypes.DEFAULT_TYPE):
    """Send a big buy alert to all subscribers."""
    amount = event.get("amount") or Decimal("0")
    amount_str = format_token_amount(amount)
    price_data = wchain_api.get_og88_price() or {}

    usd_display = "N/A"
    wco_display = "N/A"

    try:
        price_usd = price_data.get("price_usd")
        if price_usd not in (None, "", 0):
            usd_value = amount * Decimal(str(price_usd))
            usd_display = f"${usd_value:,.2f}"
    except (InvalidOperation, TypeError, ValueError):
        pass

    try:
        price_wco = price_data.get("price_wco")
        if price_wco not in (None, "", 0):
            wco_value = amount * Decimal(str(price_wco))
            wco_display = f"{format_token_amount(wco_value)} WCO"
    except (InvalidOperation, TypeError, ValueError):
        pass

    buyer = event.get("to", {}).get("hash") or "Unknown"
    method = event.get("method") or "swap"
    timestamp = format_timestamp(event.get("timestamp"))
    tx_hash = event.get("transaction_hash", "")
    tx_url = f"{SCAN_BASE_URL}/tx/{tx_hash}" if tx_hash else SCAN_BASE_URL

    message = (
        "🐼 **OG88 BIG BUY ALERT!** 🐼\n\n"
        f"Wow! Someone just scooped up *{amount_str} OG88*!\n\n"
        f"💰 USD Value: {usd_display}\n"
        f"🪙 WCO Value: {wco_display}\n\n"
        f"Buyer: `{buyer}`\n"
        f"Method: {method}\n"
        f"⏱️ Time: {timestamp}\n"
        f"🔗 Tx: [View on W-Scan]({tx_url})\n\n"
        "🎉 Stay tuned — OG88 activity is heating up!"
    )

    video_path = Path(BIG_BUY_ALERT_VIDEO_PATH) if BIG_BUY_ALERT_VIDEO_PATH else None
    video_available = bool(video_path and video_path.is_file())
    animation_url = BIG_BUY_ALERT_ANIMATION_URL

    if BIG_BUY_ALERT_VIDEO_PATH and not video_available:
        logger.warning("Big buy alert video not found at %s", BIG_BUY_ALERT_VIDEO_PATH)

    caption = message
    for chat_id in list(subscribers):
        try:
            if video_available and video_path:
                with video_path.open("rb") as animation_file:
                    await context.bot.send_animation(
                        chat_id=chat_id,
                        animation=animation_file,
                        caption=caption,
                        parse_mode='Markdown'
                    )
                continue
            if animation_url:
                await context.bot.send_animation(
                    chat_id=chat_id,
                    animation=animation_url,
                    caption=caption,
                    parse_mode='Markdown'
                )
                continue
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
        except Forbidden:
            subscribers.remove(chat_id)
            logger.warning("Removed chat %s from big buy alerts (forbidden).", chat_id)
        except Exception as exc:
            logger.warning("Unable to send big buy alert to %s: %s", chat_id, exc)

def main():
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not found. Please set it in your environment variables.")
        return
    
    # Create the Application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    job_queue = application.job_queue
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("price", price_command))
    application.add_handler(CommandHandler("supply", supply_command))
    application.add_handler(CommandHandler("holders", holders_command))
    application.add_handler(CommandHandler("info", info_command))
    application.add_handler(CommandHandler("burnwatch", burnwatch_command))
    application.add_handler(CommandHandler("buys", buys_command))
    application.add_handler(CommandHandler("ca", contract_address_command))
    application.add_handler(CommandHandler("play", play_command))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    
    # Initialize burn watch data structures
    application.bot_data.setdefault("burn_watch_subscribers", set())
    application.bot_data.setdefault("burn_watch_state", {"last_hash": None})
    application.bot_data.setdefault("big_buy_subscribers", set())
    application.bot_data.setdefault("big_buy_state", {"last_hash": None})
    application.bot_data.setdefault(WEBAPP_HISTORY_KEY, deque(maxlen=WEBAPP_HISTORY_LIMIT))
    
    # Schedule burn monitoring job
    job_queue.run_repeating(
        monitor_burn_wallet,
        interval=BURN_MONITOR_POLL_SECONDS,
        first=10
    )
    job_queue.run_repeating(
        monitor_big_buys,
        interval=OG88_BUY_MONITOR_POLL_SECONDS,
        first=15
    )
    
    # Start the bot
    print("🤖 OG88 Meme Bot is starting...")
    print("Press Ctrl+C to stop the bot")
    
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Error running bot: {e}")

if __name__ == '__main__':
    main()
