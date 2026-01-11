# Troubleshooting Guide

A customizable version of the TAM Pro Bot
Originally developed for the UT2004 Unreal Fight Club Discord Community


**PUG Pro Discord Bot**
**Developed by:** fallacy
**Any questions? Please message fallacy on Discord.**

---

## Common Issues

### Bot Won't Start

#### Error: ModuleNotFoundError: No module named 'discord'
**Solution:**
```bash
pip install discord.py
```

#### Error: ModuleNotFoundError: No module named 'database'
**Problem:** Missing database.py file
**Solution:** Ensure database.py is in same directory as pug_bot.py

#### Error: discord.errors.LoginFailure
**Problem:** Invalid bot token
**Solution:**
1. Check token in pug_bot.py is correct
2. Regenerate token in Discord Developer Portal
3. Update BOT_TOKEN in code

### Bot Connects But Doesn't Respond

#### Commands Not Working
**Check:**
1. Channel name matches ALLOWED_CHANNEL_NAME exactly
2. Bot has Read Messages and Send Messages permissions
3. Message Content Intent enabled in Developer Portal

**Test:**
```
.register
```
If no response, check console for errors.

#### Wrong Channel Error
**Problem:** Commands only work in specific channel
**Solution:** Use commands in #tampro (or your configured channel)

### Leaderboard Issues

#### Leaderboard Not Updating
**Check console for:**
```
⚠️ No leaderboard data found for guild...
```

**Solution:**
1. Create #leaderboard channel
2. Restart bot (auto-creates leaderboard)
3. Or manually run `.leaderboard` in #leaderboard

#### Can't Use .leaderboard Command
**Error:** "Can only be used in #leaderboard channel"
**Solution:** Create channel named exactly "leaderboard" (lowercase)

### Registration Issues

#### Can't Register
**Error:** "You must use .register before joining!"
**Solution:** Use `.register` command first

#### Already Registered
**Message:** Shows existing stats
**Solution:** This is normal - you're already registered!

### Queue Issues

#### Can't Join Queue
**Error:** "Cannot use ++ when pug is empty"
**Solution:** Use `.j competitive` to start the queue, not `++`

**Error:** "You're already in an active PUG"
**Solution:** Wait for current PUG to finish

**Error:** "Must register first"
**Solution:** Use `.register`

#### Stuck in Queue
**Solution:**
```
.l              (leave queue)
.reset competitive     (admin - reset queue)
```

### Ready Check Issues

#### Missed Ready Check
**Result:** Removed from queue, wait list promoted
**Solution:** Click ✅ faster next time (90 seconds)

#### Ready Check Won't Start
**Problem:** Queue full but no ready check
**Solution:** Admin use `.reset competitive` and refill queue

### Team Selection Issues

#### Picking Doesn't Work
**Error:** "Not your turn to pick"
**Solution:** Wait for your turn (captains alternate)

**Error:** "Player not available"
**Solution:** Pick from remaining unpicked players

#### AutoPick Not Working
**Check:** Is autopick enabled for this mode?
**Solution:** Admin use `.autopick <mode>`

### Voting Issues

#### Vote Won't Pass
**Problem:** Not enough votes (need 50%+1)
**Solution:** More players must vote ✅

#### Can't Vote
**Error:** "You weren't in this PUG"
**Solution:** Only players in that PUG can vote

**Error:** "Already voted"
**Solution:** Votes are final, can't change

### Stats Issues

#### Win % Doesn't Match
**Understanding:** Win % = Wins / (Wins + Losses)
**Note:** Doesn't include total_pugs from imports

#### ELO Didn't Change
**Check:**
1. Was winner declared?
2. Did vote pass?
3. Check console for errors

#### Leaderboard Rank Wrong
**Solution:**
1. Check `.topelo` for current rankings
2. Manually run `.leaderboard` to refresh
3. Restart bot

### Database Issues

#### Database Locked
**Error:** "Database is locked"
**Solution:**
1. Close any DB browser tools
2. Restart bot
3. Check file permissions

#### Database Corrupted
**Solution:**
1. Stop bot
2. Restore from backup (pug_data.db.backup)
3. If no backup, delete and restart (data loss!)

### Permission Issues

#### Admin Commands Not Working
**Problem:** Need admin role in Discord
**Solution:** Server owner must give you admin permissions

#### Bot Can't Send Messages
**Problem:** Missing permissions
**Solution:** Check bot role has Send Messages in channel

## Error Messages Explained

### "You don't have permission"
**Meaning:** Admin-only command
**Fix:** Ask admin or get admin role

### "Could not find PUG"
**Meaning:** Invalid PUG number
**Fix:** Use `.last` to see recent PUGs

### "No active pugs to join"
**Meaning:** No queues with players
**Fix:** Use `.j competitive` to start one

### "Already in this queue"
**Meaning:** You joined already
**Fix:** Use `.l` to leave if needed

### "Queue is full"
**Meaning:** 8/8 players, added to wait list
**Info:** You'll auto-promote when spot opens

## Performance Issues

### Bot Running Slow
**Causes:**
- Large database (1000+ players)
- Many simultaneous PUGs
- Poor network connection

**Solutions:**
- Restart bot periodically
- Clean old data
- Upgrade hosting

### High CPU Usage
**Normal:** During ready checks and team picking
**Abnormal:** Constantly high
**Fix:** Check for infinite loops in console

## Data Issues

### Lost Data After Update
**Prevention:** Always backup pug_data.db before updates
**Recovery:** Restore from backup

### Duplicate Players
**Cause:** Player left and rejoined server
**Fix:** Admin use `.deleteplayer` on duplicate

### Wrong ELO
**Fix:** Admin use `.setelo @player <correct_elo>`

### Wrong Stats
**Fix:** Admin commands:
```
.setpugs @player <count>
.setelo @player <elo>
```

## Console Errors

### "Connection reset by peer"
**Meaning:** Network issue
**Fix:** Bot auto-reconnects, restart if persists

### "429 Too Many Requests"
**Meaning:** Discord rate limit
**Fix:** Bot auto-handles, reduce spam

### "Forbidden"
**Meaning:** Missing permissions
**Fix:** Check bot role permissions

## Prevention Tips

### Avoid Common Issues
1. **Backup regularly:** `cp pug_data.db pug_data.db.backup`
2. **Monitor console:** Watch for errors
3. **Test in dev server:** Before production changes
4. **Document changes:** Keep notes on customizations
5. **Update carefully:** Test updates on backup first

### Best Practices
1. Restart bot weekly
2. Clean old data monthly
3. Export stats regularly
4. Keep backups offsite
5. Monitor disk space

## Getting Help

### Before Asking
1. Check this guide
2. Check console for errors
3. Test with basic commands
4. Note exact error message

### Contact Support
**Message fallacy on Discord with:**
- Exact error message
- What you were trying to do
- Console output (if any)
- Bot version

---

**Still having issues?** Message **fallacy** on Discord!

---

**Developed by:** fallacy
*Bot made for Competitive Gaming Communities to use for Pick Up Games (PUGs)*
