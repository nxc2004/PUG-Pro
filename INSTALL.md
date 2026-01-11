# Installation Guide

A customizable version of the TAM Pro Bot
Originally developed for the UT2004 Unreal Fight Club Discord Community


**PUG Pro Discord Bot**  
**Developed by:** fallacy  
**Any questions? Please message fallacy on Discord.**

---

## 📋 Prerequisites

Before installing PUG Pro Bot, ensure you have:

### Required
- **Python 3.8 or higher** - [Download Python](https://www.python.org/downloads/)
- **Discord Bot Token** - [Discord Developer Portal](https://discord.com/developers/applications)
- **Discord Server** - Admin permissions required

### Recommended
- **Text Editor** - VSCode, Notepad++, or similar
- **Command Line Access** - Terminal (Mac/Linux) or Command Prompt (Windows)

---

## 🤖 Step 1: Create Discord Bot

### 1.1 Create Application
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **"New Application"**
3. Name it (e.g., "PUG Pro Bot")
4. Click **"Create"**

### 1.2 Create Bot User
1. Navigate to **"Bot"** tab on the left
2. Click **"Add Bot"**
3. Confirm by clicking **"Yes, do it!"**
4. **Copy your bot token** (you'll need this later)
   - Click **"Reset Token"** if needed
   - Click **"Copy"** to copy the token
   - ⚠️ **Keep this secret!** Don't share it publicly

### 1.3 Configure Bot Permissions
Under **"Bot"** tab, enable:
- ✅ **Presence Intent**
- ✅ **Server Members Intent**
- ✅ **Message Content Intent**

Click **"Save Changes"**

### 1.4 Get Invite Link
1. Go to **"OAuth2"** → **"URL Generator"**
2. Under **"Scopes"**, select:
   - ✅ `bot`
   - ✅ `applications.commands`
3. Under **"Bot Permissions"**, select:
   - ✅ Send Messages
   - ✅ Embed Links
   - ✅ Attach Files
   - ✅ Read Message History
   - ✅ Add Reactions
   - ✅ Use External Emojis
   - ✅ Manage Messages (for deleting ready checks)
   - ✅ Read Messages/View Channels
4. Copy the generated URL at the bottom
5. Open the URL in your browser
6. Select your server and authorize

---

## 💾 Step 2: Install Python Dependencies

### 2.1 Download Bot Files
1. Extract the PUGPro-Bot-Release folder to your desired location
2. Example: `C:\Bots\PUGPro\` or `/home/user/bots/tampro/`

### 2.2 Install Required Packages

**Windows:**
```cmd
cd C:\Bots\PUGPro
pip install -r requirements.txt
```

**Mac/Linux:**
```bash
cd /home/user/bots/tampro
pip3 install -r requirements.txt
```

### 2.3 Verify Installation
```bash
python --version     # Should show 3.8 or higher
pip list             # Should show discord.py and other packages
```

---

## ⚙️ Step 3: Configure the Bot

### 3.1 Edit pug_bot.py

Open `pug_bot.py` in a text editor and find these lines near the top:

```python
# Configuration
ALLOWED_CHANNEL_NAME = 'tampro'  # Channel where PUG commands work
BOT_TOKEN = 'your-bot-token-here'  # Your Discord bot token
```

**Change:**
1. **BOT_TOKEN** - Paste your Discord bot token (from Step 1.2)
2. **ALLOWED_CHANNEL_NAME** - Set your PUG channel name (default: 'tampro')

**Example:**
```python
ALLOWED_CHANNEL_NAME = 'pugs'
BOT_TOKEN = 'MTIzNDU2Nzg5MDEyMzQ1Njc4OQ.GhJkLm.OpQrStUvWxYzAbCdEfGhIjKlMnOpQr'
```

### 3.2 Save Changes
- Save `pug_bot.py`
- ⚠️ **Do not share your bot token!**

---

## 🏗️ Step 4: Setup Discord Server

### 4.1 Create Required Channels

Create these text channels in your Discord server:

**Required:**
- `#tampro` (or whatever you set as ALLOWED_CHANNEL_NAME)
  - Where players use PUG commands

**Recommended:**
- `#leaderboard`
  - Bot auto-posts ELO rankings here
  - Updates automatically after each match

### 4.2 Set Channel Permissions (Optional)

For `#tampro`:
- Everyone can: Read, Send Messages, Add Reactions
- Bot needs: All permissions from Step 1.4

For `#leaderboard`:
- Everyone can: Read Messages
- Bot needs: Send Messages, Embed Links
- Consider disabling "Send Messages" for @everyone (read-only)

---

## 🚀 Step 5: Run the Bot

### 5.1 Start the Bot

**Windows:**
```cmd
cd C:\Bots\PUGPro
python pug_bot.py
```

**Mac/Linux:**
```bash
cd /home/user/bots/tampro
python3 pug_bot.py
```

### 5.2 Verify Success

You should see:
```
PUG Pro Discord Bot has connected to Discord!
Bot is ready to manage PUGs!
Database: pug_data.db

🔄 Initializing leaderboards...
⚠️ No #leaderboard channel found in YourServer, skipping auto-init
✅ Leaderboard initialization complete!
```

If you created a `#leaderboard` channel with registered players:
```
🔄 Initializing leaderboards...
📊 Initializing leaderboard for YourServer in #leaderboard...
✅ Leaderboard initialized for YourServer with 0 players
✅ Leaderboard initialization complete!
```

### 5.3 Keep Bot Running

**Option 1: Terminal Window (Development)**
- Leave terminal open
- Bot stops when you close terminal
- Good for testing

**Option 2: Background Process (Production)**

**Linux/Mac (using screen):**
```bash
screen -S tampro
python3 pug_bot.py
# Press Ctrl+A then D to detach
# Use 'screen -r tampro' to reattach
```

**Linux/Mac (using nohup):**
```bash
nohup python3 pug_bot.py &
```

**Windows (using pythonw):**
```cmd
pythonw pug_bot.py
```

**Option 3: Hosting Service**
- Heroku
- AWS
- DigitalOcean
- Replit
- Google Cloud

---

## ✅ Step 6: Test the Bot

### 6.1 Register Your First Player

In `#tampro`:
```
You: .register

Bot: 🎮 Registration Complete!
     Welcome @YourName! You are now registered for PUG tracking.
     
     Discord Username: @yourname
     Display Name: YourName
     Temporary ELO: 1000 (pending admin review)
     
     ⏳ Next Step: An admin will set your starting ELO
```

### 6.2 Set Your ELO (Admin)

As an admin (someone with admin role in Discord):
```
Admin: .setelo @YourName 1000

Bot: ⚡ ELO Update
     Player: @YourName
     Old ELO: 1000
     New ELO: 1000
     Change: 0
```

### 6.3 Check Available Modes
```
You: .modes

Bot: 📋 Available Game Modes
     
     competitive (default) - 4v4 format
     2v2 - 2v2 format
     ...
```

### 6.4 Join a Queue
```
You: .j competitive

Bot: YourName joined 4v4 (1/8)
```

### 6.5 View Stats
```
You: .mystats

Bot: 📊 YourName's Stats
     ELO: 1000 (Skilled)
     Total PUGs: 0
     Record: 0W-0L (0%)
     ...
```

**✅ If all these work, your bot is installed correctly!**

---

## 🎨 Step 7: Customize (Optional)

### 7.1 Create Game Modes

Create custom game modes:
```
Admin: .addmode 6v6 6

Bot: ✅ Game mode '6v6' created with team size 6
```

### 7.2 Add Mode Aliases
```
Admin: .addalias 6v6 sixvssix

Bot: ✅ Alias 'sixvssix' added for mode '6v6'
```

### 7.3 Enable AutoPick
```
Admin: .autopick 4v4

Bot: ✅ AutoPick enabled for 4v4
     Teams will be automatically balanced by ELO
```

---

## 🔧 Advanced Configuration

### Database Location
By default, the bot creates `pug_data.db` in the same directory.

To change location, edit in `database.py`:
```python
def __init__(self, db_path='pug_data.db'):
```

### Auto-Update Interval
Leaderboard updates after every ELO change automatically.

---

## 📊 Monitoring

### Check Bot Status
Look for console output:
```
✅ Player registered: @username
🔄 Ready check started for 4v4
⚡ Winner declared: RED team
🔄 Calling update_leaderboard...
✅ Leaderboard updated
```

### Database File
Monitor `pug_data.db`:
- Should grow as players register
- Backs up automatically
- Can be backed up manually by copying file

---

## 🆘 Troubleshooting

### Bot Won't Start

**Error: `ModuleNotFoundError: No module named 'discord'`**
```bash
pip install discord.py
```

**Error: `discord.errors.LoginFailure`**
- Check your bot token is correct
- Make sure you copied the full token
- Generate a new token if needed

**Error: `ModuleNotFoundError: No module named 'database'`**
- Ensure `database.py` is in the same directory as `pug_bot.py`

### Bot Connects But Doesn't Respond

**Check channel name:**
- Must match `ALLOWED_CHANNEL_NAME` exactly
- Case-sensitive on some systems

**Check bot permissions:**
- Bot needs Read Messages, Send Messages
- Check channel-specific permission overrides

**Check intents:**
- Ensure Message Content Intent is enabled in Developer Portal

### Leaderboard Not Updating

**Check #leaderboard channel exists:**
```
Admin: .leaderboard
```

**Check console for errors:**
Look for:
```
❌ Error in update_leaderboard: ...
```

### Commands Not Working

**Verify bot is online:**
- Check Discord member list
- Bot should show green status

**Check command prefix:**
- All commands start with `.` (period)
- Example: `.register` not `register`

**Check permissions:**
- Some commands are admin-only
- Need admin role in Discord

---

## 🔄 Updating the Bot

### To Update:
1. **Backup your database:**
   ```bash
   cp pug_data.db pug_data.db.backup
   ```

2. **Stop the bot** (Ctrl+C or kill process)

3. **Replace bot files:**
   - Keep your `pug_data.db`
   - Replace `pug_bot.py` and `database.py` with new versions

4. **Restart the bot:**
   ```bash
   python pug_bot.py
   ```

---

## 🔐 Security Best Practices

### Protect Your Bot Token
- ❌ Don't commit to GitHub
- ❌ Don't share publicly
- ❌ Don't hardcode in shared files
- ✅ Use environment variables (advanced)
- ✅ Regenerate if leaked

### Database Backups
```bash
# Daily backup (Linux/Mac)
cp pug_data.db backups/pug_data_$(date +%Y%m%d).db

# Keep last 7 days
find backups/ -name "pug_data_*.db" -mtime +7 -delete
```

### Admin Permissions
- Only trusted users should have Discord admin role
- Review admin command usage regularly
- Monitor `.setelo` and `.setwinner` usage

---

## ✅ Installation Complete!

Your PUG Pro Bot is now installed and running!

### Next Steps:
1. **Read [PLAYER_GUIDE.md](PLAYER_GUIDE.md)** - Learn player commands
2. **Read [ADMIN_GUIDE.md](ADMIN_GUIDE.md)** - Learn admin setup
3. **Invite players** - Have them use `.register`
4. **Set starting ELOs** - Use `.setelo` for new players
5. **Start playing PUGs!** 🎮

### Need Help?
- Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- Message **fallacy** on Discord

---

**Developed by:** fallacy  
**For:** Competitive Gaming Communities  
**Questions?** Message **fallacy** on Discord
