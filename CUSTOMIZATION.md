# Customization Guide

A customizable version of the TAM Pro Bot
Originally developed for the UT2004 Unreal Fight Club Discord Community


**PUG Pro Discord Bot**
**Developed by:** fallacy
**Any questions? Please message fallacy on Discord.**

---

## Overview

This bot is designed to work with ANY competitive game that uses pickup games (PUGs). Before running the bot, you need to customize it for your specific game and community.

## Required Configuration

### 1. Bot Token

**File:** `pug_bot.py` (lines 25-27)

```python
# Your Discord Bot Token (get from Discord Developer Portal)
# IMPORTANT: Keep this secret! Never share or commit to GitHub
BOT_TOKEN = "your-bot-token-here"
```

**Change to:**
```python
BOT_TOKEN = "MTIzNDU2Nzg5MDEyMzQ1Njc4OQ.GhJkLm.OpQrStUvWxYzAbCdEfGhIjKlMnOpQr"
```

**Get your token:** https://discord.com/developers/applications

---

### 2. Channel Name

**File:** `pug_bot.py` (line 23)

```python
# Channel where PUG commands work (change to your channel name)
ALLOWED_CHANNEL_NAME = "tampro"
```

**Examples:**
```python
ALLOWED_CHANNEL_NAME = "pugs"         # For general communities
ALLOWED_CHANNEL_NAME = "competitive"  # For competitive scenes
ALLOWED_CHANNEL_NAME = "pickups"      # Alternative name
ALLOWED_CHANNEL_NAME = "scrims"       # For scrim communities
```

---

## Optional Configuration

### 3. Map Pool

**File:** `pug_bot.py` (line 59)

**Option A: Hardcode maps in the file**
```python
MAP_POOL = ["Map1", "Map2", "Map3", "Map4"]
```

**Examples for different games:**

**Counter-Strike / Valorant:**
```python
MAP_POOL = ["Dust2", "Mirage", "Inferno", "Nuke", "Vertigo", "Ancient", "Anubis"]
```

**League of Legends / DOTA:**
```python
MAP_POOL = ["Summoner's Rift", "Howling Abyss"]
```

**Apex Legends / Fortnite:**
```python
MAP_POOL = ["World's Edge", "Storm Point", "Broken Moon"]
```

**Call of Duty:**
```python
MAP_POOL = ["Shoot House", "Shipment", "Terminal", "Highrise"]
```

**Rocket League:**
```python
MAP_POOL = ["DFH Stadium", "Mannfield", "Urban Central", "Beckwith Park"]
```

**Custom Game:**
```python
MAP_POOL = ["YourMap1", "YourMap2", "YourMap3"]
```

**Option B: Leave empty and add via Discord**
```python
MAP_POOL = []  # Recommended - add maps dynamically
```

Then in Discord:
```
Admin: .addmap Dust2
Admin: .addmap Mirage
Admin: .showmaps
```

---

## Game Modes Setup

**No configuration needed in code!** Set up game modes via Discord commands after starting the bot.

### Common Game Mode Examples

**FPS Games (5v5):**
```
Admin: .addmode competitive 10
Admin: .addmode casual 8
Admin: .autopick competitive
```

**MOBA Games:**
```
Admin: .addmode ranked 10
Admin: .addmode normal 10
Admin: .autopick ranked
```

**Battle Royale (Teams):**
```
Admin: .addmode duos 4
Admin: .addmode trios 6
Admin: .addmode quads 8
```

**Sports Games:**
```
Admin: .addmode 3v3 6
Admin: .addmode 2v2 4
Admin: .autopick 3v3
```

**Your Custom Game:**
```
Admin: .addmode <name> <total_players>
```

---

## First Time Setup Checklist

### Before Starting Bot

- [ ] Edit `pug_bot.py` and set `BOT_TOKEN`
- [ ] Edit `pug_bot.py` and set `ALLOWED_CHANNEL_NAME`
- [ ] (Optional) Add maps to `MAP_POOL` or leave empty
- [ ] Create Discord channel matching `ALLOWED_CHANNEL_NAME`
- [ ] Create `#leaderboard` channel (recommended)

### After Starting Bot

