# Player Guide

A customizable version of the TAM Pro Bot
Originally developed for the UT2004 Unreal Fight Club Discord Community


**PUG Pro Discord Bot**  
**Developed by:** fallacy  
**For:** Competitive Gaming Communities  

*Bot made for Competitive Gaming Communities to use for Pick Up Games (PUGs)*

**Any questions? Please message fallacy on Discord.**

---

## 📋 Table of Contents

1. [Getting Started](#getting-started)
2. [Queue Commands](#queue-commands)
3. [Match Flow](#match-flow)
4. [Statistics Commands](#statistics-commands)
5. [During a Match](#during-a-match)
6. [Understanding ELO](#understanding-elo)
7. [Tips & Best Practices](#tips--best-practices)

---

## 🎮 Getting Started

### Register for PUGs

Before joining games, you must register:

```
.register
```

**Example:**
```
You: .register

Bot: 🎮 Registration Complete!
     Welcome @PlayerName! You are now registered for PUG tracking.
     
     Discord Username: @playername
     Display Name: PlayerName
     Discord ID: 123456789012345678
     Temporary ELO: 1000 (pending admin review)
     
     ⏳ Next Step: An admin will set your starting ELO
```

An admin will set your starting ELO based on your skill level.

---

## 🎯 Queue Commands

### Join a Queue

**Join default 4v4:**
```
.j competitive
```

**Join specific mode:**
```
.j 2v2
.j 6v6
.j assault
```

**Quick join (join all active queues):**
```
++
++ competitive    (join specific mode)
```

**Examples:**
```
Player: .j competitive
Bot: PlayerName joined 4v4 (1/8)

Player: ++
Bot: PlayerName joined: 4v4 (2/8), 2v2 (1/4)
```

### Leave a Queue

**Leave all queues:**
```
.l
```

**Leave specific mode:**
```
.l competitive
.l 2v2
```

**Example:**
```
Player: .l
Bot: PlayerName left: 4v4, 2v2
```

### Check Queue Status

**List all queues:**
```
.list
```

**List specific mode:**
```
.list competitive
.list 2v2
```

**Example:**
```
Player: .list

Bot: 📊 Current Queues

     competitive (4v4) - 6/8 players
     In queue: @Player1, @Player2, @Player3, @Player4, @Player5, @Player6
     Waiting: None
     
     2v2 (2v2) - 2/4 players
     In queue: @PlayerA, @PlayerB
```

### Auto-Leave Timer

Set a timer to automatically leave queue:

```
.expire 20          - Leave in 20 minutes
.expire 30m         - Leave in 30 minutes  
.expire 1h          - Leave in 1 hour
.expire cancel      - Cancel timer
```

**Example:**
```
Player: .expire 15

Bot: ⏰ You will be auto-removed from queues in 15 minutes
     Use .expire cancel to cancel
```

### View Available Modes

```
.modes
```

**Example:**
```
Bot: 📋 Available Game Modes

     competitive (default) - 4v4 format
     2v2 - 2v2 format
     6v6 - 6v6 format
     assault - Assault mode
```

---

## 🎮 Match Flow

### 1. Queue Phase

Join the queue and wait for it to fill:

```
Player: .j competitive
Bot: PlayerName joined 4v4 (1/8)

... other players join ...

Bot: PlayerName joined 4v4 (8/8)
     Queue is full! Starting ready check...
```

### 2. Ready Check

Click ✅ reaction within 90 seconds:

```
Bot: 🎮 competitive (4v4) Ready Check

     Players (8/8):
     ✅ @Player1 @Player2 @Player3 @Player4
     ⏳ @Player5 @Player6 @Player7 @Player8
     
     React with ✅ to ready up!
     Time remaining: 1:25
```

**Important:**
- Must click ✅ within 90 seconds
- If you don't ready, you're removed from queue
- If someone times out, wait list players are promoted

### 3. Team Selection

**Captain Mode:**
```
Bot: 🎖️ Captains Selected!

     🔴 RED Captain: @Player1
     🔵 BLUE Captain: @Player8
     
     @Player1, you pick first! Use .pick @player
```

Captains alternate picking:
```
Captain: .pick @Player3

Bot: @Player3 picked for RED team
     @Player8, your turn to pick!
```

**AutoPick Mode:**
```
Bot: ⚡ Teams Automatically Balanced!

     🔴 RED TEAM (Avg ELO: 1150)
     @Player1 (1200)
     @Player2 (1180)
     @Player3 (1120)
     @Player4 (1100)
     
     🔵 BLUE TEAM (Avg ELO: 1140)
     @Player5 (1190)
     @Player6 (1160)
     @Player7 (1110)
     @Player8 (1090)
     
     Server: game.server.com:7777
     Password: pug147
```

### 4. Play the Match

Join the server and play!

### 5. Report Results

After the match, vote for the winner:

```
.winner red
.winner blue
```

**Example:**
```
Player: .winner red

Bot: 🗳️ Winner Vote Started - PUG #147

     Voting for: 🔴 RED TEAM
     
     Votes: 1/5 needed
     ✅ @Player1
     
     Time remaining: 14:55
```

Vote passes when 50%+1 players vote:

```
Bot: ✅ Vote passed! RED team wins PUG #147 (5/8 votes)

     🏆 PUG #147 Result
     🔴 RED TEAM WINS!
     
     🔴 Red Team (Winners)
     @Player1: 1200 → 1215 (+15) - Veteran
     @Player2: 1180 → 1195 (+15) - Veteran
     ...
     
     🔵 Blue Team (Losers)
     @Player5: 1190 → 1175 (-15) - Veteran
     @Player6: 1160 → 1145 (-15) - Veteran
     ...
```

### 6. Split Win (1-1 BO3)

For Best-of-3 matches ending 1-1:

```
.splitwin
```

Both teams receive small ELO changes based on a draw.

---

## 📊 Statistics Commands

### Your Stats

View your personal statistics:

```
.mystats
```

**Example:**
```
Bot: 📊 PlayerName's Stats

     ELO: 1185 (Veteran)
     Peak ELO: 1220
     
     Total PUGs: 47
     Record: 28W-19L (59.6%)
     
     Current Streak: 3 wins
     Best Streak: 7 wins
     
     Rank: #12 of 150 players
```

### Other Player Stats

```
.stats @PlayerName
```

**Example:**
```
Player: .stats @TopPlayer

Bot: 📊 TopPlayer's Stats

     ELO: 1450 (Expert)
     Peak ELO: 1480
     
     Total PUGs: 125
     Record: 78W-47L (62.4%)
```

### Top Players

**Most active players:**
```
.top10
```

**Top ELO rankings:**
```
.topelo
```

**Examples:**
```
Player: .topelo

Bot: 🏆 Top 10 ELO Rankings

     1. @Champion - 1650 ELO (Elite)
     2. @ProPlayer - 1580 ELO (Elite)
     3. @Veteran1 - 1520 ELO (Expert)
     ...
     10. @GoodPlayer - 1380 ELO (Expert)
```

### Leaderboard

View full server leaderboard (use in #leaderboard):

```
.leaderboard
```

Shows all players ranked by ELO with 3-column layout.

### Match History

**Most recent match:**
```
.last
```

**Your most recent match:**
```
.mylast
```

**Specific match:**
```
.last 147
```

**Examples:**
```
Player: .last

Bot: 📋 PUG #147 Details

     Mode: 4v4
     Status: ✅ Completed
     Winner: 🔴 RED TEAM
     
     🔴 Red Team (Winners)
     @Player1, @Player2, @Player3, @Player4
     
     🔵 Blue Team (Losers)
     @Player5, @Player6, @Player7, @Player8
     
     Played: 2 hours ago
```

---

## ⚔️ During a Match

### Declare Winner

Vote for winning team:

```
.winner red
.winner blue
```

**For specific PUG:**
```
.winner 147 red
```

**Requirements:**
- Need 50% + 1 votes to pass
- 15-minute vote window
- Can only vote if you played in the PUG

### Split Win (Incomplete BO3)

For matches ending 1-1:

```
.splitwin
```

Both teams get ELO for a draw (0.5 score).

### Cancel PUG

Vote to cancel match that wasn't played:

```
.deadpug
```

**Requirements:**
- Need 50% + 1 votes
- No ELO changes
- Match marked as cancelled

---

## 📈 Understanding ELO

### What is ELO?

ELO measures your skill level relative to other players:
- Higher ELO = Higher skill
- Gain ELO by winning
- Lose ELO by losing

### Starting ELO

Admins set your starting ELO based on skill level:
- 600-800: Beginner
- 800-1000: Novice
- 1000-1200: Competent/Skilled
- 1200-1400: Veteran
- 1400-1600: Expert
- 1600-1800: Elite
- 1800+: Champion/Legendary

### How ELO Changes

**Winning:**
- Beat higher ELO team = Gain more ELO
- Beat lower ELO team = Gain less ELO
- Beat equal team = Gain moderate ELO

**Losing:**
- Lose to higher ELO team = Lose less ELO
- Lose to lower ELO team = Lose more ELO
- Lose to equal team = Lose moderate ELO

**Example:**

Your team (1000 ELO) vs Enemy team (1200 ELO):
- If you WIN: +24 ELO (big upset!)
- If you LOSE: -8 ELO (expected)

Your team (1200 ELO) vs Enemy team (1000 ELO):
- If you WIN: +7 ELO (expected)
- If you LOSE: -24 ELO (big upset!)

### Split Win (Draw)

For 1-1 Best-of-3 matches:
- Both teams treated as 0.5 score
- Favored team loses ELO
- Underdog team gains ELO
- Changes smaller than full win/loss

**Example:** 1200 vs 1000 split:
- 1200 team: -8 ELO
- 1000 team: +8 ELO

### Win Percentage

Calculated from actual wins/losses:

```
Win % = Wins / (Wins + Losses) × 100
```

**Not affected by:**
- Total PUGs (may include imported games)
- Dead PUGs
- Split wins

---

## 💡 Tips & Best Practices

### Queue Etiquette

✅ **Do:**
- Ready up quickly when queue fills
- Stay available when in queue
- Communicate if you need to leave
- Vote for winner honestly

❌ **Don't:**
- Join queue if you can't play
- Go AFK in queue
- Leave mid-match
- Fake vote results

### Ready Check

- Click ✅ as soon as you see it
- You have 90 seconds
- Missing ready check removes you from queue
- Wait list players promoted automatically

### Team Selection

**Captain picking:**
- Captains alternate picks
- Use `.pick @player` to select
- Strategy: Balance skill, not just ELO

**AutoPick:**
- Teams balanced automatically
- Server info provided immediately
- Just join and play!

### Reporting Results

- Vote honestly for the actual winner
- Vote promptly after match ends
- Use `.splitwin` for incomplete BO3s
- Use `.deadpug` if match never happened

### Improving Your ELO

1. **Play consistently** - More games = more accurate ELO
2. **Win matches** - Obvious but important!
3. **Beat higher ELO teams** - Bigger ELO gains
4. **Avoid losing to lower ELO teams** - Bigger ELO losses
5. **Team coordination** - Work with your team
6. **Learn from losses** - Analyze mistakes

### Using Stats

```
.mystats     - Track your progress
.topelo      - See who to beat
.mylast      - Review recent performance
```

---

## ❓ Common Questions

**Q: How do I join a game?**  
A: Use `.j competitive` or `++` when queues are active.

**Q: I didn't ready in time, what happens?**  
A: You're removed from queue. Wait list players promoted.

**Q: Can I join multiple queues?**  
A: Yes! Use `++` to join all active queues.

**Q: How is ELO calculated?**  
A: Based on team ELO difference and match outcome. See [ELO_EXPLAINED.md](ELO_EXPLAINED.md).

**Q: What if match ends 1-1 in BO3?**  
A: Use `.splitwin` for a draw result.

**Q: Can I see my match history?**  
A: Yes, use `.mylast` or `.last <pug#>`.

**Q: Why didn't my win % change?**  
A: Win % only includes actual wins/losses, not total PUGs.

**Q: How do I leave a queue?**  
A: Use `.l` to leave all queues.

**Q: What's the difference between .j and ++?**  
A: `.j competitive` joins specific mode, `++` joins all active queues.

**Q: I voted for wrong team, can I change?**  
A: No, votes are final. Vote carefully!

---

## 🆘 Need Help?

**Having issues?**

1. Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
2. Ask server admins
3. Message **fallacy** on Discord

**Common Issues:**

- **"Must register first"** → Use `.register`
- **"Already in queue"** → Use `.l` to leave first
- **"Wrong channel"** → Use commands in #tampro
- **"Already voted"** → Can't change vote

---

## 📝 Quick Command Reference

```
.register       - Register for PUGs
.j competitive         - Join 4v4 queue
++              - Quick join all queues
.l              - Leave all queues
.list           - Show queue status
.mystats        - Your statistics
.topelo         - Top 10 ELO rankings
.winner red     - Vote for red team
.splitwin       - Declare 1-1 split
.deadpug        - Cancel PUG vote
.last           - Recent match details
```

---

**Ready to play?** Join a queue and start competing!

**Questions?** Message **fallacy** on Discord.

---

**Developed by:** fallacy  
**For:** Competitive Gaming Communities  
*Bot made for Competitive Gaming Communities to use for Pick Up Games (PUGs)*
