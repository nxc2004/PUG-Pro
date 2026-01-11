# Admin Guide

A customizable version of the TAM Pro Bot
Originally developed for the UT2004 Unreal Fight Club Discord Community


**PUG Pro Discord Bot**
**Developed by:** fallacy
**Any questions? Please message fallacy on Discord.**

*Bot made for Competitive Gaming Communities to use for Pick Up Games (PUGs)*

---

## Table of Contents

1. [Initial Setup](#initial-setup)
2. [Player Management](#player-management)
3. [PUG Management](#pug-management)
4. [Game Mode Configuration](#game-mode-configuration)
5. [Queue Management](#queue-management)
6. [Data Management](#data-management)
7. [Bot Configuration](#bot-configuration)
8. [Best Practices](#best-practices)

---

## Initial Setup

### Create Channels

**Required:**
- `#tampro` (or your chosen name) - PUG commands channel

**Recommended:**
- `#leaderboard` - Auto-updating rankings
- `#pug-results` - Match history (optional)

### Set Bot Token

Edit `pug_bot.py`:
```python
BOT_TOKEN = 'your-bot-token-here'
ALLOWED_CHANNEL_NAME = 'tampro'  # Your PUG channel
```

### Start the Bot

```bash
python pug_bot.py
```

Bot auto-creates leaderboard on startup if #leaderboard exists.

### Initial Configuration

```
# Create game modes
.addmode 2v2 2
.addmode 6v6 6

# Enable autopick
.autopick competitive
.autopick 2v2

# Set map cooldown
.setmapcooldown 3
```

---

## Player Management

### Register Players

Players register themselves:
```
Player: .register
```

As admin, set their starting ELO:
```
.setelo @player 1000
```

**ELO Guidelines:**
- 600-800: Beginner
- 800-1000: Novice
- 1000-1200: Competent/Skilled
- 1200-1400: Veteran
- 1400-1600: Expert
- 1600-1800: Elite
- 1800+: Champion

### Modify Player Stats

**Set ELO:**
```
.setelo @player 1200
```

**Set total PUGs:**
```
.setpugs @player 50
```

**Reset player to wins/losses:**
```
.undoplayerpugs @player
```
Sets total_pugs = wins + losses

**Delete player:**
```
.deleteplayer @player
```
Requires confirmation.

### Bulk Operations

**Export all stats:**
```
.exportstats
```
Downloads CSV with all player data.

**Import ELOs from CSV:**
```
.importelos
```
Attach CSV file with format:
```
PlayerName,ELO
ProGamer,1200
SkillMaster,1150
```

**Bulk update PUG counts:**
```
.examplepugcsv        # Generate template
.updateplayerpugs     # Import filled CSV
```

**Undo last bulk update:**
```
.undoupdateplayerpugs
```

### Reset All Players

**Reset all ELOs to 700:**
```
.reseteloall
```

**Reset all wins/losses:**
```
.resetplayerpugs
```
Requires CONFIRM.

---

## PUG Management

### Override Match Results

**Set winner manually:**
```
.setwinner 147 red
```
Calculates ELO, updates stats.

**Undo winner:**
```
.undowinner
```
Undoes most recent PUG.

**Undo specific PUG:**
```
.undowinner 147
```
Reverses ELO, stats, sets winner to NULL.

**Force cancel PUG:**
```
.forcedeadpug 147
```
Marks PUG as killed (no vote required).

**Undo cancelled PUG:**
```
.undodeadpug 147
```
Restores cancelled PUG.

### Team Picking Override

During captain picking, admins can pick for captains:

```
.pickforred @player
.pickforblue @player
```

**Undo picks:**
```
.undopickforred
.undopickforblue
```

---

## Game Mode Configuration

### Create Game Modes

**Add new mode:**
```
.addmode 6v6 6
```
Creates mode with 6 players per team (12 total).

**Remove mode:**
```
.removemode 6v6
```
Requires CONFIRM.

### Mode Aliases

**Add alias:**
```
.addalias competitive tam
.addalias 2v2 twos
```

**Remove alias:**
```
.removealias tam
```

Players can now use:
```
.j tam     # Same as .j competitive
.j twos    # Same as .j 2v2
```

### Team Balancing

**Enable autopick:**
```
.autopick competitive
```
Teams auto-balanced by ELO.

**Disable autopick:**
```
.autopickoff competitive
```
Returns to captain picking.

**How autopick works:**
1. Sorts players by ELO
2. Distributes to minimize ELO difference
3. Posts server info automatically

### Map Cooldown

**Set cooldown period:**
```
.setmapcooldown 3
```
Maps can't repeat for 3 PUGs.

Maps on cooldown shown with ~~strikethrough~~.

---

## Queue Management

### Reset Queues

**Reset specific mode:**
```
.reset competitive
```
Clears queue, cancels ready check, removes all players.

**Reset all queues:**
```
.resetall
```
Clears every queue in every mode.

### Manual Queue Control

**Add player to queue:**
```
.add @player competitive
```

**Remove player from queue:**
```
.remove @player competitive
```

**Use cases:**
- Player disconnected
- Testing queue mechanics
- Fixing stuck queues

---

## Data Management

### Export Data

**Export player stats:**
```
.exportstats
```

Creates CSV:
```
Discord ID,Display Name,ELO,Total PUGs,Wins,Losses,Win Rate
123456789,PlayerName,1200,50,30,20,60.0%
```

### Import Data

**Import ELOs:**
```
.importelos
```
1. Attach CSV file
2. Bot shows preview
3. Type CONFIRM to apply
4. ELOs updated, leaderboard refreshes

**Import PUG counts:**
```
.examplepugcsv              # Generate template
# Edit AddPUGs column
.updateplayerpugs           # Upload edited file
```

### Backup Database

**Manual backup:**
```bash
cp pug_data.db pug_data_backup_$(date +%Y%m%d).db
```

**Automated backup (Linux/Mac):**
```bash
# Add to crontab
0 0 * * * cp /path/to/pug_data.db /backups/pug_data_$(date +%Y%m%d).db
```

**Restore from backup:**
```bash
cp pug_data_backup_20260110.db pug_data.db
```

---

## Bot Configuration

### Enable/Disable Bot

**Disable bot:**
```
.tamprooff
```
Bot stops responding to all commands except .tamproon.

**Enable bot:**
```
.tamproon
```
Bot resumes normal operation.

**Use case:** Maintenance, updates, emergencies.

### Leaderboard Management

**Create/update leaderboard:**
```
.leaderboard
```
Must be used in #leaderboard channel.

**Auto-update:**
Leaderboard updates automatically after:
- `.winner` declarations
- `.setwinner` overrides
- `.setelo` changes
- `.importelos` imports
- `.reseteloall`

**Clear ELO cache:**
```
.cleartopelo
```
Forces recalculation of top 10.

---

## Best Practices

### Player Onboarding

1. Player uses `.register`
2. Admin evaluates skill level
3. Admin sets appropriate starting ELO
4. Explain ELO system to player

**Starting ELO recommendations:**
- New to game: 600-800
- Some experience: 800-1000
- Competent: 1000-1200
- Very skilled: 1200-1400
- Expert/Pro: 1400+

### Match Management

**During matches:**
- Monitor for disputes
- Be ready to `.setwinner` if vote fails
- Use `.forcedeadpug` for server issues

**After matches:**
- Verify winner votes are honest
- Check for unusual ELO swings
- Review match history with `.last`

### Regular Maintenance

**Daily:**
- Check leaderboard is updating
- Monitor console for errors
- Verify queues working correctly

**Weekly:**
- Export stats backup (`.exportstats`)
- Backup database file
- Review top players for sanity check

**Monthly:**
- Clean old data if needed
- Update bot if new version available
- Review and adjust starting ELOs

### Handling Issues

**Player disputes:**
1. Check `.last <pug#>` for facts
2. Use `.undowinner` if needed
3. Reprocess with `.setwinner`

**Queue stuck:**
```
.reset <mode>
```

**Wrong result recorded:**
```
.undowinner <pug#>
.setwinner <pug#> <correct team>
```

**Player ELO incorrect:**
```
.setelo @player <correct_elo>
```

### Anti-Cheat

**Watch for:**
- Players leaving before losses
- Vote manipulation
- Fake results
- Alt accounts

**Solutions:**
- Use `.forcedeadpug` for abandoned matches
- Override suspicious votes with `.setwinner`
- Delete alt accounts (`.deleteplayer`)
- Adjust ELOs manually if needed

---

## Advanced Configuration

### Custom Game Modes

Example: Create competitive 3v3:
```
.addmode 3v3comp 3
.autopick 3v3comp
.addalias 3v3comp 3s
```

### Migration from Old System

1. Export old data to CSV
2. Format as ELO import (Discord ID, ELO)
3. Use `.importelos`
4. Set PUG counts with `.updateplayerpugs`

### Multiple Servers

Each Discord server has:
- Independent database entries
- Separate leaderboards
- Own game modes
- Isolated player stats

Players can have different ELOs per server.

---

## Troubleshooting

### Common Admin Issues

**Commands not working:**
- Verify you have Discord admin role
- Check channel restrictions
- Bot must be online

**Leaderboard not updating:**
- Check #leaderboard channel exists
- Restart bot to auto-create
- Manually run `.leaderboard`

**ELO changes not applying:**
- Check console for errors
- Verify database isn't locked
- Try `.setelo` again

**Vote not passing:**
- Need 50%+1 votes
- Use `.setwinner` to override
- Check if players actually in PUG

### Emergency Procedures

**Bot unresponsive:**
1. Check console for errors
2. Restart bot
3. Check Discord API status

**Database corrupted:**
1. Stop bot
2. Restore from backup
3. Restart bot

**Mass ELO error:**
1. Note affected PUGs
2. `.undowinner` each PUG
3. Reprocess with correct results
4. Or restore from backup

---

## Admin Commands Quick Reference

```
# Player Management
.setelo @p 1200
.setpugs @p 50
.deleteplayer @p
.undoplayerpugs @p

# PUG Management
.setwinner 147 red
.undowinner 147
.forcedeadpug 147
.undodeadpug 147

# Queue Management
.reset competitive
.resetall
.add @p competitive
.remove @p competitive

# Game Modes
.addmode 6v6 6
.removemode 6v6
.addalias competitive tam
.removealias tam
.autopick competitive
.autopickoff competitive
.setmapcooldown 3

# Data Management
.exportstats
.importelos
.updateplayerpugs
.examplepugcsv
.reseteloall
.resetplayerpugs

# Bot Control
.tamproon
.tamprooff
.leaderboard
.cleartopelo

# Team Picking
.pickforred @p
.pickforblue @p
.undopickforred
.undopickforblue
```

---

## FAQ

**Q: How do I change channel name?**
A: Edit ALLOWED_CHANNEL_NAME in pug_bot.py, restart bot.

**Q: Can I have multiple PUG channels?**
A: Currently only one channel per server.

**Q: How do I backup the database?**
A: Copy pug_data.db file to safe location.

**Q: Can I customize ELO formula?**
A: Edit K_FACTOR in process_winner function (default: 32).

**Q: How do I reset everything?**
A: Delete pug_data.db, restart bot (creates fresh DB).

**Q: Can players change their own ELO?**
A: No, only admins can use .setelo.

**Q: What if vote manipulation happens?**
A: Use .setwinner to override incorrect results.

**Q: How often should I backup?**
A: Daily or weekly depending on activity level.

---

**Need more help?** Message **fallacy** on Discord!

---

**Developed by:** fallacy
**For:** Competitive Gaming Communities
*Bot made for Competitive Gaming Communities to use for Pick Up Games (PUGs)*
