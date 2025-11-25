#!/usr/bin/env python3
"""
Setup script for W-Chain Telegram Bot
"""

import os
import sys
import subprocess

def check_python_version():
    """Check if Python version is 3.7 or higher"""
    if sys.version_info < (3, 7):
        print("❌ Error: Python 3.7 or higher is required")
        print(f"Current version: {sys.version}")
        return False
    print(f"✅ Python version: {sys.version.split()[0]}")
    return True

def install_dependencies():
    """Install required dependencies"""
    print("📦 Installing dependencies...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error installing dependencies: {e}")
        return False

def create_env_file():
    """Create .env file if it doesn't exist"""
    if not os.path.exists('.env'):
        print("📝 Creating .env file...")
        with open('.env', 'w') as f:
            f.write("TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here\n")
        print("✅ .env file created")
        print("⚠️  Please edit .env file and add your Telegram bot token")
        return False
    else:
        print("✅ .env file already exists")
        return True

def main():
    """Main setup function"""
    print("🚀 W-Chain Telegram Bot Setup")
    print("=" * 40)
    
    # Check Python version
    if not check_python_version():
        return False
    
    # Install dependencies
    if not install_dependencies():
        return False
    
    # Create .env file
    env_exists = create_env_file()
    
    print("\n" + "=" * 40)
    if env_exists:
        print("✅ Setup complete! You can now run: python bot.py")
    else:
        print("⚠️  Setup almost complete!")
        print("1. Edit .env file and add your Telegram bot token")
        print("2. Get token from @BotFather on Telegram")
        print("3. Run: python bot.py")
    
    return True

if __name__ == "__main__":
    main()

