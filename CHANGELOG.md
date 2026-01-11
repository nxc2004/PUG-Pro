# Changelog

A customizable version of the TAM Pro Bot
Originally developed for the UT2004 Unreal Fight Club Discord Community


**PUG Pro Discord Bot**
**Developed by:** fallacy

---

## Version 1.0 (January 2026)

### Initial Release

**Core Features:**
- Queue management with ready checks
- Captain picking and autopick team balancing
- ELO rating system with automatic updates
- Complete statistics tracking
- Multiple game mode support
- Voting system for match results
- Real-time leaderboard updates

**Player Commands:**
- `.register` - Player registration
- `.j` / `++` - Queue joining
- `.l` - Queue leaving
- `.winner` - Match result voting
- `.splitwin` - BO3 split results
- `.deadpug` - Cancel match voting
- Stats commands (`.mystats`, `.topelo`, etc.)

**Admin Commands:**
- ELO management (`.setelo`, `.importelos`)
- PUG control (`.setwinner`, `.undowinner`, `.forcedeadpug`)
- Queue management (`.reset`, `.add`, `.remove`)
- Mode management (`.addmode`, `.autopick`)
- Data export/import

**Key Features:**
- Auto-updating leaderboard on bot startup
- 10-minute ready status persistence
- Automatic team balancing by ELO
- CSV import/export for bulk operations
- Win percentage calculation fix
- Split win support for incomplete BO3s
- Map cooldown system
- 4-hour queue inactivity timeout
- Waiting list with auto-promotion

**Bug Fixes:**
- Fixed ready check not restarting after timeout
- Fixed "already in queue" detection
- Fixed double ELO application on admin override
- Fixed leaderboard not updating
- Fixed win % calculation to use wins+losses

---

## Future Improvements

Potential features for future versions:
- Web dashboard
- Advanced statistics and analytics
- Tournament bracket system
- Custom ELO formulas per mode
- Player achievements/badges
- Match replay system
- Discord voice channel integration

---

**Questions or suggestions?** Message **fallacy** on Discord.

---

*Bot made for Competitive Gaming Communities to use for Pick Up Games (PUGs)*
