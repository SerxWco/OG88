# 🚀 W-Chain Bot Deployment Guide

## 24/7 Hosting Options

### Option 1: Heroku (Recommended)

1. **Create Heroku Account:**
   - Go to [heroku.com](https://heroku.com)
   - Sign up for a free account

2. **Install Heroku CLI:**
   - Download from [devcenter.heroku.com](https://devcenter.heroku.com/articles/heroku-cli)
   - Install and restart your terminal

3. **Deploy to Heroku:**
   ```bash
   # Login to Heroku
   heroku login
   
   # Create a new app (replace 'your-bot-name' with your desired name)
   heroku create wchain-bot-yourname
   
   # Initialize git if not already done
   git init
   git add .
   git commit -m "Initial commit"
   
   # Deploy to Heroku
   git push heroku main
   ```

4. **Set Environment Variables:**
   ```bash
   heroku config:set TELEGRAM_BOT_TOKEN=8268666832:AAGPkHQoyG0IUsgm0C31Wj1jHwaoyzcPQEs
   ```

5. **Scale the Bot:**
   ```bash
   heroku ps:scale worker=1
   ```

6. **Check Status:**
   ```bash
   heroku ps
   heroku logs --tail
   ```

### Option 2: Railway

1. Go to [railway.app](https://railway.app)
2. Sign up with GitHub
3. Create new project
4. Connect your repository
5. Set environment variable: `TELEGRAM_BOT_TOKEN=8268666832:AAGPkHQoyG0IUsgm0C31Wj1jHwaoyzcPQEs`
6. Deploy automatically

### Option 3: Your Own Server (wco-ocean.com)

1. **Upload files to your server**
2. **Install Python 3.11+ and pip**
3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
4. **Create systemd service:**
   ```bash
   sudo nano /etc/systemd/system/wchain-bot.service
   ```
   ```ini
   [Unit]
   Description=W-Chain Telegram Bot
   After=network.target

   [Service]
   Type=simple
   User=your-username
   WorkingDirectory=/path/to/your/bot
   Environment=TELEGRAM_BOT_TOKEN=8268666832:AAGPkHQoyG0IUsgm0C31Wj1jHwaoyzcPQEs
   ExecStart=/usr/bin/python3 bot.py
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```
5. **Start the service:**
   ```bash
   sudo systemctl enable wchain-bot
   sudo systemctl start wchain-bot
   sudo systemctl status wchain-bot
   ```

## Important Notes

- **Heroku Free Tier:** Limited to 550 hours/month (about 18 hours/day)
- **Railway:** More generous free tier
- **Your Server:** Unlimited but requires maintenance

## Monitoring

- Check bot status regularly
- Monitor logs for errors
- Set up alerts if possible

## Files Created for Deployment

- `Procfile` - Tells Heroku how to run the bot
- `runtime.txt` - Specifies Python version
- `requirements.txt` - Lists dependencies
- `.env` - Contains your bot token (don't commit this to git!)

## Security Note

Never commit your `.env` file to version control. The bot token is already set as an environment variable in the deployment platforms.
