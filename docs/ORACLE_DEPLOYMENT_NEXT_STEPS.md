# Oracle Cloud Deployment Guide (Continue After App Is Ready)

## Current Status

✅ Oracle Cloud account created
✅ Compute instance created (Ubuntu 22.04)
✅ Firewall configured
    - TCP 22 (SSH)
    - TCP 5000 (Application)
✅ SSH access working
✅ Python/Git/PostgreSQL/FFmpeg installed

---

# Step 1 — Update Your Application

Finish all code changes locally or in Replit.

Test everything.

Push the latest code to GitHub.

Example:

git add .
git commit -m "Final deployment version"
git push origin main

---

# Step 2 — Clone Repository on Oracle VM

SSH into Oracle.

Go to your home folder.

cd ~

Clone your repository.

git clone https://github.com/YOUR_USERNAME/quirklore-studio.git

Enter project.

cd quirklore-studio

If already cloned previously:

git pull

---

# Step 3 — Create PostgreSQL Database

Create database user.

sudo -u postgres psql

Inside PostgreSQL:

CREATE USER quirklore WITH PASSWORD 'YOUR_STRONG_PASSWORD';

CREATE DATABASE quirklore_db OWNER quirklore;

GRANT ALL PRIVILEGES ON DATABASE quirklore_db TO quirklore;

\q

---

# Step 4 — Create .env File

Inside project:

nano .env

Example:

DATABASE_URL=postgresql+asyncpg://quirklore:YOUR_STRONG_PASSWORD@localhost/quirklore_db

GROQ_API_KEY=

YOUTUBE_API_KEY=

YOUTUBE_CLIENT_ID=

YOUTUBE_CLIENT_SECRET=

YOUTUBE_REFRESH_TOKEN=

HF_API_TOKEN=

PEXELS_API_KEY=

PIXABAY_API_KEY=

JAMENDO_CLIENT_ID=

SMTP_USER=

SMTP_PASSWORD=

NOTIFY_EMAIL_TO=

SLACK_WEBHOOK_URL=

DISCORD_WEBHOOK_URL=

TELEGRAM_BOT_TOKEN=

TELEGRAM_CHAT_ID=

INSTAGRAM_ACCESS_TOKEN=

INSTAGRAM_BUSINESS_ACCOUNT_ID=

SESSION_SECRET=

DASHBOARD_AUTH_TOKEN=

Save:

CTRL + O

ENTER

CTRL + X

Protect the file:

chmod 600 .env

---

# Step 5 — Create Python Virtual Environment

Inside project:

python3 -m venv venv

Activate:

source venv/bin/activate

Upgrade pip:

pip install --upgrade pip

Install dependencies:

pip install -r requirements.txt

---

# Step 6 — Run Database Migrations

Activate virtual environment.

source venv/bin/activate

Load environment variables.

export $(grep -v '^#' .env | xargs)

Run Alembic:

alembic upgrade head

If your project requires stamping first:

alembic stamp 720ba5c1665d

Then:

alembic upgrade head

---

# Step 7 — Test Application

source venv/bin/activate

export $(grep -v '^#' .env | xargs)

Run:

uvicorn app.main:app --host 0.0.0.0 --port 5000

Open:

http://YOUR_PUBLIC_IP:5000

Verify:

✔ Login page appears

✔ APIs work

✔ Background jobs start

Press:

CTRL + C

---

# Step 8 — Create systemd Service

sudo nano /etc/systemd/system/quirklore.service

Paste:

[Unit]
Description=Quirklore Studio
After=network.target postgresql.service

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/quirklore-studio
EnvironmentFile=/home/ubuntu/quirklore-studio/.env
ExecStart=/home/ubuntu/quirklore-studio/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 5000
Restart=always

[Install]
WantedBy=multi-user.target

Save.

Reload:

sudo systemctl daemon-reload

Enable:

sudo systemctl enable quirklore

Start:

sudo systemctl start quirklore

Check:

sudo systemctl status quirklore

---

# Step 9 — View Logs

Follow logs:

sudo journalctl -u quirklore -f

Exit:

CTRL + C

---

# Step 10 — Useful Commands

Restart:

sudo systemctl restart quirklore

Stop:

sudo systemctl stop quirklore

Status:

sudo systemctl status quirklore

Logs:

sudo journalctl -u quirklore --since "1 hour ago"

Update project:

cd ~/quirklore-studio

git pull

sudo systemctl restart quirklore

---

# Step 11 — Verify

Application:

http://YOUR_PUBLIC_IP:5000

Everything should now be running continuously on Oracle Cloud.

---

# Troubleshooting

### PostgreSQL

Check:

sudo systemctl status postgresql

Restart:

sudo systemctl restart postgresql

---

### Application Logs

sudo journalctl -u quirklore -f

---

### Port Check

ss -tlnp | grep 5000

---

### Python Version

python3 --version

---

### Virtual Environment

source venv/bin/activate

---

### Update Dependencies

pip install -r requirements.txt

---

### Common Errors

Database connection error

→ Verify DATABASE_URL

Missing API keys

→ Verify .env

Import errors

→ Run:

pip install -r requirements.txt

Migration errors

→ Verify Alembic configuration

Permission errors

→ Verify:

chmod 600 .env

Wrong branch

→ Verify:

git branch

git pull


nohup sh -c "while true; do true; done" &