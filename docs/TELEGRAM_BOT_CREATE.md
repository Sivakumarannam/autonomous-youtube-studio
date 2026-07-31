# Telegram Bot Setup Guide
### Complete Setup for YouTube Automation Project

This guide explains how to create a Telegram bot, get the bot token, find your Telegram Chat ID, and connect it to your YouTube automation workflow.

---

# Prerequisites

- Telegram account
- Telegram mobile app or desktop app
- Internet connection

---

# Step 1: Create a Telegram Account

If you already have Telegram, skip this step.

1. Download Telegram:

   https://telegram.org/

2. Register using your phone number.

3. Complete the verification process.

Your Telegram account is now ready.

---

# Step 2: Create a Telegram Bot

Telegram bots are created using the official bot manager:

```
@BotFather
```

---

## Open BotFather

1. Open Telegram.

2. Search for:

```
BotFather
```

3. Open the account with the blue verification badge.

4. Click:

```
Start
```

---

# Step 3: Create Your Bot

Send this command:

```
/newbot
```

BotFather will ask for a bot name.

Example:

```
YouTube Automation Bot
```

---

Next, BotFather asks for a username.

The username must end with:

```
bot
```

Examples:

```
youtube_automation_bot
```

or

```
yt_upload_notify_bot
```

---

After successful creation, BotFather will provide a message containing:

```
Done! Congratulations on your new bot.
```

and a token like:

```
1234567890:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

# Step 4: Save Your Bot Token

Copy the token.

Example:

```
TELEGRAM_BOT_TOKEN=1234567890:AAxxxxxxxxxxxxxxxx
```

Keep this private.

Anyone with this token can control your bot.

---

# Step 5: Start Your Bot

Search for your bot username.

Example:

```
@youtube_automation_bot
```

Open it.

Click:

```
Start
```

or send:

```
/start
```

This allows your bot to send messages to you.

---

# Step 6: Get Your Telegram Chat ID

Telegram needs your Chat ID to know where to send notifications.

Use:

```
@userinfobot
```

---

## Steps

1. Search Telegram for:

```
userinfobot
```

2. Open the bot.

3. Click:

```
Start
```

4. The bot will reply with your information.

Example:

```
Id: 123456789

First Name:
Your Name
```

Your Chat ID is:

```
123456789
```

---

# Step 7: Save Chat ID

Example:

```
TELEGRAM_CHAT_ID=123456789
```

---

# Step 8: Test Telegram Bot

Python Example:

```python
import requests

BOT_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

data = {
    "chat_id": CHAT_ID,
    "text": "✅ Telegram bot is working!"
}

response = requests.post(url, data=data)

print(response.json())
```

You should receive:

```
✅ Telegram bot is working!
```

in Telegram.

---

# Example Notifications

## Video Uploaded

```
✅ YouTube Upload Complete

Title:
Amazing Space Facts

Status:
Published

Time:
10:30 AM
```

---

## Upload Error

```
❌ Upload Failed

Reason:
API quota exceeded

Check automation system.
```

---

## Daily Report

```
📊 Daily Automation Report

Videos:
5

Shorts:
15

Errors:
0

Status:
Completed ✅
```

---

# Example YouTube Automation Workflow

```
Generate Script
        │
        ▼
Generate Voice
        │
        ▼
Create Video
        │
        ▼
Create Thumbnail
        │
        ▼
Upload To YouTube
        │
        ▼
Send Telegram Notification
        │
        ▼
Finished
```

---

# Store Credentials Safely

Use environment variables:

```
TELEGRAM_BOT_TOKEN=your_bot_token_here

TELEGRAM_CHAT_ID=your_chat_id_here
```

Do not put tokens directly inside public code.

---

# Project Structure Example

```
youtube-automation/
│
├── scripts/
├── voice/
├── videos/
├── thumbnails/
├── uploads/
├── notifications/
│   └── telegram.py
└── logs/
```

---

# Troubleshooting

## Bot does not send messages

Check:

- You pressed `/start` on your bot.
- Bot token is correct.
- Chat ID is correct.

---

## Cannot find BotFather

Search exactly:

```
@BotFather
```

Use the official verified account.

---

## Chat ID is incorrect

Open:

```
@userinfobot
```

again and copy the numeric ID.

---

# Checklist

- [ ] Telegram account created
- [ ] BotFather opened
- [ ] Bot created
- [ ] Bot token copied
- [ ] Bot started
- [ ] Chat ID obtained
- [ ] Test message received

---

# Recommended Naming

Bot Name:

```
YouTube Automation Bot
```

Bot Username:

```
youtube_automation_bot
```

Environment Variables:

```
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

---

# Completion

Your Telegram notification system is ready.

You can now connect it with Python, n8n, Make, Zapier, GitHub Actions, or any YouTube automation workflow to receive upload notifications and error alerts.