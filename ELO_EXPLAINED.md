# ELO System Explained

A customizable version of the TAM Pro Bot
Originally developed for the UT2004 Unreal Fight Club Discord Community


**PUG Pro Discord Bot**
**Developed by:** fallacy
**Any questions? Please message fallacy on Discord.**

*Bot made for Competitive Gaming Communities to use for Pick Up Games (PUGs)*

---

# .splitwin Command - ELO Calculation Examples

## How .splitwin Works

When a Best-of-3 match ends 1-1 without a tiebreaker, use `.splitwin` to declare a draw. Both teams receive ELO changes as if the match result was 0.5 (a draw) instead of 1.0 (win) or 0.0 (loss).

## Formula

For a split/draw:
```
Score = 0.5 for both teams

Expected Score (Red) = 1 / (1 + 10^((Blue ELO - Red ELO) / 400))
Expected Score (Blue) = 1 - Expected Score (Red)

ELO Change (Red) = 32 × (0.5 - Expected Score Red)
ELO Change (Blue) = 32 × (0.5 - Expected Score Blue)
```

## Example 1: Evenly Matched Teams (1000 vs 1000 ELO)

**Setup:**
- Red Team Average: 1000 ELO
- Blue Team Average: 1000 ELO
- K-Factor: 32

**Calculation:**
```
Expected Red = 1 / (1 + 10^((1000-1000)/400))
            = 1 / (1 + 10^0)
            = 1 / 2
            = 0.50 (50% chance to win)

Expected Blue = 0.50 (50% chance to win)

Red ELO Change = 32 × (0.5 - 0.5) = 0
Blue ELO Change = 32 × (0.5 - 0.5) = 0
```

**Result:**
- Red Team: 1000 → **1000** (±0)
- Blue Team: 1000 → **1000** (±0)

**Why?** When teams are perfectly matched, a draw results in zero ELO change.

---

## Example 2: Higher ELO Team vs Lower ELO Team (1200 vs 1000)

**Setup:**
- Red Team Average: 1200 ELO (higher)
- Blue Team Average: 1000 ELO (lower)
- K-Factor: 32

**Calculation:**
```
Expected Red = 1 / (1 + 10^((1000-1200)/400))
            = 1 / (1 + 10^(-0.5))
            = 1 / (1 + 0.316)
            = 1 / 1.316
            = 0.76 (76% chance to win)

Expected Blue = 1 - 0.76 = 0.24 (24% chance to win)

Red ELO Change = 32 × (0.5 - 0.76) = 32 × (-0.26) = -8.3
Blue ELO Change = 32 × (0.5 - 0.24) = 32 × (0.26) = +8.3
```

**Result:**
- Red Team: 1200 → **1192** (-8)
- Blue Team: 1000 → **1008** (+8)

**Why?** The higher ELO team was expected to win 76% of the time. A draw (50-50 split) is worse than expected for them, so they lose ELO. The lower ELO team gains ELO because they exceeded expectations by forcing a draw.

---

## Example 3: Moderate ELO Difference (1150 vs 1050)

**Setup:**
- Red Team Average: 1150 ELO
- Blue Team Average: 1050 ELO
- K-Factor: 32

**Calculation:**
```
Expected Red = 1 / (1 + 10^((1050-1150)/400))
            = 1 / (1 + 10^(-0.25))
            = 1 / (1 + 0.562)
            = 1 / 1.562
            = 0.64 (64% chance to win)

Expected Blue = 1 - 0.64 = 0.36 (36% chance to win)

Red ELO Change = 32 × (0.5 - 0.64) = 32 × (-0.14) = -4.5
Blue ELO Change = 32 × (0.5 - 0.36) = 32 × (0.14) = +4.5
```

**Result:**
- Red Team: 1150 → **1145** (-5)
- Blue Team: 1050 → **1055** (+5)

**Why?** Smaller ELO difference = smaller changes. Red team slightly underperformed, Blue team slightly overperformed.

---

## Example 4: Large ELO Difference (1400 vs 800)

