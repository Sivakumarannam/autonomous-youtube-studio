# Discord Webhook Setup Guide
### Complete Setup for YouTube Automation Project

This guide explains how to create a Discord server, create a channel, create a webhook, and obtain the Webhook URL for your YouTube automation project.

---

# Prerequisites

- Discord account
- Internet connection
- Web browser or Discord Desktop App

---

# Step 1: Create a Discord Account

If you already have an account, skip to Step 2.

1. Visit

   https://discord.com/register

2. Enter

- Email Address
- Username
- Password
- Date of Birth

3. Click

```
Continue
```

4. Verify your email address.

---

# Step 2: Create a Discord Server

After logging in:

Click the **+ (Add a Server)** button on the left sidebar.

Select

```
Create My Own
```

Choose

```
For me and my friends
```

Server Name

Example

```
YouTube Automation
```

(Optional) Upload a server icon.

Click

```
Create
```

Your Discord server is now ready.

---

# Step 3: Create a Channel

If the server already has a **general** channel, you can use it.

Or create a new channel.

Click the **+** next to **Text Channels**.

Channel Name

Example

```
youtube-automation
```

Click

```
Create Channel
```

---

# Step 4: Open Channel Settings

Open your channel.

Example

```
#youtube-automation
```

Click the **gear icon (⚙️)** beside the channel name.

This opens the channel settings.

---

# Step 5: Open Integrations

Inside Channel Settings

Click

```
Integrations
```

---

# Step 6: Create a Webhook

Click

```
Create Webhook
```

or

```
New Webhook
```

Discord creates a webhook automatically.

Example

```
Webhook 1
```

Rename it.

Example

```
YouTube Automation Bot
```

---

# Step 7: Select the Channel

Choose the channel where messages should appear.

Example

```
#youtube-automation
```

---

# Step 8: Copy the Webhook URL

Click

```
Copy Webhook URL
```

The URL will look similar to

```
https://discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz
```

Save this URL securely.

Your automation workflow will use this URL.

---

# Step 9: Test the Webhook

Python Example

```python
import requests

WEBHOOK_URL = "PASTE_YOUR_WEBHOOK_URL"

payload = {
    "content": "✅ Discord webhook is working!"
}

requests.post(WEBHOOK_URL, json=payload)
```

You should receive

```
✅ Discord webhook is working!
```

inside your Discord channel.

---

# Example Notifications

## Upload Successful

```
✅ Video Uploaded Successfully

Title:
Amazing Space Facts

Time:
10:30 AM
```

---

## Upload Failed

```
❌ Upload Failed

Reason:
YouTube API quota exceeded.
```

---

## Daily Report

```
📊 Daily Report

Videos Uploaded : 6

Shorts Uploaded : 12

Failures : 0

Status : Completed
```

---

# Example Workflow

```
Generate Script
        │
        ▼
Generate Voice
        │
        ▼
Generate Images
        │
        ▼
Create Video
        │
        ▼
Generate Thumbnail
        │
        ▼
Upload to YouTube
        │
        ▼
Send Discord Notification
        │
        ▼
Finished
```

---

# Project Structure

```
youtube-automation/
│
├── scripts/
├── voice/
├── images/
├── videos/
├── uploads/
├── notifications/
└── logs/
```

---

# Store the Webhook URL

Example

```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxxxxxxxxxxxxxxxxxxxxxxx
```

Python

```python
import os
import requests

requests.post(
    os.getenv("DISCORD_WEBHOOK_URL"),
    json={"content": "Automation completed successfully."}
)
```

---

# Troubleshooting

## Integrations option is missing

Possible reasons

- You don't have permission to manage the channel.
- You're not the server owner.
- Community/server permissions restrict webhook creation.

---

## Cannot create webhook

Make sure you have

```
Manage Webhooks
```

permission for the channel.

---

## Invalid Webhook URL

Copy the entire URL without modifying it.

---

## Messages are not appearing

- Verify the webhook points to the correct channel.
- Test it using the Python example above.

---

# Checklist

- [ ] Discord account created
- [ ] Discord server created
- [ ] Text channel created
- [ ] Webhook created
- [ ] Webhook URL copied
- [ ] Test message sent successfully

---

# Recommended Naming

Server

```
YouTube Automation
```

Channel

```
#youtube-automation
```

Webhook

```
YouTube Automation Bot
```

Environment Variable

```
DISCORD_WEBHOOK_URL
```

---

# Completion

Your Discord webhook setup is complete.

You can now use the Webhook URL in Python, n8n, Make, Zapier, GitHub Actions, or any automation platform that supports HTTP POST requests to receive notifications from your YouTube automation workflow.