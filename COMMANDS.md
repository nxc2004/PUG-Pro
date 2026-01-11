# Complete Command Reference

A customizable version of the TAM Pro Bot
Originally developed for the UT2004 Unreal Fight Club Discord Community


**PUG Pro Discord Bot**
**Developed by:** fallacy
**Any questions? Please message fallacy on Discord.**

---

## Player Commands

### Registration & Profile
```
.register                    - Register for PUG tracking
.mystats                     - View your statistics
.stats @player               - View another player's stats
```

### Queue Management
```
.j competitive                      - Join default 4v4 mode
.j <mode>                    - Join specific mode (2v2, 6v6, etc.)
++                           - Quick join all active queues
++ <mode>                    - Quick join specific mode
.l                           - Leave all queues
.l <mode>                    - Leave specific mode
.list                        - Show all queue statuses
.list <mode>                 - Show specific queue status
.expire <time>               - Auto-leave queue after time (e.g., 20m, 1h)
.expire cancel               - Cancel expire timer
```

### Match Results
```
.winner red                  - Vote for red team victory
.winner blue                 - Vote for blue team victory
.winner <pug#> red           - Vote for specific PUG
.splitwin                    - Declare 1-1 split (incomplete BO3)
.splitwin <pug#>             - Split specific PUG
.deadpug                     - Vote to cancel current PUG
.deadpug <pug#>              - Vote to cancel specific PUG
```

### Statistics & Rankings
```
.top10                       - Top 10 most active players
.topelo                      - Top 10 ELO rankings
.leaderboard                 - Full ELO leaderboard (use in #leaderboard)
.last                        - Most recent PUG details
.mylast                      - Your most recent PUG
.last <pug#>                 - Specific PUG details
```

### Information
```
.modes                       - List all game modes
```

### Team Picking (Captain Mode)
```
.pick @player                - Pick a player for your team (captains only)
```

---

## Admin Commands

### Player Management
```
.setelo @player <elo>        - Set player's ELO
.setpugs @player <count>     - Set player's total PUG count
.deleteplayer @player        - Delete player from database
.undoplayerpugs @player      - Reset player's wins/losses to match total PUGs
```

### PUG Management
```
.setwinner <pug#> red/blue   - Override PUG winner
.undowinner                  - Undo most recent winner declaration
.undowinner <pug#>           - Undo specific PUG winner
.forcedeadpug <pug#>         - Force cancel PUG (admin only)
.undodeadpug <pug#>          - Undo cancelled PUG
```

### Queue Management
```
.reset <mode>                - Reset specific queue
.resetall                    - Reset all queues
.add @player <mode>          - Add player to queue (admin)
.remove @player <mode>       - Remove player from queue (admin)
```

### Game Mode Management
```
.addmode <name> <size>       - Create new game mode
.removemode <name>           - Delete game mode
.addalias <mode> <alias>     - Add alias for mode
.removealias <alias>         - Remove mode alias
.autopick <mode>             - Enable auto team picking for mode
.autopickoff <mode>          - Disable auto team picking
.setmapcooldown <count>      - Set map cooldown period
```

### Data Management
```
.exportstats                 - Export all player data to CSV
.importelos                  - Import ELO updates from CSV
.updateplayerpugs            - Bulk update PUG counts from CSV
.undoupdateplayerpugs        - Undo last bulk PUG update
.examplepugcsv               - Generate template CSV for PUG updates
.reseteloall                 - Reset all player ELOs to 700
.resetplayerpugs             - Reset all wins/losses to 0
```

### Bot Control
```
.tamproon                    - Enable bot
.tamprooff                   - Disable bot
.leaderboard                 - Create/update leaderboard (in #leaderboard)
.cleartopelo                 - Clear top ELO cache
```

### Team Management (Captain Mode)
```
.pickforred @player          - Admin pick for red captain
.pickforblue @player         - Admin pick for blue captain
.undopickforred              - Undo last red team pick
.undopickforblue             - Undo last blue team pick
```

---

## Command Format Examples

### Time Formats
```
.expire 20       → 20 minutes
.expire 30m      → 30 minutes
.expire 1h       → 1 hour
.expire 2h30m    → 2 hours 30 minutes
```

### CSV Import Format
```
PlayerName,ELO
ProGamer,1200
SkillMaster,1150
TopPlayer,1300
```

Or with Discord IDs:
```
123456789012345678,1200
234567890123456789,1150
```

### PUG Count CSV Format
```
PlayerName,AddPUGs,DiscordID
ProGamer,150,'864676891234567890
SkillMaster,200,'906568123456789012
```

---

## Permission Requirements

### No Permissions Required
- .register, .j, ++, .l, .list, .modes
- .mystats, .stats, .top10, .topelo, .last, .mylast
- .winner, .splitwin, .deadpug
- .pick (when you're captain)
- .expire

### Admin Role Required
- .setelo, .setpugs, .deleteplayer
- .setwinner, .undowinner, .forcedeadpug, .undodeadpug
- .reset, .resetall, .add, .remove
- .addmode, .removemode, .addalias, .removealias
- .autopick, .autopickoff, .setmapcooldown
- .exportstats, .importelos, .updateplayerpugs
- .reseteloall, .resetplayerpugs
- .tamproon, .tamprooff
- .pickforred, .pickforblue

### Channel Restrictions
- Most commands: #tampro (or configured PUG channel)
- .leaderboard: #leaderboard channel only

---

## Quick Reference by Task

### Starting a PUG
```
1. .j competitive          (join queue)
2. Wait for 8/8
3. Click ✅ in ready check
4. Pick teams or wait for autopick
5. Join server and play
```

### Reporting Results
```
1. .winner red      (vote for winner)
2. Wait for 50%+1 votes
3. ELO updated automatically
```

### Checking Stats
```
.mystats            (your stats)
.topelo             (top players)
.leaderboard        (full rankings)
```

### Admin Setup
```
1. .addmode 6v6 6   (create mode)
2. .autopick 6v6    (enable autopick)
3. .setelo @new 1000 (set player ELO)
```

---

**Developed by:** fallacy
**For:** Competitive Gaming Communities
*Bot made for Competitive Gaming Communities to use for Pick Up Games (PUGs)*
