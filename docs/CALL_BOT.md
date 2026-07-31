# WhatsApp CallMeBot Setup Guide
### Complete Setup for YouTube Automation Project

This guide explains how to connect WhatsApp notifications to your YouTube automation workflow using CallMeBot.

---

# Overview

CallMeBot allows your automation system to send WhatsApp messages through an API.

Workflow:

```
YouTube Automation
        |
        ▼
CallMeBot API
        |
        ▼
WhatsApp Notification
```

---

# Prerequisites

- WhatsApp account
- Mobile number with WhatsApp activated
- Internet connection

---

# Step 1: Save the CallMeBot Number

Open WhatsApp.

Save this number as a contact:

```
CallMeBot
+34 644 59 78 48
```

---

# Step 2: Give Permission to CallMeBot

Open a WhatsApp chat with:

```
+34 644 59 78 48
```

Send this exact message:

```
I allow callmebot to send me messages
```

Important:

- Use the exact text.
- Do not add extra spaces or punctuation.

---

# Step 3: Wait for the API Key

CallMeBot will reply with a message containing your API key.

Example:

```
Your API key is:
123456
```

Save this key.

Example:

```
CALLMEBOT_API_KEY=123456
```

---

# Step 4: Test WhatsApp Notification

You can test it using Python.

```python
import requests

PHONE_NUMBER = "YOUR_PHONE_NUMBER"
API_KEY = "YOUR_API_KEY"

message = "✅ YouTube automation WhatsApp notification is working!"

url = (
    "https://api.callmebot.com/whatsapp.php"
    f"?phone={PHONE_NUMBER}"
    f"&text={message}"
    f"&apikey={API_KEY}"
)

response = requests.get(url)

print(response.text)
```

---

# Step 5: Example Notifications

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

## Upload Failed

```
❌ YouTube Upload Failed

Reason:
Rendering error

Action:
Check automation logs
```

---

## Daily Report

```
📊 Daily Automation Report

Videos Uploaded:
5

Shorts Uploaded:
20

Errors:
0

Status:
Completed ✅
```

---

# Step 6: Store Credentials Safely

Use environment variables:

```
CALLMEBOT_PHONE=your_phone_number

CALLMEBOT_API_KEY=your_api_key
```

Do not publish your API key.

---

# YouTube Automation Workflow Example

```
Generate Script
        |
        ▼
Generate Voice
        |
        ▼
Create Video
        |
        ▼
Generate Thumbnail
        |
        ▼
Upload To YouTube
        |
        ▼
Send WhatsApp Notification
        |
        ▼
Finished
```

---

# Troubleshooting

## No API key received

Check:

- You sent the exact permission message.
- You sent it from the WhatsApp number you want to receive notifications on.
- Wait a few minutes and try again.

---

## Messages are not delivered

Check:

- Phone number format is correct.
- API key is correct.
- Your WhatsApp account is active.

---

# Checklist

- [ ] WhatsApp account ready
- [ ] CallMeBot contact saved
- [ ] Permission message sent
- [ ] API key received
- [ ] Test message sent successfully

---

# Recommended Environment Variables

```
CALLMEBOT_PHONE
CALLMEBOT_API_KEY
```

---

# Completion

Your WhatsApp notification system is ready.

You can connect it with Python, n8n, Make, Zapier, or any YouTube automation workflow to receive upload alerts and error notifications.        