**Setup:**
- Red Team Average: 1400 ELO (much higher)
- Blue Team Average: 800 ELO (much lower)
- K-Factor: 32

**Calculation:**
```
Expected Red = 1 / (1 + 10^((800-1400)/400))
            = 1 / (1 + 10^(-1.5))
            = 1 / (1 + 0.0316)
            = 1 / 1.0316
            = 0.97 (97% chance to win)

Expected Blue = 1 - 0.97 = 0.03 (3% chance to win)

Red ELO Change = 32 × (0.5 - 0.97) = 32 × (-0.47) = -15.0
Blue ELO Change = 32 × (0.5 - 0.03) = 32 × (0.47) = +15.0
```

**Result:**
- Red Team: 1400 → **1385** (-15)
- Blue Team: 800 → **815** (+15)

**Why?** The elite team was expected to win 97% of the time. Splitting 1-1 is a massive underperformance for them and a huge overperformance for the weaker team.

---

## Example 5: Real-World Scenario (1180 vs 1120)

**Setup:**
- Red Team Average: 1180 ELO
- Blue Team Average: 1120 ELO
- K-Factor: 32

**Calculation:**
```
Expected Red = 1 / (1 + 10^((1120-1180)/400))
            = 1 / (1 + 10^(-0.15))
            = 1 / (1 + 0.708)
            = 1 / 1.708
            = 0.59 (59% chance to win)

Expected Blue = 1 - 0.59 = 0.41 (41% chance to win)

Red ELO Change = 32 × (0.5 - 0.59) = 32 × (-0.09) = -2.9
Blue ELO Change = 32 × (0.5 - 0.41) = 32 × (0.09) = +2.9
```

**Result:**
- Red Team: 1180 → **1177** (-3)
- Blue Team: 1120 → **1123** (+3)

**Why?** Close match, close ELO. Small changes reflect that both teams performed roughly as expected in a competitive match.

---

## Comparison: Split vs Full Win/Loss

### Scenario: 1200 vs 1000 ELO

| Result | Red (1200) | Blue (1000) | Notes |
|--------|------------|-------------|-------|
| **Red Wins** | +7 | -7 | Red team expected to win |
| **Split (1-1)** | -8 | +8 | Draw is bad for higher team |
| **Blue Wins** | -24 | +24 | Big upset! |

**Key Insight:** A split penalizes the favored team and rewards the underdog, but less severely than a full loss/win would.

---

## When to Use .splitwin

✅ **Use .splitwin when:**
- Match is Best-of-3 format
- Series ends 1-1 (each team won 1 map)
- Cannot complete tiebreaker map due to:
  - Time constraints
  - Server issues
  - Player availability
  - Mutually agreed to end match

❌ **Don't use .splitwin when:**
- Match format is Best-of-1
- One team won 2-0 or 2-1
- Match was never played (use `.deadpug`)
- Only 1 map was played (use `.winner`)

---

## Voting Requirements

- **Votes needed:** 50% + 1 of all players in the PUG
- **Vote duration:** 15 minutes maximum
- **Auto-pass:** Vote passes immediately when majority reached
- **Both teams affected:** Everyone gets ELO change (no wins/losses recorded)

---

## Stats Impact

**What changes:**
- ✅ ELO (as calculated above)
- ✅ Total PUGs (+1 for everyone)

**What doesn't change:**
- ❌ Wins (stays same)
- ❌ Losses (stays same)
- ❌ Win % (stays same)
- ❌ Streaks (stays same)

A split is recorded as a draw - no winner or loser.

---

## Summary Table: ELO Changes by Team Difference

| ELO Difference | Higher Team Change | Lower Team Change |
|----------------|-------------------|-------------------|
| 0 (even) | ±0 | ±0 |
| 50 | -2 | +2 |
| 100 | -5 | +5 |
| 150 | -7 | +7 |
| 200 | -8 | +8 |
| 300 | -12 | +12 |
| 400 | -14 | +14 |
| 600 | -15 | +15 |

**Pattern:** The larger the skill gap, the more the favored team loses (and underdog gains) from a split.
