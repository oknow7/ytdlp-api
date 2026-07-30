# 90Tools Downloader API
yt-dlp based video download API - Free hosting ready!

## Deploy to Replit (Easiest - Free, No Credit Card)

1. Go to https://replit.com
2. Create account (GitHub/Google)
3. Click + New Repl → Import from GitHub → Paste your repo URL
   OR: + New Repl → Python → Paste all files manually
4. Open shell and run:
   ```
   pip install yt-dlp
   pip install -r requirements.txt
   ```
5. Click "Run" button
6. Copy the URL (e.g., https://your-repl-name.replit.app)

## Deploy to Render (Free - Needs Credit Card)

1. Go to https://render.com
2. Create a New Web Service
3. Connect your GitHub repo
4. Set:
   - Runtime: Python 3
   - Build Command: `pip install -r requirements.txt && pip install yt-dlp`
   - Start Command: `gunicorn main:app`
5. Deploy!

## Deploy to Koyeb (Free - Needs Credit Card)

1. Go to https://koyeb.com
2. Create app → Docker/Python
3. Use this repo

## API Usage

```bash
# Health check
curl https://your-api.com/health

# Get video info
curl "https://your-api.com/api/info?url=https://youtube.com/watch?v=xxx"

# Download (returns file info)
curl "https://your-api.com/api/download?url=https://youtube.com/watch?v=xxx"

# Download audio
curl "https://your-api.com/api/download?url=https://youtube.com/watch?v=xxx&quality=audio"

# Download direct (for Telegram bot)
curl -X POST "https://your-api.com/api/download_direct" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://youtube.com/watch?v=xxx"}'
```

## Test in Browser
Open `https://your-api.com/health` to check if yt-dlp is installed.