```
1. Create game modes:
   Admin: .addmode <name> <players>
   Example: .addmode 5v5 10

2. Add mode aliases (optional):
   Admin: .addalias 5v5 comp
   
3. Enable autopick (recommended):
   Admin: .autopick 5v5
   
4. Add maps (if using tiebreakers):
   Admin: .addmap MapName
   
5. Test registration:
   Player: .register
   Admin: .setelo @player 1000
   
6. Test joining:
   Player: .j 5v5
```

---

## Game-Specific Examples

### Counter-Strike / Valorant Setup

```python
# pug_bot.py
ALLOWED_CHANNEL_NAME = "pugs"
MAP_POOL = ["Dust2", "Mirage", "Inferno", "Nuke", "Vertigo"]
```

Discord commands:
```
.addmode comp 10
.addmode casual 8
.autopick comp
.addalias comp competitive
```

---

### League of Legends / DOTA Setup

```python
# pug_bot.py
ALLOWED_CHANNEL_NAME = "inhouse"
MAP_POOL = ["Summoner's Rift"]
```

Discord commands:
```
.addmode ranked 10
.addmode normal 10
.autopick ranked
.addalias ranked 5v5
```

---

### Rocket League Setup

```python
# pug_bot.py
ALLOWED_CHANNEL_NAME = "competitive"
MAP_POOL = ["DFH Stadium", "Mannfield", "Urban Central"]
```

Discord commands:
```
.addmode 3v3 6
.addmode 2v2 4
.addmode 1v1 2
.autopick 3v3
.autopick 2v2
```

---

### Battle Royale Setup

```python
# pug_bot.py
ALLOWED_CHANNEL_NAME = "scrims"
MAP_POOL = ["World's Edge", "Storm Point"]  # If map voting used
```

Discord commands:
```
.addmode duos 4
.addmode trios 6
.addmode quads 8
.autopick duos
```

---

## Advanced Customization

### Starting ELO

**File:** `pug_bot.py` (line 43)

```python
STARTING_ELO = 1000  # Default starting ELO for new players
```

Change based on your community's preference:
```python
STARTING_ELO = 1500  # Higher baseline
STARTING_ELO = 700   # Lower baseline
```

### Ready Check Timeout

**File:** `pug_bot.py` (line 42)

```python
READY_CHECK_TIMEOUT = 60  # Seconds (90 total)
```

### Captain Pick Time

**File:** `pug_bot.py` (line 41)

```python
CAPTAIN_WAIT_TIME = 10  # Seconds between picks
```

---

## Testing Your Configuration

### 1. Start the Bot

```bash
python pug_bot.py
```

Expected output:
```
======================================================================
PUG Pro Discord Bot - Starting...
Developed by: fallacy
For: Competitive Gaming Communities
======================================================================

Bot has connected to Discord!
Bot is ready to manage PUGs!
Database: pug_data.db
```

### 2. Test Commands

```
Player: .register
Bot: ✅ Registration Complete!

Admin: .modes
Bot: 📋 Available Game Modes
     (empty if no modes created yet)

Admin: .addmode test 4
Bot: ✅ Game mode 'test' created with team size 4

Player: .j test
Bot: PlayerName joined test (1/4)
```

### 3. Verify Leaderboard

Create `#leaderboard` channel, then restart bot.

Bot should auto-post leaderboard on startup.

---

## Common Customization Questions

**Q: Can I change the command prefix from `.` to something else?**
A: Yes! Edit line 38 in `pug_bot.py`:
```python
bot = commands.Bot(command_prefix='!', ...)  # Change . to !
```

**Q: Do I need to set up modes in the code?**
A: No! Use Discord commands after starting the bot.

**Q: Can I have multiple game modes?**
A: Yes! Create as many as you want with `.addmode`.

**Q: What if my game doesn't use maps?**
A: Leave `MAP_POOL = []` and don't use tiebreaker commands.

**Q: Can I rename "PUG Pro Bot"?**
A: Yes, but only in Discord (bot nickname). Code name doesn't matter.

**Q: How do I reset everything?**
A: Delete `pug_data.db` and restart bot (creates fresh database).

---

## Need Help?

**Message fallacy on Discord!**

Common issues:
- Bot won't start: Check bot token
- Commands not working: Check channel name
- Modes not showing: Create them with `.addmode`

---

**Developed by:** fallacy
**For:** Competitive Gaming Communities
*Bot made for Competitive Gaming Communities to use for Pick Up Games (PUGs)*
