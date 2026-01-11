# PUG Pro Bot - Quick Start Guide

A customizable version of the TAM Pro Bot
Originally developed for the UT2004 Unreal Fight Club Discord Community


**Developed by:** fallacy  
**Any questions? Please message fallacy on Discord.**

---

## 🚀 5-Minute Setup

### Step 1: Download Files (1 min)
Extract `PUGPro-Bot-Complete.tar.gz` to your desired location.

### Step 2: Install Python Dependencies (2 min)
```bash
pip install -r requirements.txt
```

### Step 3: Configure Bot (1 min)
Edit `pug_bot.py`:
```python
ALLOWED_CHANNEL_NAME = 'tampro'  # Your PUG channel name
BOT_TOKEN = 'paste-your-bot-token-here'
```

### Step 4: Create Discord Channels (30 sec)
- Create `#tampro` (or your channel name)
- Create `#leaderboard` (recommended)

### Step 5: Run Bot (30 sec)
```bash
python pug_bot.py
```

---

## ✅ Test It Works

In Discord:
```
You: .register
Bot: 🎮 Registration Complete! Welcome @YourName!

Admin: .setelo @YourName 1000
Bot: ⚡ ELO Update - Player: @YourName, ELO: 1000

You: .j competitive
Bot: YourName joined 4v4 (1/8)
```

**✅ Working!** You're ready to play PUGs!

---

## 📚 Next Steps

1. **Read**: [PLAYER_GUIDE.md](PLAYER_GUIDE.md) - Learn commands
2. **Read**: [ADMIN_GUIDE.md](ADMIN_GUIDE.md) - Setup options
3. **Invite Players**: Have them use `.register`
4. **Start Playing!** 🎮

---

## 🆘 Problems?

**Bot won't start?**
- Check Python version: `python --version` (need 3.8+)
- Install dependencies: `pip install -r requirements.txt`
- Verify bot token is correct

**Commands not working?**
- Check channel name matches exactly
- Verify bot has permissions
- Enable Message Content Intent in Developer Portal

**Need more help?**
- Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- Message **fallacy** on Discord

---

## 📦 Package Contents

```
README.md               - Overview and introduction
INSTALL.md              - Detailed installation guide
PLAYER_GUIDE.md         - Player commands and usage
ADMIN_GUIDE.md          - Admin setup and management
COMMANDS.md             - Complete command reference
ELO_EXPLAINED.md        - ELO system explanation
TROUBLESHOOTING.md      - Common issues and fixes
CHANGELOG.md            - Version history
QUICKSTART.md           - This file
pug_bot.py              - Main bot script
database.py             - Database manager
requirements.txt        - Python dependencies
LICENSE.txt             - MIT License
```

---

**That's it!** Your bot should be running in under 5 minutes.

**Questions?** Message **fallacy** on Discord.

---

**Developed by:** fallacy  
**For:** Competitive Gaming Communities  
*Bot made for Competitive Gaming Communities to use for Pick Up Games (PUGs)*
