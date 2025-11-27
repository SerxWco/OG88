import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional, Set
from telegram import Update
from telegram.error import Forbidden
from telegram.ext import Application, CommandHandler, ContextTypes
from wchain_api import WChainAPI
from config import (
    TELEGRAM_BOT_TOKEN,
    BURN_WALLET_ADDRESS,
    OG88_TOKEN_ADDRESS,
    BURN_MONITOR_POLL_SECONDS,
    BURN_ALERT_ANIMATION_URL,
    BURN_ALERT_VIDEO_PATH,
    BIG_BUY_ALERT_VIDEO_PATH,
    OG88_BIG_BUY_THRESHOLD,
    OG88_BUY_MONITOR_POLL_SECONDS,
    OG88_LIQUIDITY_ADDRESSES,
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


def format_buy_event_summary(event: dict) -> str:
    """Return a Markdown snippet describing a big buy event."""
    amount = event.get("amount") or Decimal("0")
    amount_str = format_token_amount(amount)
    buyer = event.get("to", {}).get("hash") or "Unknown"
    timestamp = format_timestamp(event.get("timestamp"))
    tx_hash = event.get("transaction_hash", "")
    tx_url = f"{SCAN_BASE_URL}/tx/{tx_hash}" if tx_hash else SCAN_BASE_URL

    summary = (
        f"• `{buyer}` scooped *{amount_str} ANDA*\n"
        f"  🕒 {timestamp}\n"
    )
    if tx_hash:
        summary += f"  🔗 [Transaction]({tx_url})\n"
    return summary

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    welcome_message = """
🐼 **OG88 Meme Bot**

Welcome to the OG88 panda command center. This bot now focuses 100% on the
original meme coin of W Chain.

**Commands**
/price - OG88 spot price in USD + WCO
/supply - Current total vs burned supply
/holders - Wallet count pulled from W-Scan
/burnwatch - Toggle burn alerts for the panda furnace
/buys - Subscribe to >100 ANDA buy alerts

Use /price or /supply for the fastest status check. 🔥
"""
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    help_message = """
📖 **OG88 Meme Bot Help**

**Core Commands**
/start - Quick intro and command list
/price - Spot price (USD + WCO) with timestamp
/supply - Total / burned / circulating snapshot
/holders - Total OG88 holder count
/burnwatch - Subscribe/unsubscribe from burn alerts
/buys - Subscribe/unsubscribe from big buy alerts (>100 ANDA)

**Data Sources**
• OG88 price feed (Railway OG88 API)
• W-Chain explorer counters & transfers
• Direct burn wallet + liquidity pool monitoring

**Tips**
• Use `/buys status` or `/burnwatch status` to confirm subscriptions
• Configure OG88 liquidity pool addresses via `OG88_LIQUIDITY_ADDRESSES`
    """
    await update.message.reply_text(help_message, parse_mode='Markdown')

async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return OG88 price information in USD and WCO."""
    await update.message.reply_text("🔄 Fetching OG88 price data...")

    price_data = wchain_api.get_og88_price()

    if not price_data:
        await update.message.reply_text("❌ Unable to fetch OG88 price. Please try again later.")
        return

    price_usd = float(price_data.get("price_usd") or 0)
    price_wco = float(price_data.get("price_wco") or 0)
    market_cap = price_data.get("market_cap")
    last_updated = format_timestamp(price_data.get("last_updated"))

    message = "💰 **OG88 Price**\n\n"
    message += f"**USD:** {format_price(price_usd)}\n"
    message += f"**WCO:** {format_wco_price(price_wco)} WCO\n"

    if market_cap not in (None, "", 0):
        try:
            cap_value = float(market_cap)
            message += f"**Market Cap:** ${format_number(cap_value, 2)}\n"
        except (ValueError, TypeError):
            pass

    if last_updated and last_updated != "Unknown":
        message += f"\n🕒 Updated: {last_updated}\n"

    message += "\n📊 *Data from OG88 Price Oracle*"
    await update.message.reply_text(message, parse_mode='Markdown')

async def supply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get OG88 supply and burn information."""
    await update.message.reply_text("🔄 Fetching OG88 supply data...")

    supply_info = wchain_api.get_og88_supply_overview(burn_addresses=BURN_ADDRESSES)

    if not supply_info:
        await update.message.reply_text("❌ Unable to fetch OG88 supply data. Please try again later.")
        return

    total_display = format_supply_value(supply_info.get("total_supply"))
    burned_display = format_supply_value(supply_info.get("burned"))
    circulating_display = format_supply_value(supply_info.get("circulating_supply"))

    message = "📦 **OG88 Supply**\n\n"
    message += f"📉 Circulating: {circulating_display} ANDA\n"
    message += f"🔥 Burned Forever: {burned_display} ANDA\n"
    message += f"📦 Total Minted: {total_display} ANDA\n"

    message += "\n📊 *Data from W-Chain Explorer*"
    await update.message.reply_text(message, parse_mode='Markdown')


async def holders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get OG88 holder and transfer counts."""
    await update.message.reply_text("🔄 Fetching OG88 holders...")

    counters = wchain_api.get_og88_counters()
    if not counters:
        await update.message.reply_text("❌ Unable to fetch holder information. Please try again later.")
        return

    holders_count = int(counters.get('token_holders_count', 0))
    transfers_count = int(counters.get('transfers_count', 0))

    message = "👥 **OG88 Holders**\n\n"
    message += f"Total Holders: {holders_count:,}\n"
    message += f"Transfers Recorded: {transfers_count:,}\n"
    message += "\n📊 *Source: W-Chain Explorer Counters*"

    await update.message.reply_text(message, parse_mode='Markdown')


async def burnwatch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manage OG88 burn alert subscriptions."""
    if not update.effective_chat or not update.message:
        return
    chat_id = update.effective_chat.id
    subscribers = ensure_burn_subscribers(context.application.bot_data)
    burn_state = ensure_burn_state(context.application.bot_data)
    action = (context.args[0].lower() if context.args else "").strip()
    if action in {"off", "stop", "unsubscribe"}:
        if chat_id in subscribers:
            subscribers.remove(chat_id)
            await update.message.reply_text("🛑 Burn alerts disabled for this chat.")
        else:
            await update.message.reply_text("ℹ️ Burn alerts are already disabled here.")
        return
    if action == "status":
        count = len(subscribers)
        status = "subscribed" if chat_id in subscribers else "not subscribed"
        await update.message.reply_text(
            f"📊 Burn alert status: {status}. Total subscribers: {count}."
        )
        return
    if chat_id in subscribers:
        await update.message.reply_text("✅ Burn alerts already enabled for this chat.")
        return
    subscribers.add(chat_id)
    await update.message.reply_text(
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
    if not update.effective_chat or not update.message:
        return

    if not OG88_LIQUIDITY_ADDRESSES:
        await update.message.reply_text(
            "⚠️ Big buy alerts require OG88 liquidity pool addresses. "
            "Please set OG88_LIQUIDITY_ADDRESSES in your environment."
        )
        return

    chat_id = update.effective_chat.id
    subscribers = ensure_big_buy_subscribers(context.application.bot_data)
    buy_state = ensure_big_buy_state(context.application.bot_data)
    action = (context.args[0].lower() if context.args else "").strip()
    threshold_display = format_token_amount(OG88_BIG_BUY_THRESHOLD)

    if action in {"off", "stop", "unsubscribe"}:
        if chat_id in subscribers:
            subscribers.remove(chat_id)
            await update.message.reply_text("🛑 Big buy alerts disabled for this chat.")
        else:
            await update.message.reply_text("ℹ️ Big buy alerts are already disabled here.")
        return

    if action == "status":
        count = len(subscribers)
        status = "subscribed" if chat_id in subscribers else "not subscribed"
        await update.message.reply_text(
            f"📊 Big buy alerts are {status}. Threshold: {threshold_display} ANDA. "
            f"Total subscribers: {count}."
        )
        return

    if action in {"latest", "recent"}:
        events = wchain_api.get_recent_og88_buys(
            min_amount=OG88_BIG_BUY_THRESHOLD,
            limit=3
        )
        if events is None:
            await update.message.reply_text("❌ Unable to fetch recent buys. Please try again later.")
            return
        if not events:
            await update.message.reply_text(
                f"ℹ️ No OG88 buys above {threshold_display} ANDA in the latest blocks."
            )
            return
        message = "🐋 **Latest Big Buys**\n\n"
        message += "\n".join(format_buy_event_summary(event) for event in events)
        await update.message.reply_text(message, parse_mode='Markdown')
        return

    if chat_id in subscribers:
        await update.message.reply_text(
            f"✅ Big buy alerts already enabled for {threshold_display}+ ANDA."
        )
        return

    subscribers.add(chat_id)
    await update.message.reply_text(
        "🐼 Panda scouts activated! You'll be pinged whenever "
        f"{threshold_display}+ ANDA are purchased."
    )

    if buy_state.get("last_hash") is None:
        recent_buys = wchain_api.get_recent_og88_buys(
            min_amount=OG88_BIG_BUY_THRESHOLD,
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
    timestamp = format_timestamp(transaction.get("timestamp"))
    tx_hash = transaction.get("transaction_hash", "")
    tx_url = f"https://scan.w-chain.com/tx/{tx_hash}" if tx_hash else "https://scan.w-chain.com"
    from_address = transaction.get("from", {}).get("hash", "Unknown")
    block_number = transaction.get("block_number", "N/A")
    token_address_display = (
        token.get("hash")
        or token.get("address")
        or OG88_TOKEN_ADDRESS
    )
    message = (
        "🔥🔥🔥 OG88 BURN ALERT 🔥🔥🔥\n"
        "The panda is hungry… and someone just fed the fire. 🔥🐼\n\n"
        f"💣 Burned Amount: {amount_str} OG88\n"
        f"💰 USD Value: {usd_display}\n"
        f"🏷️ Token: {token_address_display}\n\n"
        f"👤 From: {from_address}\n"
        f"⛓️ Block: {block_number}\n"
        f"🕒 Time: {timestamp}\n\n"
        "🔍 Transaction:\n"
        f"👉 [View on W-Scan]({tx_url})\n"
    )
    local_video_path = Path(BURN_ALERT_VIDEO_PATH) if BURN_ALERT_VIDEO_PATH else None
    local_video_available = bool(local_video_path and local_video_path.is_file())
    if BURN_ALERT_VIDEO_PATH and not local_video_available:
        logger.warning("Burn alert video not found at %s", BURN_ALERT_VIDEO_PATH)
    for chat_id in list(subscribers):
        try:
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
            if BURN_ALERT_ANIMATION_URL:
                caption = f"🔥 {amount_str} OG88 burned!"
                await context.bot.send_animation(
                    chat_id=chat_id,
                    animation=BURN_ALERT_ANIMATION_URL,
                    caption=caption
                )
            elif local_video_available and local_video_path:
                caption = f"🔥 {amount_str} OG88 burned!"
                with local_video_path.open("rb") as animation_file:
                    await context.bot.send_animation(
                        chat_id=chat_id,
                        animation=animation_file,
                        caption=caption
                    )
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

    buy_state = ensure_big_buy_state(context.application.bot_data)
    events = wchain_api.get_recent_og88_buys(
        min_amount=OG88_BIG_BUY_THRESHOLD,
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
    if BIG_BUY_ALERT_VIDEO_PATH and not video_available:
        logger.warning("Big buy alert video not found at %s", BIG_BUY_ALERT_VIDEO_PATH)

    for chat_id in list(subscribers):
        try:
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
            if video_available and video_path:
                caption = f"🐼 {amount_str} OG88 buy!"
                with video_path.open("rb") as animation_file:
                    await context.bot.send_animation(
                        chat_id=chat_id,
                        animation=animation_file,
                        caption=caption
                    )
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
    application.add_handler(CommandHandler("burnwatch", burnwatch_command))
    application.add_handler(CommandHandler("buys", buys_command))
    
    # Initialize burn watch data structures
    application.bot_data.setdefault("burn_watch_subscribers", set())
    application.bot_data.setdefault("burn_watch_state", {"last_hash": None})
    application.bot_data.setdefault("big_buy_subscribers", set())
    application.bot_data.setdefault("big_buy_state", {"last_hash": None})
    
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
