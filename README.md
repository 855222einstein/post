# PostBot

A Telegram bot for saving and quickly sending post templates — similar to [@PostBot](https://t.me/PostBot).

## Features

- **Create post** — send text, photo, video, or document; add a caption, inline URL buttons, and toggle text position (above/below media)
- **My posts** — browse saved posts; send, edit, or delete them with one tap
- **Profile** — view your user ID, username, and post count
- **`/usersettings`** — configure Log Channel (auto-forward new posts), Force Subscribe, and Cookies
- **Log Channel** — every saved post is automatically forwarded to your configured channel

## Folder structure

```
bot/
├── main.py              # entry point
├── db.py                # SQLite database (aiosqlite)
├── keyboards.py         # all reply & inline keyboards
└── handlers/
    ├── start.py         # /start command
    ├── profile.py       # 👤 Profile
    ├── create_post.py   # 📝 Create post — full post-settings flow
    ├── my_posts.py      # 📋 My posts — list / send / edit / delete
    └── settings.py      # /usersettings command
requirements.txt
render.yaml
```

## Deploy on Render

### 1. Push to GitHub
Push this folder to a new GitHub repository.

### 2. Create a Render Worker
1. Go to [render.com](https://render.com) → **New → Background Worker**
2. Connect your GitHub repo
3. Render will detect `render.yaml` automatically, or set manually:
   - **Runtime:** Python 3
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `python -m bot.main`

### 3. Set the environment variable
In Render → your service → **Environment**:

| Key | Value |
|-----|-------|
| `TELEGRAM_BOT_TOKEN` | your token from [@BotFather](https://t.me/BotFather) |

### 4. Deploy
Click **Deploy**. The bot starts polling and is live.

> **Note:** Render's free tier spins down idle services. Because this is a **Background Worker** (not a Web Service), it stays running continuously — perfect for a polling bot.

## Local development

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=your_token_here
python -m bot.main
```

The SQLite database (`bot/postbot.db`) is created automatically on first run.

## Button format (Add buttons)

```
Button text — https://example.com
Left button — https://a.com | Right button — https://b.com
Channel — @mychannel — green
```

- Each line = one button row  
- `|` separates buttons on the same row  
- Optional color hint at end: `green`, `blue`, `red`  
- `@username` is expanded to `https://t.me/username` automatically
