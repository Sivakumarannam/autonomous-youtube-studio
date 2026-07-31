# Slack Incoming Webhook Setup Guide
### Complete Setup for YouTube Automation Project

This guide explains how to create a Slack workspace, create a Slack App, enable Incoming Webhooks, and obtain a Webhook URL for your YouTube automation project.

---

# Prerequisites

- Email address
- Internet connection
- Web browser

---

# Step 1: Create a Slack Workspace

1. Open your browser.

2. Visit:

   https://slack.com/get-started/create

3. Sign in using your email.

4. Verify your email using the code sent by Slack.

5. Enter your workspace name.

Example:

```
YouTube Automation
```

6. Click **Next**.

7. Create your first channel.

Example:

```
#all-youtube-automation
```

8. Finish the setup.

Congratulations! Your Slack workspace is now ready.

---

# Step 2: Open the Slack API Portal

Visit:

https://api.slack.com/apps

This page allows you to create Slack applications.

---

# Step 3: Create a Slack App

Click:

```
Create an App
```

Select:

```
From scratch
```

Fill in the following:

### App Name

```
YouTube Automation Bot
```

### Workspace

Select

```
YouTube Automation
```

Click

```
Create App
```

---

# Step 4: Enable Incoming Webhooks

From the left sidebar click

```
Incoming Webhooks
```

Enable

```
Activate Incoming Webhooks
```

Switch it to

```
ON
```

---

# Step 5: Add a Webhook

Scroll to the bottom.

Click

```
Add New Webhook to Workspace
```

Choose the channel

```
#all-youtube-automation
```

Click

```
Allow
```

---

# Step 6: Copy the Webhook URL

Slack will generate a URL similar to:

```
https://hooks.slack.com/services/TXXXXXXXX/BXXXXXXXX/XXXXXXXXXXXXXXXXXXXXXXXX
```

Copy this URL.

Save it securely.

This URL will be used by your automation workflow to send notifications.

---

# Step 7: Test the Webhook

Example using Python

```python
import requests

WEBHOOK_URL = "PASTE_YOUR_WEBHOOK_URL"

payload = {
    "text": "✅ Slack webhook is working!"
}

requests.post(WEBHOOK_URL, json=payload)
```

If successful, you should receive the following message inside Slack.

```
✅ Slack webhook is working!
```

---

# Example Notification Messages

## Success

```
✅ Video Uploaded Successfully

Title:
Amazing Space Facts

Upload Time:
10:30 AM

Status:
Success
```

---

## Failure

```
❌ Upload Failed

Reason:
YouTube API quota exceeded.
```

---

## Daily Report

```
📊 Daily Upload Report

Videos Uploaded : 6
Shorts Uploaded : 15
Failures : 0

Status : Completed
```

---

# Example Automation Workflow

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
Send Slack Notification
        │
        ▼
Finished
```

---

# Project Structure Example

```
youtube-automation/
│
├── scripts/
├── voice/
├── images/
├── videos/
├── thumbnails/
├── uploads/
├── notifications/
└── logs/
```

---

# Where the Webhook URL Is Used

The Slack Webhook URL is typically stored in an environment variable.

Example:

```
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXXXXXXXXXXX
```

Python example:

```python
import os
import requests

requests.post(
    os.getenv("SLACK_WEBHOOK_URL"),
    json={"text": "Automation completed successfully."}
)
```

---

# Troubleshooting

## Incoming Webhooks option is missing

- Ensure you created a Slack App first.
- Open the app from https://api.slack.com/apps.

---

## Cannot install the app

- Make sure you selected the correct workspace.
- If you're using your own workspace, you should have permission to install it.

---

## Invalid Webhook URL

- Confirm you copied the complete URL.
- Do not modify or truncate the URL.

---

## Messages are not appearing

- Verify the webhook is connected to the correct channel.
- Send a test message using the Python example above.

---

# Checklist

- [ ] Slack workspace created
- [ ] Slack channel created
- [ ] Slack App created
- [ ] Incoming Webhooks enabled
- [ ] Webhook added to workspace
- [ ] Webhook URL copied
- [ ] Test message sent successfully

---

# Recommended Naming

Workspace

```
YouTube Automation
```

Channel

```
#all-youtube-automation
```

Slack App

```
YouTube Automation Bot
```

Environment Variable

```
SLACK_WEBHOOK_URL
```

---

# Completion

Your Slack setup is now complete.

You can use the Webhook URL in Python, n8n, Make, Zapier, GitHub Actions, or any automation platform that supports HTTP POST requests to receive notifications from your YouTube automation workflow.