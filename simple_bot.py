#!/usr/bin/env python3
"""
Simple W-Chain Telegram Bot - Compatible version
"""

import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from wchain_api import WChainAPI
from config import TELEGRAM_BOT_TOKEN

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize W-Chain API
wchain_api = WChainAPI()

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
        return f"${price:.4f}"
    elif price >= 0.01:
        return f"${price:.6f}"
    else:
        return f"${price:.8f}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    welcome_message = """
🎯 **WChain Bot**

Welcome! I provide real-time information about W-Chain and its tokens.

**Available Commands:**
/start - See the welcome message
/info - Get the complete W-Chain update
/wco - Show WCO token price, supply, market cap, and burn stats
/wave - Show WAVE token price and market info

**Coming Soon:**
/wallet - Lookup wallet holdings
/topwhales - See top WCO holders
/farms - Show live WAVE farm stats
/pairs - List top W-Swap liquidity pairs
/network - View network stats
/alerts - Subscribe to notifications

Use /info for the complete update! 📊
    """
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get comprehensive W-Chain information."""
    await update.message.reply_text("🔄 Fetching comprehensive data...")
    
    # Get all data
    wco_price = wchain_api.get_wco_price()
    wave_price = wchain_api.get_wave_price()
    supply_data = wchain_api.get_wco_supply_info()
    market_cap = wchain_api.get_market_cap()
    
    if not any([wco_price, wave_price, supply_data]):
        await update.message.reply_text("❌ Unable to fetch data. Please try again later.")
        return
    
    message = "🎯 **WChain Bot Update**\n\n"
    
    # Price Information
    message += "💰 **Prices**\n"
    if wco_price:
        price = wco_price.get('price', 0)
        message += f"WCO: {format_price(price)}\n"
    
    if wave_price:
        price = wave_price.get('price', 0)
        message += f"WAVE: {format_price(price)}\n"
    
    # Market Cap
    if market_cap:
        message += f"Market Cap: ${format_number(market_cap, 2)}\n"
    
    message += "\n"
    
    # Supply Information
    if supply_data:
        summary = supply_data.get('summary', {})
        message += "📈 **Supply**\n"
        
        initial_supply = float(summary.get('initial_supply_wco', 0))
        circulating_supply = float(summary.get('circulating_supply_wco', 0))
        locked_supply = float(summary.get('locked_supply_wco', 0))
        burned_supply = float(summary.get('burned_supply_wco', 0))
        
        # Calculate total supply (initial - burnt)
        total_supply = initial_supply - burned_supply
        message += f"Total: {total_supply:,.0f} WCO\n"
        
        # Calculate percentages based on total supply
        if total_supply > 0:
            circulating_pct = (circulating_supply / total_supply) * 100
            locked_pct = (locked_supply / total_supply) * 100
            burned_pct = (burned_supply / total_supply) * 100
            
            message += f"Circulating: {circulating_supply:,.0f} ({circulating_pct:.1f}%)\n"
            message += f"Locked: {format_number(locked_supply, 2)} ({locked_pct:.1f}%)\n"
            message += f"Burnt: {format_number(burned_supply, 2)} ({burned_pct:.1f}%)\n"
    
    # Next Features
    message += "\n⚡ **Next Features Coming:**\n"
    message += "/wallet /farms /pairs"
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def wco_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show WCO token information."""
    await update.message.reply_text("🔄 Fetching WCO data...")
    
    wco_price = wchain_api.get_wco_price()
    supply_data = wchain_api.get_wco_supply_info()
    market_cap = wchain_api.get_market_cap()
    
    if not wco_price and not supply_data:
        await update.message.reply_text("❌ Unable to fetch WCO data. Please try again later.")
        return
    
    message = "🪙 **WCO Token Information**\n\n"
    
    # Price and Market Cap
    if wco_price:
        price = wco_price.get('price', 0)
        message += f"**Price:** {format_price(price)}\n"
    
    if market_cap:
        message += f"**Market Cap:** ${format_number(market_cap, 2)}\n"
    
    message += "\n"
    
    # Supply Information
    if supply_data:
        summary = supply_data.get('summary', {})
        initial_supply = float(summary.get('initial_supply_wco', 0))
        circulating_supply = float(summary.get('circulating_supply_wco', 0))
        locked_supply = float(summary.get('locked_supply_wco', 0))
        burned_supply = float(summary.get('burned_supply_wco', 0))
        
        total_supply = initial_supply - burned_supply
        
        message += "**Supply Stats:**\n"
        message += f"• Total: {total_supply:,.0f} WCO\n"
        message += f"• Circulating: {circulating_supply:,.0f} WCO\n"
        message += f"• Locked: {format_number(locked_supply, 2)} WCO\n"
        message += f"• Burnt: {format_number(burned_supply, 2)} WCO\n"
        
        # Calculate percentages
        if total_supply > 0:
            circulating_pct = (circulating_supply / total_supply) * 100
            locked_pct = (locked_supply / total_supply) * 100
            burned_pct = (burned_supply / total_supply) * 100
            
            message += f"\n**Distribution:**\n"
            message += f"• Circulating: {circulating_pct:.1f}%\n"
            message += f"• Locked: {locked_pct:.1f}%\n"
            message += f"• Burnt: {burned_pct:.1f}%\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def wave_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show WAVE token information."""
    await update.message.reply_text("🔄 Fetching WAVE data...")
    
    wave_price = wchain_api.get_wave_price()
    wco_price = wchain_api.get_wco_price()
    
    if not wave_price:
        await update.message.reply_text("❌ Unable to fetch WAVE data. Please try again later.")
        return
    
    message = "🌊 **WAVE Token Information**\n\n"
    
    # Price Information
    if wave_price:
        price = wave_price.get('price', 0)
        message += f"**Price:** {format_price(price)}\n"
    
    # WCO Price for reference
    if wco_price:
        wco_price_val = wco_price.get('price', 0)
        message += f"**WCO Price:** {format_price(wco_price_val)}\n"
    
    message += "\n"
    message += "**Token Info:**\n"
    message += "WAVE is the native reward and incentive token at the heart of W Swap, W Chain's decentralized exchange. Designed to catalyze liquidity, user participation, and sustainable ecosystem growth, WAVE empowers users through liquidity mining, staking rewards, and future governance capabilities.\n"
    message += "\n• Price calculated via WAVE/WCO trading pair"
    
    message += f"\n📊 *Data from W-Chain Oracle API*"
    
    await update.message.reply_text(message, parse_mode='Markdown')

def main():
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not found. Please set it in your environment variables.")
        return
    
    # Create the Application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("info", info_command))
    application.add_handler(CommandHandler("wco", wco_command))
    application.add_handler(CommandHandler("wave", wave_command))
    
    # Start the bot
    print("🤖 W-Chain Bot is starting...")
    print("Press Ctrl+C to stop the bot")
    
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Error running bot: {e}")

if __name__ == '__main__':
    main()

