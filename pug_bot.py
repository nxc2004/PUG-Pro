#!/usr/bin/env python3
"""
PUG Pro Discord Bot - PUG Management System

A customizable version of the TAM Pro Bot
Originally developed for the UT2004 Unreal Fight Club Discord Community

Developed by: fallacy
For: Competitive Gaming Communities

Bot made for Competitive Gaming Communities to use for Pick Up Games (PUGs)
Any questions? Please message fallacy on Discord.

Version: 1.0
"""

import discord
from discord.ext import commands
import asyncio
import os
from datetime import datetime, timedelta, timezone
import random
from typing import Optional, List, Dict, Tuple
from database import DatabaseManager
from scraper import ut2k4_scraper

# ============================================================================
# CUSTOMIZATION SECTION - Configure these for your game/community
# ============================================================================

# Channel where PUG commands work (change to your channel name)
ALLOWED_CHANNEL_NAME = "tampro"  # Example: "pugs", "pickups", "competitive"

# Your Discord Bot Token (get from Discord Developer Portal)
# IMPORTANT: Keep this secret! Never share or commit to GitHub
BOT_TOKEN = "your-bot-token-here"

# ============================================================================
# END CUSTOMIZATION SECTION
# ============================================================================

# Bot start time
bot_start_time = datetime.now()

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='.', intents=intents, help_command=None)

# Configuration
CAPTAIN_WAIT_TIME = 10
READY_CHECK_TIMEOUT = 60
STARTING_ELO = 1000

# Bot state
bot_enabled = True

# ============================================================================
# Map Pool Configuration
# ============================================================================
# Add your game's maps/levels here for tiebreaker selection
# Leave empty to add maps dynamically with .addmap command
# 
# Examples for different games:
#   FPS:  MAP_POOL = ["Dust2", "Mirage", "Inferno", "Nuke"]
#   MOBA: MAP_POOL = ["Summoner's Rift", "Howling Abyss"]
#   BR:   MAP_POOL = ["Erangel", "Miramar", "Vikendi"]
#   
# Or leave empty and use Discord commands:
#   Admin: .addmap MapName
#   Admin: .removemap MapName
#   Admin: .showmaps

MAP_POOL = []  # Start empty - admins add maps via .addmap command

# Tiebreaker map cooldown tracking
# Store last 3 tiebreaker maps per server to prevent immediate repeats
recent_tiebreakers = {}  # {server_id: [map1, map2, map3]}

# Promote command cooldown tracking (3 minutes per server)
promote_cooldowns = {}  # {server_id: datetime}

# Leaderboard auto-update tracking
leaderboard_auto_update_data = {}  # {server_id: {'channel_id': int, 'message_ids': [int], 'last_update': datetime}}

# PUG count update backup for undo functionality
pug_count_backup = {}  # {server_id: {discord_id: old_total_pugs}}

# Initialize database
db_manager = DatabaseManager('pug_data.db')

# PUG Queue Manager
class PUGQueue:
    def __init__(self, channel, game_mode='default'):
        self.channel = channel
        self.server_id = str(channel.guild.id) if hasattr(channel, 'guild') else None
        self.game_mode_name = game_mode
        mode_data = db_manager.get_game_mode(game_mode)
        if not mode_data:
            mode_data = db_manager.get_game_mode('default')
        self.team_size = mode_data['team_size']
        self.max_per_team = self.team_size // 2
        self.queue = []  # Active queue (max team_size)
        self.waiting_queue = []  # Overflow queue for when main queue is full/in progress
        self.initial_queue = []  # Store original queue order for consistent numbering
        self.red_captain = None
        self.blue_captain = None
        self.red_team = []
        self.blue_team = []
        self.state = 'waiting'  # waiting, ready_check, selecting_captains, picking
        self.captain_timer = None
        self.ready_check_task = None
        self.ready_check_message = None  # Track the ready check message
        self.ready_responses = {}
        self.pick_turn = 'red'
        self.pick_count = {'red': 0, 'blue': 0}
        self.simulation_mode = False
        self.autopick_mode = True  # Autopick enabled by default
        self.dm_notifications = True  # DM notifications enabled by default
        self.last_pug_id = None  # Track last completed PUG ID
        self.expire_timers = {}  # Track expire timers for players {user_id: asyncio.Task}
        self.persistent_ready = {}  # Track ready status with timestamp {user_id: timestamp}
        self.READY_PERSIST_TIME = 600  # Ready status persists for 10 minutes
        self.selected_tiebreaker = None  # Store selected tiebreaker map for cooldown tracking
        self.inactivity_timeout = 4 * 60 * 60  # 4 hours in seconds
        self.queue_start_time = None  # Track when first player joins
        self.inactivity_timer = None  # Track inactivity timeout task
    
    def reset(self):
        """Reset picking phase but keep queue intact - returns to captain selection"""
        # Save the queue
        saved_queue = self.queue.copy()
        saved_initial_queue = self.initial_queue.copy()
        saved_dm_setting = self.dm_notifications
        
        # Reset picking state
        self.red_captain = None
        self.blue_captain = None
        self.red_team = []
        self.blue_team = []
        self.ready_responses = {}
        self.pick_turn = 'red'
        self.pick_count = {'red': 0, 'blue': 0}
        
        # Restore queue and go back to captain selection if queue is full
        self.queue = saved_queue
        self.initial_queue = saved_initial_queue
        self.dm_notifications = saved_dm_setting
        
        if len(self.queue) == self.team_size:
            self.state = 'selecting_captains'
        else:
            self.state = 'waiting'
        
        if self.captain_timer:
            self.captain_timer.cancel()
        if self.ready_check_task:
            self.ready_check_task.cancel()
    
    def hard_reset(self):
        """Completely clear queue and reset everything"""
        self.queue = []
        self.initial_queue = []
        self.red_captain = None
        self.blue_captain = None
        self.red_team = []
        self.blue_team = []
        self.state = 'waiting'
        self.ready_responses = {}
        self.pick_turn = 'red'
        self.pick_count = {'red': 0, 'blue': 0}
        if self.captain_timer:
            self.captain_timer.cancel()
        if self.ready_check_task:
            self.ready_check_task.cancel()
        if self.inactivity_timer:
            self.inactivity_timer.cancel()
            self.inactivity_timer = None
        
        # Reset inactivity tracking
        self.queue_start_time = None
        
        # Move waiting queue players to main queue after reset
        if self.waiting_queue:
            players_to_move = min(len(self.waiting_queue), self.team_size)
            for _ in range(players_to_move):
                if self.waiting_queue:
                    self.queue.append(self.waiting_queue.pop(0))
    
    async def add_player(self, user):
        # Check timeout
        is_timed_out, timeout_end = db_manager.is_timed_out(user.id)
        if is_timed_out:
            return False, f"You are timed out until {timeout_end.strftime('%Y-%m-%d %H:%M:%S')}"
        
        # Check if player is registered
        player_data = db_manager.get_player(user.id, self.server_id)
        if not player_data:
            return False, "You must use `.register` before joining a queue!"
        
        if not player_data.get('registered'):
            return False, "You must use `.register` before joining a queue!"
        
        # Check if already in active queue
        if user.id in self.queue:
            return False, "You are already in this queue!"
        
        # Check if already in waiting queue
        if user.id in self.waiting_queue:
            return False, "You are already in the waiting queue for this mode!"
        
        # If queue is full or game in progress, add to waiting queue
        if len(self.queue) >= self.team_size or self.state != 'waiting':
            self.waiting_queue.append(user.id)
            
            mode_data = db_manager.get_game_mode(self.game_mode_name)
            position = len(self.waiting_queue)
            return True, f"queue_full:{position}"  # Signal to show waiting queue message
        
        # Add to active queue
        self.queue.append(user.id)
        
        # Start inactivity timer if this is the first player
        if len(self.queue) == 1:
            await self.start_inactivity_timer()
        
        await self.check_queue_full()
        return True, None
    
    async def promote_from_waiting_queue(self):
        """Move player from waiting queue to active queue if there's space"""
        # Allow promotion during 'waiting' or 'ready_check' states
        if self.waiting_queue and len(self.queue) < self.team_size and self.state in ['waiting', 'ready_check']:
            promoted_id = self.waiting_queue.pop(0)
            self.queue.append(promoted_id)
            
            mode_data = db_manager.get_game_mode(self.game_mode_name)
            
            # Send promotion message quickly (no await on user fetch)
            member = self.channel.guild.get_member(promoted_id)
            if member:
                name = member.display_name
            else:
                name = f"Player_{promoted_id}"
            
            await self.channel.send(
                f"{name} promoted from waiting list to **{mode_data['name']}** ({len(self.queue)}/{self.team_size})"
            )
            
            # Try to DM in background (don't wait)
            async def send_dm():
                try:
                    user = await bot.fetch_user(promoted_id)
                    await user.send(f"🔄 You've been promoted to the **{mode_data['name']}** PUG queue!")
                except:
                    pass
            
            # Fire and forget DM task
            bot.loop.create_task(send_dm())
            
            # If we're in ready_check state, initialize ready response for new player
            if self.state == 'ready_check':
                self.ready_responses[promoted_id] = False
                # Update the ready check display immediately
                await self.update_ready_check_display()
            
            await self.check_queue_full()
            return True
        return False
    
    async def remove_players_from_other_queues(self, player_ids):
        """Remove players from all other queues in this channel (called when PUG starts)"""
        from collections import defaultdict
        removed_from = defaultdict(list)  # Track which modes each player was removed from
        
        # Get all queues in this channel
        channel_queues = get_channel_queues(self.channel)
        
        for queue_key, queue in channel_queues.items():
            # Skip this queue
            if queue == self:
                continue
            
            # Remove each player from this queue
            for player_id in player_ids:
                if player_id in queue.queue:
                    queue.queue.remove(player_id)
                    queue.cancel_expire_timer(player_id)
                    removed_from[player_id].append(queue.game_mode_name)
                elif player_id in queue.waiting_queue:
                    queue.waiting_queue.remove(player_id)
                    removed_from[player_id].append(queue.game_mode_name)
        
        # Notify players if they were removed from other queues
        if removed_from:
            mode_names = set()
            for modes in removed_from.values():
                mode_names.update(modes)
            
            if mode_names:
                mode_displays = []
                for mode_name in mode_names:
                    mode_data = db_manager.get_game_mode(mode_name)
                    if mode_data:
                        mode_displays.append(mode_data['name'])
                
                if mode_displays:
                    await self.channel.send(
                        f"Players removed from other queues: {', '.join(mode_displays)}"
                    )
    
    async def remove_player(self, user_id):
        removed = False
        was_in_ready_check = self.state == 'ready_check'
        
        # Check active queue
        if user_id in self.queue:
            self.queue.remove(user_id)
            # Cancel expire timer if set
            self.cancel_expire_timer(user_id)
            removed = True
            
            # If in ready check, mark as declined
            if was_in_ready_check and user_id in self.ready_responses:
                self.ready_responses[user_id] = 'declined'
            
            # Try to promote from waiting queue
            promoted = await self.promote_from_waiting_queue()
            
            # If was in ready check and queue is no longer full, cancel ready check
            if was_in_ready_check and len(self.queue) < self.team_size:
                # Cancel ready check task
                if self.ready_check_task:
                    self.ready_check_task.cancel()
                
                # Return to waiting state
                self.state = 'waiting'
                self.ready_responses = {}
                
                mode_data = db_manager.get_game_mode(self.game_mode_name)
                remaining = len(self.queue)
                needed = self.team_size - remaining
                
                await self.channel.send(
                    f"🔄 Ready check cancelled - queue no longer full.\n"
                    f"📊 **{mode_data['name']}** queue status: **{remaining}/{self.team_size}** players ({needed} spot{'s' if needed != 1 else ''} remaining)"
                )
        
        # Check waiting queue
        elif user_id in self.waiting_queue:
            self.waiting_queue.remove(user_id)
            # Cancel expire timer if set
            self.cancel_expire_timer(user_id)
            removed = True
        
        return removed
    
    async def check_queue_full(self):
        if len(self.queue) == self.team_size:
            # Queue is now full
            if self.state == 'waiting':
                # Normal flow: start ready check
                # Send DM notifications if enabled
                if self.dm_notifications:
                    for uid in self.queue:
                        try:
                            user = await bot.fetch_user(uid)
                            mode_data = db_manager.get_game_mode(self.game_mode_name)
                            await user.send(f"🎮 **PUG Queue Full!**\nYour **{mode_data['name']}** pug is starting! Check #{self.channel.name}")
                        except:
                            pass  # Ignore DM failures
                
                self.state = 'ready_check'
                await self.start_ready_check()
            
            elif self.state == 'ready_check':
                # Already in ready check and queue just refilled (promoted from waiting)
                # Check if all players are ready
                all_ready = all(self.ready_responses.get(uid, False) for uid in self.queue)
                
                if all_ready:
                    # Everyone ready, proceed to captains/picking
                    # Cancel ready check
                    if self.ready_check_task:
                        self.ready_check_task.cancel()
                    
                    # Delete ready check message
                    if self.ready_check_message:
                        try:
                            await self.ready_check_message.delete()
                        except:
                            pass
                    
                    # Proceed to next phase
                    await self.start_captain_selection()
    
    async def check_inactivity_timeout(self):
        """Check if queue has been inactive for 4 hours and clear it"""
        import time
        
        if self.queue_start_time is None:
            return
        
        current_time = time.time()
        elapsed = current_time - self.queue_start_time
        
        if elapsed >= self.inactivity_timeout:
            # Queue has been inactive for 4 hours
            mode_data = db_manager.get_game_mode(self.game_mode_name)
            await self.channel.send(
                f"⏱️ **{mode_data['name']}** queue has been inactive for 4 hours and has been cleared due to inactivity."
            )
            
            # Clear the queue
            self.hard_reset()
            self.queue_start_time = None
            
            # Cancel the timer
            if self.inactivity_timer:
                self.inactivity_timer.cancel()
                self.inactivity_timer = None
    
    async def start_inactivity_timer(self):
        """Start a background task to check for inactivity"""
        import time
        
        # Set queue start time if not already set
        if self.queue_start_time is None:
            self.queue_start_time = time.time()
        
        # Cancel existing timer if any
        if self.inactivity_timer:
            self.inactivity_timer.cancel()
        
        # Start new timer
        async def inactivity_check():
            try:
                await asyncio.sleep(self.inactivity_timeout)
                await self.check_inactivity_timeout()
            except asyncio.CancelledError:
                pass
        
        self.inactivity_timer = asyncio.create_task(inactivity_check())
    
    async def start_ready_check(self):
        mode_data = db_manager.get_game_mode(self.game_mode_name)
        
        # Cancel all expire timers when ready check starts
        # Players shouldn't be removed during ready check or active game
        for uid in self.queue:
            self.cancel_expire_timer(uid)
        
        # Initialize ready responses for all players
        # Check persistent ready status first
        import time
        current_time = time.time()
        
        for uid in self.queue:
            # Check if player has persistent ready status (within 2 minutes)
            if uid in self.persistent_ready:
                ready_time = self.persistent_ready[uid]
                if current_time - ready_time < self.READY_PERSIST_TIME:
                    # Still valid, mark as ready
                    self.ready_responses[uid] = True
                else:
                    # Expired, needs to ready again
                    self.ready_responses[uid] = False
                    del self.persistent_ready[uid]
            else:
                self.ready_responses[uid] = False
        
        embed = discord.Embed(
            title="🎮 Ready Check", 
            description=f"**{mode_data['name']}** ({self.max_per_team}v{self.max_per_team}) - Queue is full!\n"
                       f"React with ✅ within {READY_CHECK_TIMEOUT} seconds.",
            color=discord.Color.green()
        )
        
        # Show ready status
        ready_status = self._get_ready_status_text()
        embed.add_field(name="Status", value=ready_status, inline=False)
        
        msg = await self.channel.send(embed=embed)
        
        # Store message BEFORE adding reactions (prevents race condition)
        self.ready_check_message = msg
        
        # Add reactions
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        
        # Small delay to ensure reactions are fully registered
        # This prevents race condition if players click too fast
        await asyncio.sleep(0.5)
        
        self.ready_check_task = asyncio.create_task(self.wait_for_ready_check(msg))
    
    def _get_ready_status_text(self):
        """Generate ready status text for display"""
        ready_count = sum(1 for v in self.ready_responses.values() if v == True)
        total = len(self.queue)
        
        # Build lists of player names
        ready_names = []
        not_ready_names = []
        
        for uid in self.queue:
            response = self.ready_responses.get(uid, False)
            # Get display name from Discord
            try:
                member = self.channel.guild.get_member(uid)
                name = member.display_name if member else f"Player_{uid}"
            except:
                name = f"Player_{uid}"
            
            if response == True:
                ready_names.append(name)
            elif response == 'declined':
                # Skip declined players - they're already removed
                continue
            else:
                not_ready_names.append(name)
        
        # Format as horizontal lists
        status_text = f"**Ready: ✅ ({ready_count}/{total})**\n"
        if ready_names:
            status_text += "Ready: " + ", ".join(ready_names)
        if not_ready_names:
            if ready_names:
                status_text += "\n"
            status_text += "Pending: " + ", ".join(not_ready_names)
        
        return status_text
    
    async def update_ready_check_display(self):
        """Update the ready check message with current status"""
        if hasattr(self, 'ready_check_message') and self.ready_check_message:
            try:
                mode_data = db_manager.get_game_mode(self.game_mode_name)
                
                embed = discord.Embed(
                    title="🎮 Ready Check", 
                    description=f"**{mode_data['name']}** ({self.max_per_team}v{self.max_per_team}) - Queue is full!\n"
                               f"React with ✅ within {READY_CHECK_TIMEOUT} seconds.",
                    color=discord.Color.green()
                )
                
                ready_status = self._get_ready_status_text()
                embed.add_field(name="Status", value=ready_status, inline=False)
                
                await self.ready_check_message.edit(embed=embed)
            except:
                pass  # Message might be deleted
    
    async def wait_for_ready_check(self, msg):
        try:
            # Wait for timeout, but can be cancelled early if everyone is ready
            await asyncio.sleep(READY_CHECK_TIMEOUT)
        except asyncio.CancelledError:
            # Task was cancelled - check why
            # If state is no longer 'ready_check', it was cancelled due to queue no longer being full
            # In that case, don't remove any players
            if self.state != 'ready_check':
                return
            # Otherwise, it was cancelled because everyone is ready - proceed normally
        
        # Only process if still in ready_check state
        if self.state != 'ready_check':
            return
        
        # Check who didn't ready up (only remove those who didn't respond, not those who declined)
        # Players who clicked ❌ are already removed in the reaction handler
        not_ready = []
        for uid in self.queue[:]:
            response = self.ready_responses.get(uid)
            # Only remove if they haven't responded at all (False or None), not 'declined'
            # Players marked as 'declined' were already removed
            if response != True and response != 'declined':
                not_ready.append(uid)
                self.queue.remove(uid)
        
        if not_ready:
            mentions = [f"<@{uid}>" for uid in not_ready]
            await self.channel.send(
                f"❌ {', '.join(mentions)} removed from pug for not readying up in time."
            )
            self.state = 'waiting'
            self.ready_responses = {}
            
            # Try to promote from waiting queue to fill empty spots
            mode_data = db_manager.get_game_mode(self.game_mode_name)
            promoted_count = 0
            
            while len(self.queue) < self.team_size and self.waiting_queue:
                promoted_id = self.waiting_queue.pop(0)
                self.queue.append(promoted_id)
                promoted_count += 1
                
                try:
                    user = await bot.fetch_user(promoted_id)
                    await self.channel.send(
                        f"🔄 <@{promoted_id}> promoted from waiting list to **{mode_data['name']}** queue! ({len(self.queue)}/{self.team_size})"
                    )
                    # Try to DM
                    try:
                        await user.send(f"🔄 You've been promoted to the **{mode_data['name']}** PUG queue!")
                    except:
                        pass
                except:
                    await self.channel.send(
                        f"🔄 A player was promoted from waiting list to **{mode_data['name']}** queue! ({len(self.queue)}/{self.team_size})"
                    )
            
            # Announce queue status after promotions
            remaining = len(self.queue)
            needed = self.team_size - remaining
            
            if promoted_count > 0:
                await self.channel.send(
                    f"📊 **{mode_data['name']}** queue status: **{remaining}/{self.team_size}** players ({needed} spots remaining)"
                )
            else:
                await self.channel.send(
                    f"📊 **{mode_data['name']}** queue status: **{remaining}/{self.team_size}** players ({needed} spots remaining)"
                )
            
            # Check if queue filled back up after promotions
            if len(self.queue) == self.team_size:
                await self.check_queue_full()
        else:
            # Save initial queue order NOW before any picks happen
            self.initial_queue = self.queue.copy()
            
            # Check if this is a 1v1 mode (2 players total)
            if self.team_size == 2:
                await self.channel.send("✅ All players ready! Starting 1v1 match...")
                # Automatically assign players to teams for 1v1
                self.red_team = [self.queue[0]]
                self.blue_team = [self.queue[1]]
                self.red_captain = self.queue[0]
                self.blue_captain = self.queue[1]
                self.state = 'picking'
                
                # Skip picking phase and go straight to finish
                await self.finish_picking()
            else:
                # Check if autopick is enabled
                if self.autopick_mode:
                    # Skip captain selection entirely, go straight to autopick
                    await self.channel.send("All players ready! Auto-balancing teams...")
                    self.state = 'picking'
                    
                    # Validate queue is still in good state before autopicking
                    if len(self.queue) == self.team_size:
                        await self.autopick_teams()
                    else:
                        # Queue changed during ready check, abort
                        await self.channel.send(f"❌ Queue changed during ready check. Current: {len(self.queue)}/{self.team_size}")
                        self.state = 'waiting'
                else:
                    # Manual pick mode - need captain selection
                    await self.channel.send(f"All players ready! Use `.captain` to become a captain! Auto-selecting in {CAPTAIN_WAIT_TIME} seconds...")
                    self.state = 'selecting_captains'
                    await self.start_captain_selection()
    
    async def start_captain_selection(self):
        # Message already sent in wait_for_ready_check
        self.captain_timer = asyncio.create_task(self.auto_select_captains())
    
    async def auto_select_captains(self):
        await asyncio.sleep(CAPTAIN_WAIT_TIME)
        
        if self.state != 'selecting_captains':
            return
        
        # Auto-select captains if not selected
        available = [uid for uid in self.queue if uid not in [self.red_captain, self.blue_captain]]
        
        if not self.red_captain and available:
            self.red_captain = random.choice(available)
            available.remove(self.red_captain)
            member = self.channel.guild.get_member(self.red_captain)
            name = member.display_name if member else f"Player_{self.red_captain}"
            await self.channel.send(f"{name} auto-selected as Red Captain")
        
        if not self.blue_captain and available:
            self.blue_captain = random.choice(available)
            member = self.channel.guild.get_member(self.blue_captain)
            name = member.display_name if member else f"Player_{self.blue_captain}"
            await self.channel.send(f"{name} auto-selected as Blue Captain")
        
        if self.red_captain and self.blue_captain:
            await self.start_picking()
    
    async def volunteer_captain(self, user_id, team=None):
        if user_id not in self.queue:
            return False, "You are not in the pug!"
        
        member = self.channel.guild.get_member(user_id)
        name = member.display_name if member else f"Player_{user_id}"
        
        if team == 'red':
            if self.red_captain:
                return False, "Red captain already selected!"
            self.red_captain = user_id
            await self.channel.send(f"{name} is now the Red Captain")
        elif team == 'blue':
            if self.blue_captain:
                return False, "Blue captain already selected!"
            self.blue_captain = user_id
            await self.channel.send(f"{name} is now the Blue Captain")
        else:
            # Auto-assign to first available
            if not self.red_captain:
                self.red_captain = user_id
                await self.channel.send(f"{name} is now the Red Captain")
            elif not self.blue_captain:
                self.blue_captain = user_id
                await self.channel.send(f"{name} is now the Blue Captain")
            else:
                return False, "Both captains are already selected!"
        
        # Start picking if both captains selected
        if self.red_captain and self.blue_captain:
            if self.captain_timer:
                self.captain_timer.cancel()
            await self.start_picking()
        
        return True, None
    
    async def takeover_captain(self, user_id, team):
        if user_id not in self.queue:
            return False, "You are not in the pug!"
        
        if team == 'red':
            old_captain = self.red_captain
            self.red_captain = user_id
            await self.channel.send(f"🔴 <@{user_id}> took over as Red Captain!")
        elif team == 'blue':
            old_captain = self.blue_captain
            self.blue_captain = user_id
            await self.channel.send(f"🔵 <@{user_id}> took over as Blue Captain!")
        else:
            return False, "Invalid team!"
        
        return True, None
    
    async def start_picking(self):
        self.state = 'picking'
        self.red_team = [self.red_captain]
        self.blue_team = [self.blue_captain]
        self.pick_turn = 'red'
        self.pick_count = {'red': 0, 'blue': 0}
        
        # Save initial queue order for consistent numbering (if not already set)
        if not self.initial_queue:
            self.initial_queue = self.queue.copy()
        
        # Check if autopick is enabled
        if self.autopick_mode:
            await self.autopick_teams()
        else:
            await self.show_teams()
            await self.prompt_pick()
    
    async def autopick_teams(self):
        """Automatically balance teams based on ELO using optimal combinations with variance minimization"""
        try:
            # Validate state before proceeding
            if self.state not in ['picking', 'ready_check']:
                print(f"Warning: autopick_teams called in invalid state: {self.state}")
                return
            
            # Ensure we're in picking state
            self.state = 'picking'
            
            # Get all players and their ELOs (no captains selected yet)
            all_players = list(self.queue)
            
            # Validate we have enough players
            if len(all_players) != self.team_size:
                await self.channel.send(f"❌ Cannot autopick: expected {self.team_size} players, got {len(all_players)}")
                self.state = 'waiting'
                return
            
            # Get all player ELOs
            all_elos = {}
            for uid in all_players:
                player_data = db_manager.get_player(uid, self.server_id)
                if not player_data:
                    await self.channel.send(f"❌ Cannot autopick: player data missing for <@{uid}>")
                    self.state = 'waiting'
                    return
                all_elos[uid] = player_data['elo']
            
            # Calculate how many players per team
            players_per_team = self.max_per_team
            
            # Try to find the most balanced split
            from itertools import combinations
            import random
            
            best_diff = float('inf')
            best_red_picks = None
            best_variance = float('inf')  # For tie-breaking
            best_win_probability_diff = float('inf')  # Additional metric
            
            # Calculate total ELO for optimization
            total_elo = sum(all_elos.values())
            target_per_team = total_elo / 2  # Ideal ELO per team
            
            # Try all possible combinations of players for red team
            for red_picks in combinations(all_players, players_per_team):
                # Calculate red team total
                red_total = sum(all_elos[uid] for uid in red_picks)
                
                # Calculate blue team total (optimization: use total instead of recalculating)
                blue_total = total_elo - red_total
                
                # Find the combination with smallest ELO difference
                diff = abs(red_total - blue_total)
                
                # Calculate average ELOs
                red_avg = red_total / players_per_team
                blue_avg = blue_total / players_per_team
                
                # Calculate win probability (based on ELO system)
                red_win_prob = 1 / (1 + 10 ** ((blue_avg - red_avg) / 400))
                win_prob_diff = abs(red_win_prob - 0.5)  # Distance from 50/50
                
                # Calculate variance (skill distribution within teams)
                red_elos = [all_elos[uid] for uid in red_picks]
                blue_picks = [uid for uid in all_players if uid not in red_picks]
                blue_elos = [all_elos[uid] for uid in blue_picks]
                
                # Variance calculation - how spread out are skills within each team
                red_var = sum((elo - red_avg) ** 2 for elo in red_elos) / players_per_team
                blue_var = sum((elo - blue_avg) ** 2 for elo in blue_elos) / players_per_team
                total_var = red_var + blue_var
                
                # Early termination: if we found perfect balance, use it
                if diff == 0 and win_prob_diff < 0.01:  # Perfect balance
                    best_diff = 0
                    best_red_picks = red_picks
                    best_variance = total_var
                    best_win_probability_diff = win_prob_diff
                    break
                
                # Multi-criteria optimization:
                # 1. Minimize ELO difference (most important)
                # 2. Minimize win probability difference (second priority)
                # 3. Minimize variance (tie-breaker for same ELO diff)
                
                is_better = False
                
                if diff < best_diff:
                    # Significantly better ELO balance
                    is_better = True
                elif diff == best_diff:
                    # Same ELO difference, check win probability
                    if win_prob_diff < best_win_probability_diff:
                        is_better = True
                    elif win_prob_diff == best_win_probability_diff:
                        # Same win probability, check variance
                        if total_var < best_variance:
                            is_better = True
                
                if is_better:
                    best_diff = diff
                    best_red_picks = red_picks
                    best_variance = total_var
                    best_win_probability_diff = win_prob_diff
            
            # Assign the best combination
            if best_red_picks is not None:
                # Assign teams
                self.red_team = list(best_red_picks)
                self.blue_team = [uid for uid in all_players if uid not in best_red_picks]
                
                # Calculate final stats for logging
                red_total = sum(all_elos[uid] for uid in self.red_team)
                blue_total = sum(all_elos[uid] for uid in self.blue_team)
                red_avg = red_total / len(self.red_team)
                blue_avg = blue_total / len(self.blue_team)
                
                # Log balancing results (for debugging)
                print(f"[AUTOPICK] Red: {red_avg:.0f} avg | Blue: {blue_avg:.0f} avg | Diff: {abs(red_avg - blue_avg):.0f}")
                print(f"[AUTOPICK] Red ELOs: {sorted([all_elos[uid] for uid in self.red_team], reverse=True)}")
                print(f"[AUTOPICK] Blue ELOs: {sorted([all_elos[uid] for uid in self.blue_team], reverse=True)}")
                
                # Randomly select captains from each team
                self.red_captain = random.choice(self.red_team)
                self.blue_captain = random.choice(self.blue_team)
                
                # Finish picking (this will show teams)
                await self.finish_picking()
            else:
                await self.channel.send("❌ Error: Could not balance teams. Please try manual picking.")
                self.state = 'selecting_captains'
        except Exception as e:
            await self.channel.send(f"❌ Error in autopick: {str(e)}")
            import traceback
            traceback.print_exc()
            self.state = 'selecting_captains'
    
    def get_available_players(self):
        picked = self.red_team + self.blue_team
        return [uid for uid in self.queue if uid not in picked]
    
    async def pick_player(self, captain_id, player_id, team, admin_override=False):
        # Validate captain (skip for admin override)
        if not admin_override:
            if team == 'red' and captain_id != self.red_captain:
                return False, "You are not the red captain!"
            if team == 'blue' and captain_id != self.blue_captain:
                return False, "You are not the blue captain!"
            
            # Validate it's their turn
            if self.pick_turn != team:
                return False, "It's not your turn to pick!"
        
        # Validate player is available
        available = self.get_available_players()
        if player_id not in available:
            return False, "That player is not available!"
        
        # Add to team
        if team == 'red':
            self.red_team.append(player_id)
            await self.channel.send(f"🔴 RED picks <@{player_id}>!")
        else:
            self.blue_team.append(player_id)
            await self.channel.send(f"🔵 BLUE picks <@{player_id}>!")
        
        # Update pick count
        self.pick_count[team] += 1
        
        # Check if only 1 player left - auto-assign them
        total_players = len(self.red_team) + len(self.blue_team)
        available = self.get_available_players()
        if len(available) == 1 and total_players == self.team_size - 1:
            last_player = available[0]
            # Determine which team needs the player
            if len(self.red_team) < self.max_per_team:
                self.red_team.append(last_player)
                await self.channel.send(f"🔴 RED gets the last player <@{last_player}>!")
            else:
                self.blue_team.append(last_player)
                await self.channel.send(f"🔵 BLUE gets the last player <@{last_player}>!")
            
            total_players += 1
        
        # Check if done
        if total_players == self.team_size:
            await self.finish_picking()
            return True, None
        else:
            await self.advance_pick_turn()
            await self.show_teams()
            await self.prompt_pick()
        
        return True, None
    
    async def advance_pick_turn(self):
        total_picked = sum(self.pick_count.values())
        total_needed = self.team_size - 2  # Minus the 2 captains
        
        # If all picks done, don't change turn
        if len(self.red_team) + len(self.blue_team) == self.team_size:
            return
        
        # Check if we need to auto-assign last player
        if total_picked == total_needed - 1:
            available = self.get_available_players()
            if available:
                self.blue_team.append(available[0])
                await self.channel.send(f"🔵 BLUE gets the last player: <@{available[0]}>!")
            return
        
        # Snake draft pattern: RED → BLUE → BLUE → RED → RED → BLUE → BLUE...
        # Pattern: R, BB, RR, BB, RR, BB...
        
        if total_picked == 0:
            # First pick after captains: RED picks
            self.pick_turn = 'red'
        elif total_picked == 1:
            # After RED's first pick: BLUE picks
            self.pick_turn = 'blue'
        else:
            # For picks 2+, alternate in pairs
            # total_picked: 2=B, 3=R, 4=R, 5=B, 6=B, 7=R, 8=R...
            # Pattern after pick 1: BB RR BB RR...
            picks_after_first = total_picked - 1
            pair_position = picks_after_first % 4
            
            if pair_position in [0, 1]:
                # Positions 0,1 in cycle: BLUE picks
                self.pick_turn = 'blue'
            else:
                # Positions 2,3 in cycle: RED picks
                self.pick_turn = 'red'
    
    async def prompt_pick(self):
        available = self.get_available_players()
        if not available:
            return
        
        captain_id = self.red_captain if self.pick_turn == 'red' else self.blue_captain
        
        # Check if this is a double pick turn
        total_picked = sum(self.pick_count.values())
        is_double_pick = False
        
        # Determine if captain can pick twice (double pick in snake draft)
        if total_picked >= 1:
            picks_after_first = total_picked - 1
            pair_position = picks_after_first % 4
            
            # Check if next pick is also same team
            next_total = total_picked + 1
            if next_total < self.team_size - 2:  # Not the last pick
                next_picks_after = next_total - 1
                next_pair = next_picks_after % 4
                
                if pair_position in [0, 1] and next_pair in [0, 1]:
                    is_double_pick = True
                elif pair_position in [2, 3] and next_pair in [2, 3]:
                    is_double_pick = True
        
        # Show numbered list using INITIAL queue positions
        if self.initial_queue:
            player_list_items = []
            for uid in self.initial_queue:
                if uid in available:
                    position = self.initial_queue.index(uid) + 1
                    player_list_items.append(f"**{position}.** <@{uid}>")
            player_list = "\n".join(player_list_items)
        else:
            player_list = "\n".join([f"**{i+1}.** <@{uid}>" for i, uid in enumerate(available)])
        
        pick_instruction = "`.pick <number>` or `.pick <n>`"
        if is_double_pick:
            pick_instruction += " (you can pick 2: `.pick 3 5`)"
        
        await self.channel.send(
            f"{'🔴' if self.pick_turn == 'red' else '🔵'} <@{captain_id}>, pick a player using {pick_instruction}\n\n{player_list}"
        )

    async def show_teams(self, include_prediction=False):
        mode_data = db_manager.get_game_mode(self.game_mode_name)
        embed = discord.Embed(
            title=f"Current Teams - {mode_data['name']} ({self.max_per_team}v{self.max_per_team})", 
            color=discord.Color.blue()
        )
        
        # Get player names instead of mentions
        red_names = []
        for uid in self.red_team:
            member = self.channel.guild.get_member(uid)
            name = member.display_name if member else f"Player_{uid}"
            if uid == self.red_captain:
                name = f"👑 {name}"
            red_names.append(name)
        
        blue_names = []
        for uid in self.blue_team:
            member = self.channel.guild.get_member(uid)
            name = member.display_name if member else f"Player_{uid}"
            if uid == self.blue_captain:
                name = f"👑 {name}"
            blue_names.append(name)
        
        red_players = ", ".join(red_names) if red_names else "Empty"
        blue_players = ", ".join(blue_names) if blue_names else "Empty"
        
        # Add emojis to team names when teams are complete
        if include_prediction and len(self.red_team) == self.max_per_team and len(self.blue_team) == self.max_per_team:
            red_team_name = f"🔴 Red Team ({len(self.red_team)}/{self.max_per_team})"
            blue_team_name = f"🔵 Blue Team ({len(self.blue_team)}/{self.max_per_team})"
        else:
            red_team_name = f"Red Team ({len(self.red_team)}/{self.max_per_team})"
            blue_team_name = f"Blue Team ({len(self.blue_team)}/{self.max_per_team})"
        
        embed.add_field(name=red_team_name, value=red_players, inline=False)
        embed.add_field(name=blue_team_name, value=blue_players, inline=False)
        
        # Include match prediction if picking is complete
        if include_prediction and len(self.red_team) == self.max_per_team and len(self.blue_team) == self.max_per_team:
            # Calculate team ELO averages
            red_elos = [db_manager.get_player(uid, self.server_id)['elo'] for uid in self.red_team]
            blue_elos = [db_manager.get_player(uid, self.server_id)['elo'] for uid in self.blue_team]
            
            avg_red_elo = sum(red_elos) / len(red_elos)
            avg_blue_elo = sum(blue_elos) / len(blue_elos)
            
            # Calculate win probability
            red_win_prob = 1 / (1 + 10 ** ((avg_blue_elo - avg_red_elo) / 400))
            blue_win_prob = 1 - red_win_prob
            
            # Determine prediction
            if red_win_prob > 0.5:
                prediction = f"Red: {avg_red_elo:.0f} ELO | Blue: {avg_blue_elo:.0f} ELO - Red favored ({red_win_prob*100:.1f}% vs {blue_win_prob*100:.1f}%)"
            elif blue_win_prob > 0.5:
                prediction = f"Red: {avg_red_elo:.0f} ELO | Blue: {avg_blue_elo:.0f} ELO - Blue favored ({blue_win_prob*100:.1f}% vs {red_win_prob*100:.1f}%)"
            else:
                prediction = f"Red: {avg_red_elo:.0f} ELO | Blue: {avg_blue_elo:.0f} ELO - Even match (50% vs 50%)"
            
            embed.add_field(name="Match Prediction", value=prediction, inline=False)
            
            # Add tiebreaker map for 4v4 PUGs
            if self.team_size == 8:  # 4v4
                server_id = str(self.channel.guild.id)
                
                # Initialize cooldown tracking for this server
                if server_id not in recent_tiebreakers:
                    recent_tiebreakers[server_id] = []
                
                # Get maps that are NOT on cooldown
                on_cooldown = recent_tiebreakers[server_id]
                available_maps = [m for m in MAP_POOL if m not in on_cooldown]
                
                # If all maps are on cooldown (shouldn't happen with 14 maps), reset
                if not available_maps:
                    recent_tiebreakers[server_id] = []
                    available_maps = MAP_POOL.copy()
                
                # Select random tiebreaker from available maps
                tiebreaker = random.choice(available_maps)
                
                # Store this tiebreaker (will be added to cooldown in finish_picking)
                self.selected_tiebreaker = tiebreaker
                
                embed.add_field(name="Tiebreaker", value=tiebreaker, inline=False)
        else:
            # Show available players only during picking
            available = self.get_available_players()
            
            # Show numbered list for picking using INITIAL queue order WITH ELO
            if available and self.initial_queue:
                # Number players based on their position in initial_queue
                available_players_list = []
                for uid in self.initial_queue:
                    if uid in available:
                        # Find position in initial queue (1-indexed)
                        position = self.initial_queue.index(uid) + 1
                        # Get player ELO and rank
                        player_data = db_manager.get_player(uid, self.server_id)
                        elo = player_data['elo']
                        rank = get_elo_rank(elo)
                        member = self.channel.guild.get_member(uid)
                        name = member.display_name if member else f"Player_{uid}"
                        available_players_list.append(f"{position}. {name} - {elo:.0f} ELO ({rank})")
                available_players = " | ".join(available_players_list)
            elif available:
                # Fallback if initial_queue not set
                available_players_list = []
                for i, uid in enumerate(available):
                    player_data = db_manager.get_player(uid, self.server_id)
                    elo = player_data['elo']
                    rank = get_elo_rank(elo)
                    member = self.channel.guild.get_member(uid)
                    name = member.display_name if member else f"Player_{uid}"
                    available_players_list.append(f"{i+1}. {name} - {elo:.0f} ELO ({rank})")
                available_players = " | ".join(available_players_list)
            else:
                available_players = "None"
            
            embed.add_field(name="Available Players", value=available_players, inline=False)
        
        await self.channel.send(embed=embed)
    
    async def finish_picking(self):
        try:
            # Show teams with match prediction included
            await self.show_teams(include_prediction=True)
            
            mode_data = db_manager.get_game_mode(self.game_mode_name)
            
            # Calculate team ELO averages for database
            red_elos = [db_manager.get_player(uid, self.server_id)['elo'] for uid in self.red_team]
            blue_elos = [db_manager.get_player(uid, self.server_id)['elo'] for uid in self.blue_team]
            
            avg_red_elo = sum(red_elos) / len(red_elos)
            avg_blue_elo = sum(blue_elos) / len(blue_elos)
            
            # Save PUG data
            pug_number = db_manager.add_pug(
                red_team=self.red_team,
                blue_team=self.blue_team,
                game_mode=self.game_mode_name,
                avg_red_elo=avg_red_elo,
                avg_blue_elo=avg_blue_elo,
                tiebreaker_map=self.selected_tiebreaker if self.team_size == 8 else None
            )
            
            await self.channel.send(f"This is PUG #{pug_number}. Use `.winner red` or `.winner blue` to report the result")
            
            # Add tiebreaker to cooldown list (keep last 3)
            if self.selected_tiebreaker and self.team_size == 8:
                server_id = str(self.channel.guild.id)
                if server_id not in recent_tiebreakers:
                    recent_tiebreakers[server_id] = []
                
                # Add this tiebreaker to the front of the list
                recent_tiebreakers[server_id].insert(0, self.selected_tiebreaker)
                
                # Keep only the last 3 tiebreakers
                recent_tiebreakers[server_id] = recent_tiebreakers[server_id][:3]
            
            # Store the PUG ID for deadpug functionality
            self.last_pug_id = pug_number
            
            # Remove all players in this PUG from other queues in same channel
            all_players = self.red_team + self.blue_team
            await self.remove_players_from_other_queues(all_players)
            
            # Check if there are players in waiting queue before reset
            had_waiting_players = len(self.waiting_queue) > 0
            waiting_count = len(self.waiting_queue)
            
            self.hard_reset()  # Use hard_reset to completely clear queue (moves waiting to main)
            
            # Notify if waiting queue players were promoted
            if had_waiting_players:
                promoted_count = len(self.queue)
                if promoted_count > 0:
                    await self.channel.send(
                        f"🔄 **{promoted_count}** player{'s' if promoted_count != 1 else ''} promoted from waiting list to **{mode_data['name']}** queue!\n"
                        f"Current queue: {promoted_count}/{self.team_size}"
                    )
                    
                    # Check if the queue filled immediately
                    await self.check_queue_full()
        except Exception as e:
            await self.channel.send(f"❌ Error in finish_picking: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def get_queue_list(self):
        return self.queue.copy()
    
    async def set_expire_timer(self, user_id, minutes):
        """Set an expire timer for a player to auto-remove them from queue"""
        # Cancel existing timer if any
        if user_id in self.expire_timers:
            self.expire_timers[user_id].cancel()
        
        # Create new timer
        async def expire_callback():
            await asyncio.sleep(minutes * 60)
            if user_id in self.queue:
                self.queue.remove(user_id)
                mode_data = db_manager.get_game_mode(self.game_mode_name)
                try:
                    user = await bot.fetch_user(user_id)
                    await self.channel.send(f"⏰ <@{user_id}> has been removed from **{mode_data['name']}** queue (timer expired)")
                    # Try to DM the user
                    try:
                        await user.send(f"⏰ You've been removed from the **{mode_data['name']}** PUG queue - your timer expired!")
                    except:
                        pass
                except:
                    await self.channel.send(f"⏰ A player has been removed from **{mode_data['name']}** queue (timer expired)")
            
            # Clean up timer
            if user_id in self.expire_timers:
                del self.expire_timers[user_id]
        
        # Start timer
        task = asyncio.create_task(expire_callback())
        self.expire_timers[user_id] = task
    
    def cancel_expire_timer(self, user_id):
        """Cancel expire timer for a player"""
        if user_id in self.expire_timers:
            self.expire_timers[user_id].cancel()
            del self.expire_timers[user_id]

# Global queue instance (will be set per channel if needed)
queues = {}

def get_queue(channel, game_mode='default'):
    # Resolve alias to actual mode name
    game_mode = db_manager.resolve_mode_alias(game_mode)
    
    # Create a unique key for channel + game mode
    queue_key = f"{channel.id}_{game_mode}"
    if queue_key not in queues:
        queues[queue_key] = PUGQueue(channel, game_mode)
    return queues[queue_key]

def get_channel_queues(channel):
    """Get all active queues for a channel"""
    return {k: v for k, v in queues.items() if k.startswith(f"{channel.id}_")}

@bot.check
async def globally_check_bot_state(ctx):
    """Global check for bot enabled status and channel restriction"""
    global bot_enabled
    
    # Allow tamproon and tamprooff commands regardless of bot state/channel
    if ctx.command.name in ['tamproon', 'tamprooff']:
        return True
    
    # Allow leaderboard command to work in leaderboard channels
    if ctx.command.name == 'leaderboard':
        # Leaderboard has its own channel check, let it through
        return bot_enabled
    
    # Allow only help in DMs
    if isinstance(ctx.channel, discord.DMChannel):
        if ctx.command.name in ['help']:
            return True
        return False
    
    # Check if bot is enabled
    if not bot_enabled:
        return False
    
    # Check channel restriction (only allow in #tampro)
    if ctx.channel.name != ALLOWED_CHANNEL_NAME:
        return False
    
    return True


def is_full_admin(ctx):
    """Check if user has the Admins role (not just PUG Admin)"""
    return any(role.name == "Admins" for role in ctx.author.roles)

def is_pug_admin(ctx):
    """Check if user is a PUG Admin on this server"""
    return db_manager.is_pug_admin(ctx.author.id, ctx.guild.id)

def is_admin(ctx):
    """Check if user is either Admin or PUG Admin"""
    return is_full_admin(ctx) or is_pug_admin(ctx)

async def resolve_player(ctx, player_identifier: str):
    """
    Resolve a player from @mention or display name/username
    Returns (member, discord_id) tuple or (None, None) if not found
    """
    # Check if it's a mention
    if ctx.message.mentions:
        member = ctx.message.mentions[0]
        return member, str(member.id)
    
    # Try to find by display name or username
    for guild_member in ctx.guild.members:
        if (guild_member.display_name.lower() == player_identifier.lower() or 
            guild_member.name.lower() == player_identifier.lower()):
            return guild_member, str(guild_member.id)
    
    return None, None

def get_elo_rank(elo):
    """
    S+: 1800+
    S:  1600-1799
    A:  1300-1599
    B:  900-1299
    C:  650-899
    D:  0-649
    """
    if elo >= 1800:
        return 'S+'
    elif elo >= 1600:
        return 'S'
    elif elo >= 1300:
        return 'A'
    elif elo >= 900:
        return 'B'
    elif elo >= 650:
        return 'C'
    else:
        return 'D'

def get_leaderboard_position(discord_id, server_id):
    """Get player's position on the leaderboard"""
    players = db_manager.get_all_players(server_id)
    
    # Filter out simulation players
    active_players = []
    for p in players:
        try:
            player_id = int(p['discord_id'])
            if player_id < 1000 or player_id >= 2000:
                active_players.append(p)
        except (ValueError, TypeError):
            active_players.append(p)
    
    # Sort by ELO (highest first)
    active_players.sort(key=lambda x: x['elo'], reverse=True)
    
    # Find position
    for i, player in enumerate(active_players):
        if str(player['discord_id']) == str(discord_id):
            return i + 1, len(active_players)
    
    return None, len(active_players)

# Commands
@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print(f'Bot is ready to manage PUGs!')
    print(f'Database: pug_data.db')
    
    # Auto-initialize leaderboard for all guilds
    print("\n🔄 Initializing leaderboards...")
    for guild in bot.guilds:
        try:
            # Check if leaderboard already exists for this guild
            str_guild_id = str(guild.id)
            
            # Find or create #leaderboard channel
            leaderboard_channel = discord.utils.get(guild.text_channels, name='leaderboard')
            
            if not leaderboard_channel:
                print(f"⚠️ No #leaderboard channel found in {guild.name}, skipping auto-init")
                continue
            
            # Check if leaderboard data already exists
            if str_guild_id in leaderboard_auto_update_data:
                print(f"✅ Leaderboard already initialized for {guild.name}")
                continue
            
            # Check if there are any players
            players = db_manager.get_all_players(str_guild_id)
            if not players:
                print(f"⚠️ No players found for {guild.name}, skipping leaderboard init")
                continue
            
            # Initialize leaderboard by calling the leaderboard logic
            print(f"📊 Initializing leaderboard for {guild.name} in #{leaderboard_channel.name}...")
            
            # Filter out simulation players
            active_players = []
            for p in players:
                try:
                    player_id = int(p['discord_id'])
                    if player_id < 1000 or player_id >= 2000:
                        active_players.append(p)
                except (ValueError, TypeError):
                    active_players.append(p)
            
            if not active_players:
                print(f"⚠️ No active players found for {guild.name}")
                continue
            
            # Sort by ELO
            active_players.sort(key=lambda x: x['elo'], reverse=True)
            
            # Build player entries
            entries = []
            for i, player in enumerate(active_players):
                discord_id = player['discord_id']
                elo = int(player['elo'])
                rank = i + 1
                
                member = guild.get_member(int(discord_id))
                if member:
                    name = member.display_name
                else:
                    player_data = db_manager.get_player(discord_id, str_guild_id)
                    name = player_data.get('display_name') or player_data.get('discord_name') or f"Player_{discord_id}"
                    if '#' in name:
                        name = name.split('#')[0]
                
                if len(name) > 8:
                    name = name[:5] + "..."
                
                entries.append({'rank': rank, 'name': name, 'elo': elo})
            
            # Build 3-column layout
            all_lines = []
            total_players = len(entries)
            players_per_column = (total_players + 2) // 3
            
            for row_idx in range(players_per_column):
                columns = []
                for col_idx in range(3):
                    player_idx = row_idx + (col_idx * players_per_column)
                    if player_idx < total_players:
                        entry = entries[player_idx]
                        rank_str = f"#{entry['rank']}".ljust(4)
                        name_str = entry['name'].ljust(8)
                        elo_str = str(entry['elo']).ljust(4)
                        column = f"{rank_str}{name_str}{elo_str}"
                        columns.append(column)
                    else:
                        columns.append(" " * 16)
                line = "  ".join(columns)
                all_lines.append(line.rstrip())
            
            # Split into chunks
            chunk_size = 60
            chunks = [all_lines[i:i + chunk_size] for i in range(0, len(all_lines), chunk_size)]
            
            # Send embeds and store message IDs
            leaderboard_message_ids = []
            for chunk_idx, chunk in enumerate(chunks):
                chunk_text = "\n".join(chunk)
                embed = discord.Embed(
                    title="🏆 Server ELO Leaderboard" if chunk_idx == 0 else f"🏆 Leaderboard (continued)",
                    description=f"```\n{chunk_text}\n```",
                    color=discord.Color.gold()
                )
                if chunk_idx == 0:
                    current_time = datetime.now()
                    embed.set_footer(
                        text=f"Total Players: {len(active_players)} • Auto-updates on ELO changes • Last Updated: {current_time.strftime('%I:%M %p')}"
                    )
                msg = await leaderboard_channel.send(embed=embed)
                leaderboard_message_ids.append(msg.id)
            
            # Store for auto-updates
            leaderboard_auto_update_data[str_guild_id] = {
                'channel_id': leaderboard_channel.id,
                'message_ids': leaderboard_message_ids,
                'last_update': datetime.now()
            }
            
            print(f"✅ Leaderboard initialized for {guild.name} with {len(active_players)} players")
            
        except Exception as e:
            print(f"❌ Error initializing leaderboard for {guild.name}: {e}")
            import traceback
            traceback.print_exc()
    
    print("✅ Leaderboard initialization complete!\n")

@bot.event
async def on_message(message):
    # Ignore bot messages
    if message.author.bot:
        return
    
    content = message.content.strip()
    ctx = await bot.get_context(message)
    
    # Check for dynamic .list<mode> commands (e.g., .list4v4, .list2v2)
    if content.startswith('.list') and len(content) > 5:
        # Check channel restriction
        if not isinstance(ctx.channel, discord.DMChannel) and ctx.channel.name != ALLOWED_CHANNEL_NAME:
            return  # Silently ignore in wrong channel
        
        mode_name = content[5:].strip()  # Extract mode after ".list"
        if mode_name:
            await list_queue.callback(ctx, mode_name)
            return
    
    # Check for dynamic .autopick<mode> commands (e.g., .autopick2v2, .autopick6v6)
    # But NOT .autopickoff (that's a separate command)
    if content.startswith('.autopick') and len(content) > 9 and not content.startswith('.autopickoff'):
        # Check channel restriction
        if not isinstance(ctx.channel, discord.DMChannel) and ctx.channel.name != ALLOWED_CHANNEL_NAME:
            return  # Silently ignore in wrong channel
        
        mode_name = content[9:].strip()  # Extract mode after ".autopick"
        if mode_name:
            await enable_autopick.callback(ctx, mode_name)
            return
    
    # Check for ++ without prefix
    if content.startswith('++'):
        # Check bot state and channel restriction (same as global check)
        if not bot_enabled:
            return  # Silently ignore when bot disabled
        if isinstance(ctx.channel, discord.DMChannel) or ctx.channel.name != ALLOWED_CHANNEL_NAME:
            return  # Silently ignore in DMs or wrong channel
        
        # Extract game mode if provided
        parts = content.split(maxsplit=1)
        game_mode = parts[1] if len(parts) > 1 else None
        
        # Call the join_quick function
        if game_mode:
            await join_quick.callback(ctx, game_mode)
        else:
            await join_quick.callback(ctx)
        return
    
    # Check for +mode syntax (e.g., +tam4, +tam2, +2v2)
    if content.startswith('+') and len(content) > 1 and not content.startswith('++'):
        # Check bot state and channel restriction
        if not bot_enabled:
            return  # Silently ignore when bot disabled
        if isinstance(ctx.channel, discord.DMChannel) or ctx.channel.name != ALLOWED_CHANNEL_NAME:
            return  # Silently ignore in DMs or wrong channel
        
        # Extract the mode (everything after the +)
        mode_input = content[1:].strip().split()[0]  # Get first word after +
        
        # Resolve alias to actual mode name
        resolved_mode = db_manager.resolve_mode_alias(mode_input.lower())
        
        # Special handling for TAM4 or aliases that resolve to default
        if mode_input.upper() == 'TAM4' or resolved_mode == 'default':
            game_mode = 'default'
        else:
            game_mode = resolved_mode
        
        # Validate game mode exists
        mode_data = db_manager.get_game_mode(game_mode)
        if not mode_data:
            # Silently ignore invalid modes (don't spam channel)
            return
        
        # Join the queue using the resolved mode
        queue = get_queue(ctx.channel, game_mode)
        success, error = await queue.add_player(ctx.author)
        
        if success:
            mode_display = mode_data['name']
            spots_filled = len(queue.queue)
            spots_remaining = queue.team_size - spots_filled
            await ctx.send(f"{ctx.author.display_name} joined **{mode_display}** ({spots_filled}/{queue.team_size})")
        else:
            await ctx.send(f"❌ {error}")
        return
    
    # Check for -- without prefix
    if content.startswith('--'):
        # Check bot state and channel restriction (same as global check)
        if not bot_enabled:
            return  # Silently ignore when bot disabled
        if isinstance(ctx.channel, discord.DMChannel) or ctx.channel.name != ALLOWED_CHANNEL_NAME:
            return  # Silently ignore in DMs or wrong channel
        
        # Extract game mode if provided
        parts = content.split(maxsplit=1)
        game_mode = parts[1] if len(parts) > 1 else None
        
        # Call the leave_quick function
        if game_mode:
            await leave_quick.callback(ctx, game_mode)
        else:
            await leave_quick.callback(ctx)
        return
    
    # Check for -mode syntax (e.g., -tam4, -tam2, -2v2)
    if content.startswith('-') and len(content) > 1 and not content.startswith('--'):
        # Check bot state and channel restriction
        if not bot_enabled:
            return  # Silently ignore when bot disabled
        if isinstance(ctx.channel, discord.DMChannel) or ctx.channel.name != ALLOWED_CHANNEL_NAME:
            return  # Silently ignore in DMs or wrong channel
        
        try:
            # Extract the mode (everything after the -)
            mode_input = content[1:].strip().split()[0]  # Get first word after -
            
            # Resolve alias to actual mode name
            resolved_mode = db_manager.resolve_mode_alias(mode_input.lower())
            
            # Special handling for TAM4 or aliases that resolve to default
            if mode_input.upper() == 'TAM4' or resolved_mode == 'default':
                game_mode = 'default'
            else:
                game_mode = resolved_mode
            
            # Validate game mode exists
            mode_data = db_manager.get_game_mode(game_mode)
            if not mode_data:
                await ctx.send(f"❌ Game mode '{mode_input}' not found!")
                return
            
            # Leave the queue using the resolved mode
            queue = get_queue(ctx.channel, game_mode)
            removed = await queue.remove_player(ctx.author.id)  # Returns bool, not tuple
            
            if removed:
                mode_display = mode_data['name']
                spots_filled = len(queue.queue)
                spots_remaining = queue.team_size - spots_filled
                await ctx.send(f"{ctx.author.display_name} left **{mode_display}** ({spots_filled}/{queue.team_size})")
            else:
                await ctx.send(f"❌ You are not in the **{mode_data['name']}** queue!")
        except Exception as e:
            await ctx.send(f"❌ Error leaving queue: {e}")
            import traceback
            traceback.print_exc()
        return
    
    # Process other commands normally
    await bot.process_commands(message)

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return
    
    # Handle ready check
    channel_queues = get_channel_queues(reaction.message.channel)
    for queue_key, queue in channel_queues.items():
        # CRITICAL: Only process reactions on the actual ready check message!
        if queue.state == 'ready_check' and user.id in queue.queue and queue.ready_check_message and reaction.message.id == queue.ready_check_message.id:
            if str(reaction.emoji) == "✅":
                # Ensure ready_responses dict exists and has entry for this user
                if not hasattr(queue, 'ready_responses'):
                    queue.ready_responses = {}
                
                queue.ready_responses[user.id] = True
                
                # Save persistent ready timestamp
                import time
                queue.persistent_ready[user.id] = time.time()
                
                print(f"✅ Player {user.id} readied up - Status: {queue.ready_responses.get(user.id)}")
                
                # Update the ready check message
                await queue.update_ready_check_display()
                
                # Check if everyone is now ready - proceed immediately!
                all_ready = all(queue.ready_responses.get(uid, False) == True for uid in queue.queue)
                
                if all_ready and queue.ready_check_task:
                    # Cancel the timeout task and proceed immediately
                    queue.ready_check_task.cancel()
                
            elif str(reaction.emoji) == "❌":
                # Player actively declined ready check
                # Mark as declined before removing so wait_for_ready_check knows
                queue.ready_responses[user.id] = 'declined'
                
                # Remove this player immediately
                if user.id in queue.queue:
                    queue.queue.remove(user.id)
                    
                    # Get player name
                    member = reaction.message.guild.get_member(user.id)
                    name = member.display_name if member else f"Player_{user.id}"
                    
                    await reaction.message.channel.send(
                        f"{name} declined the ready check and has been removed from the queue"
                    )
                    
                    # Try to promote from waiting queue
                    promoted = await queue.promote_from_waiting_queue()
                    
                    # Check if queue is still full after decline
                    if len(queue.queue) < queue.team_size:
                        # Queue is no longer full, abort ready check and return to waiting
                        if queue.ready_check_task:
                            queue.ready_check_task.cancel()
                        
                        queue.state = 'waiting'
                        queue.ready_responses = {}
                        
                        mode_data = db_manager.get_game_mode(queue.game_mode_name)
                        remaining = len(queue.queue)
                        needed = queue.team_size - remaining
                        
                        await reaction.message.channel.send(
                            f"Ready check cancelled - queue no longer full | **{mode_data['name']}**: {remaining}/{queue.team_size} ({needed} spot{'s' if needed != 1 else ''} remaining)"
                        )
                    else:
                        # Queue is still full, update display and check if all ready
                        await queue.update_ready_check_display()
                        
                        # Check if all remaining players are now ready
                        if queue.queue:  # If queue still has players
                            all_ready = all(queue.ready_responses.get(uid, False) == True for uid in queue.queue)
                            if all_ready and queue.ready_check_task:
                                # Everyone else is ready, proceed immediately!
                                queue.ready_check_task.cancel()

@bot.event
async def on_command_error(ctx, error):
    """Global error handler to silently ignore check failures from wrong channels"""
    # Silently ignore check failures (wrong channel, bot disabled, etc.)
    if isinstance(error, commands.CheckFailure):
        return
    
    # For other errors, you might want to log them or handle differently
    # For now, silently ignore to avoid spam
    pass

@bot.command(name='j', aliases=['J'])
async def join_with_code(ctx, mode_or_code: str = None, code: str = None):
    """Join the PUG - use .j TAM4 for default mode, .j <mode> for other modes, or just .j to join all active"""
    
    # Check if player is already in an active PUG (ready check, picking, etc) - prevents joining other queues
    channel_queues = get_channel_queues(ctx.channel)
    for queue_key, queue in channel_queues.items():
        if ctx.author.id in queue.queue and queue.state in ['ready_check', 'selecting_captains', 'picking']:
            mode_data = db_manager.get_game_mode(queue.game_mode_name)
            mode_display = mode_data['name'] if mode_data else queue.game_mode_name
            await ctx.send(f"❌ You're already in an active **{mode_display}** PUG! Wait for it to complete.")
            return
    
    # If no mode provided, join all active queues (like ++)
    if mode_or_code is None:
        channel_queues = get_channel_queues(ctx.channel)
        joined_queues = []
        already_in = []
        errors = []
        
        # PRIORITY: Sort queues by team_size (largest first) to fill bigger pugs first
        # This prevents filling all modes simultaneously when player joins
        sorted_queues = sorted(
            [(k, q) for k, q in channel_queues.items() if len(q.queue) > 0],
            key=lambda x: x[1].team_size,
            reverse=True
        )
        
        for queue_key, queue in sorted_queues:
            success, error = await queue.add_player(ctx.author)
            mode_data = db_manager.get_game_mode(queue.game_mode_name)
            mode_display = mode_data['name'] if mode_data else queue.game_mode_name
            queue_status = f"{mode_display} ({len(queue.queue)}/{queue.team_size})"
            
            if success:
                joined_queues.append(queue_status)
            elif error and "already in" in error.lower():
                already_in.append(queue_status)
            elif error:
                errors.append(f"{queue_status}: {error}")
        
        if not joined_queues and not already_in:
            await ctx.send("❌ No active pugs to join! Use `.j TAM4` or `.j <mode>` to start a pug.")
            return
        
        messages = []
        if joined_queues:
            messages.append(f"{ctx.author.display_name} joined: {', '.join(joined_queues)}")
        if already_in:
            messages.append(f"{ctx.author.display_name} already in: {', '.join(already_in)}")
        if errors:
            messages.append(f"❌ Errors: {', '.join(errors)}")
        
        await ctx.send("\n".join(messages))
        return
    
    # Mode was provided, proceed with normal join logic
    game_mode = 'default'
    
    # First, try to resolve alias
    potential_alias = mode_or_code.lower()
    resolved_mode = db_manager.resolve_mode_alias(potential_alias)
    
    # Check if joining default mode (requires TAM4 OR an alias that resolves to default)
    if mode_or_code.upper() == 'TAM4' or resolved_mode == 'default':
        # .j TAM4 format for default mode, OR alias pointing to default
        game_mode = 'default'
    else:
        # .j <mode> format for other modes
        game_mode = resolved_mode
        
        # Validate it's not trying to use tam4 in wrong position
        if potential_alias == 'tam4':
            await ctx.send("❌ Invalid format! Use `.j TAM4` or `.J TAM4` for default mode, or `.j <mode>` for other modes.")
            return
    
    # Validate game mode exists
    mode_data = db_manager.get_game_mode(game_mode)
    if not mode_data:
        await ctx.send(f"❌ Game mode '{game_mode}' does not exist! Use `.modes` to see available modes.")
        return
    
    queue = get_queue(ctx.channel, game_mode)
    success, error = await queue.add_player(ctx.author)
    
    if success:
        mode_display = mode_data['name']
        
        # Check if added to waiting queue
        if error and error.startswith("queue_full:"):
            position = error.split(":")[1]
            msg = f"{ctx.author.display_name} added to **{mode_display}** waiting list (#{position}) - {len(queue.queue)}/{queue.team_size} in queue"
            await ctx.send(msg)
        else:
            msg = f"{ctx.author.display_name} joined **{mode_display}** ({len(queue.queue)}/{queue.team_size})"
            await ctx.send(msg)
    else:
        await ctx.send(f"❌ {error}")

@bot.command(name='++')
async def join_quick(ctx, game_mode: str = None):
    """Join the PUG queue (quick) - no mode joins ALL active pugs"""
    
    # Check if player is already in an active PUG (ready check, picking, etc)
    channel_queues = get_channel_queues(ctx.channel)
    for queue_key, queue in channel_queues.items():
        if ctx.author.id in queue.queue and queue.state in ['ready_check', 'selecting_captains', 'picking']:
            mode_data = db_manager.get_game_mode(queue.game_mode_name)
            mode_display = mode_data['name'] if mode_data else queue.game_mode_name
            await ctx.send(f"❌ You're already in an active **{mode_display}** PUG! Wait for it to complete.")
            return
    
    if game_mode:
        # Join specific mode
        game_mode = game_mode.lower()
        
        # Resolve alias to actual mode name
        game_mode = db_manager.resolve_mode_alias(game_mode)
        
        # Validate game mode exists
        mode_data = db_manager.get_game_mode(game_mode)
        if not mode_data:
            await ctx.send(f"❌ Game mode '{game_mode}' does not exist! Use `.modes` to see available modes.")
            return
        
        queue = get_queue(ctx.channel, game_mode)
        
        if len(queue.queue) == 0:
            if game_mode == 'default':
                await ctx.send("❌ Cannot use `++` when pug is empty! Use `.j TAM4` instead.")
            else:
                await ctx.send(f"❌ Cannot use `++` when pug is empty! Use `.j {game_mode}` instead.")
            return
        
        success, error = await queue.add_player(ctx.author)
        
        if success:
            mode_display = mode_data['name']
            
            # Check if added to waiting queue
            if error and error.startswith("queue_full:"):
                position = error.split(":")[1]
                await ctx.send(
                    f"{ctx.author.display_name} added to **{mode_display}** waiting list (#{position})"
                )
            else:
                await ctx.send(f"{ctx.author.display_name} joined **{mode_display}** ({len(queue.queue)}/{queue.team_size})")
        else:
            await ctx.send(f"❌ {error}")
    else:
        # Join all queues with at least 1 player
        channel_queues = get_channel_queues(ctx.channel)
        joined_queues = []
        already_in = []
        errors = []
        
        # PRIORITY: Sort queues by team_size (largest first) to fill bigger pugs first
        # This prevents filling all modes simultaneously when player joins
        sorted_queues = sorted(
            [(k, q) for k, q in channel_queues.items() if len(q.queue) > 0],
            key=lambda x: x[1].team_size,
            reverse=True
        )
        
        for queue_key, queue in sorted_queues:
            success, error = await queue.add_player(ctx.author)
            mode_data = db_manager.get_game_mode(queue.game_mode_name)
            mode_display = mode_data['name'] if mode_data else queue.game_mode_name
            queue_status = f"{mode_display} ({len(queue.queue)}/{queue.team_size})"
            
            if success:
                joined_queues.append(queue_status)
            elif error and "already in" in error.lower():
                already_in.append(queue_status)
            elif error:
                errors.append(f"{queue_status}: {error}")
        
        if not joined_queues and not already_in:
            await ctx.send("❌ No active pugs to join! Use `.j TAM4` or `.j <mode>` to start a pug.")
            return
        
        messages = []
        if joined_queues:
            messages.append(f"{ctx.author.display_name} joined: {', '.join(joined_queues)}")
        if already_in:
            messages.append(f"{ctx.author.display_name} already in: {', '.join(already_in)}")
        if errors:
            messages.append(f"❌ Errors: {', '.join(errors)}")
        
        await ctx.send("\n".join(messages))

@bot.command(name='leave', aliases=['l'])
async def leave(ctx, game_mode: str = None):
    """Leave the PUG queue"""
    if game_mode:
        # Leave specific game mode
        game_mode_input = game_mode.lower()
        
        # Resolve alias
        game_mode_resolved = db_manager.resolve_mode_alias(game_mode_input)
        
        queue = get_queue(ctx.channel, game_mode_resolved)
        if await queue.remove_player(ctx.author.id):
            mode_data = db_manager.get_game_mode(game_mode_resolved)
            await ctx.send(f"{ctx.author.display_name} left **{mode_data['name']}** ({len(queue.queue)}/{queue.team_size})")
        else:
            await ctx.send(f"You're not in the {game_mode_input} pug!")
    else:
        # Leave all queues in this channel
        removed_from = []
        channel_queues = get_channel_queues(ctx.channel)
        for queue_key, queue in channel_queues.items():
            if await queue.remove_player(ctx.author.id):
                removed_from.append(queue.game_mode_name)
        
        if removed_from:
            modes_str = ", ".join(removed_from)
            await ctx.send(f"{ctx.author.display_name} left: {modes_str}")
        else:
            await ctx.send("You're not in any pug!")

@bot.command(name='--')
async def leave_quick(ctx, game_mode: str = None):
    """Leave the PUG queue (quick command)"""
    await leave.callback(ctx, game_mode)

@bot.command(name='lva')
async def leave_all(ctx):
    """Leave all queues (explicit command)"""
    removed_from = []
    channel_queues = get_channel_queues(ctx.channel)
    for queue_key, queue in channel_queues.items():
        if await queue.remove_player(ctx.author.id):
            removed_from.append(queue.game_mode_name)
    
    if removed_from:
        modes_str = ", ".join(removed_from)
        await ctx.send(f"{ctx.author.display_name} left all: {modes_str}")
    else:
        await ctx.send("You're not in any pug!")

@bot.command(name='expire')
async def set_expire(ctx, time_str: str, game_mode: str = None):
    """Set a timer to auto-remove yourself from queue. Usage: .expire 10m [mode]"""
    # Parse time string (e.g., "10m", "30m", "1h")
    time_str = time_str.lower().strip()
    
    try:
        if time_str.endswith('m'):
            minutes = int(time_str[:-1])
        elif time_str.endswith('h'):
            hours = int(time_str[:-1])
            minutes = hours * 60
        else:
            # Assume minutes if no unit
            minutes = int(time_str)
    except ValueError:
        await ctx.send("❌ Invalid time format! Use: `.expire 10m` or `.expire 1h`")
        return
    
    # Validate time range (1 minute to 2 hours)
    if minutes < 1:
        await ctx.send("❌ Time must be at least 1 minute!")
        return
    if minutes > 120:
        await ctx.send("❌ Maximum expire time is 2 hours (120 minutes)!")
        return
    
    if game_mode:
        # Set expire for specific mode
        game_mode_input = game_mode.lower()
        game_mode_resolved = db_manager.resolve_mode_alias(game_mode_input)
        
        queue = get_queue(ctx.channel, game_mode_resolved)
        
        if ctx.author.id not in queue.queue:
            mode_data = db_manager.get_game_mode(game_mode_resolved)
            await ctx.send(f"❌ You're not in the **{mode_data['name']}** queue!")
            return
        
        await queue.set_expire_timer(ctx.author.id, minutes)
        mode_data = db_manager.get_game_mode(game_mode_resolved)
        
        # Format time display
        if minutes >= 60:
            time_display = f"{minutes // 60}h {minutes % 60}m" if minutes % 60 else f"{minutes // 60}h"
        else:
            time_display = f"{minutes}m"
        
        await ctx.send(f"⏰ {ctx.author.mention} will be auto-removed from **{mode_data['name']}** queue in **{time_display}**")
    else:
        # Set expire for all queues player is in
        channel_queues = get_channel_queues(ctx.channel)
        set_in_modes = []
        
        for queue_key, queue in channel_queues.items():
            if ctx.author.id in queue.queue:
                await queue.set_expire_timer(ctx.author.id, minutes)
                set_in_modes.append(queue.game_mode_name)
        
        if not set_in_modes:
            await ctx.send("❌ You're not in any queue!")
            return
        
        # Format time display
        if minutes >= 60:
            time_display = f"{minutes // 60}h {minutes % 60}m" if minutes % 60 else f"{minutes // 60}h"
        else:
            time_display = f"{minutes}m"
        
        modes_str = ", ".join([db_manager.get_game_mode(m)['name'] for m in set_in_modes])
        await ctx.send(f"⏰ {ctx.author.mention} will be auto-removed from queue(s) in **{time_display}**: {modes_str}")

@bot.command(name='cancelexpire', aliases=['noexpire', 'removeexpire'])
async def cancel_expire(ctx, game_mode: str = None):
    """Cancel your expire timer. Usage: .cancelexpire [mode]"""
    
    if game_mode:
        # Cancel expire for specific mode
        game_mode_input = game_mode.lower()
        game_mode_resolved = db_manager.resolve_mode_alias(game_mode_input)
        
        queue = get_queue(ctx.channel, game_mode_resolved)
        
        # Check if player is in queue
        if ctx.author.id not in queue.queue and ctx.author.id not in queue.waiting_queue:
            mode_data = db_manager.get_game_mode(game_mode_resolved)
            await ctx.send(f"❌ You're not in the **{mode_data['name']}** queue!")
            return
        
        # Check if they have an expire timer
        if ctx.author.id not in queue.expire_timers:
            mode_data = db_manager.get_game_mode(game_mode_resolved)
            await ctx.send(f"❌ You don't have an expire timer set for **{mode_data['name']}**!")
            return
        
        # Cancel the timer
        queue.cancel_expire_timer(ctx.author.id)
        mode_data = db_manager.get_game_mode(game_mode_resolved)
        
        await ctx.send(f"✅ {ctx.author.mention} cancelled expire timer for **{mode_data['name']}** queue")
    else:
        # Cancel expire for all queues player is in
        channel_queues = get_channel_queues(ctx.channel)
        cancelled_modes = []
        
        for queue_key, queue in channel_queues.items():
            if (ctx.author.id in queue.queue or ctx.author.id in queue.waiting_queue) and ctx.author.id in queue.expire_timers:
                queue.cancel_expire_timer(ctx.author.id)
                cancelled_modes.append(queue.game_mode_name)
        
        if not cancelled_modes:
            await ctx.send("❌ You don't have any expire timers set!")
            return
        
        modes_str = ", ".join([db_manager.get_game_mode(m)['name'] for m in cancelled_modes])
        await ctx.send(f"✅ {ctx.author.mention} cancelled expire timer(s) for: {modes_str}")

@bot.command(name='list')
async def list_queue(ctx, game_mode: str = None):
    """List all players in the queue(s)"""
    channel_queues = get_channel_queues(ctx.channel)
    
    if game_mode:
        # Show specific mode
        game_mode_input = game_mode.lower()
        
        # Resolve alias
        game_mode_resolved = db_manager.resolve_mode_alias(game_mode_input)
        
        queue = get_queue(ctx.channel, game_mode_resolved)
        queue_list = queue.get_queue_list()
        
        mode_data = db_manager.get_game_mode(game_mode_resolved)
        
        if not queue_list:
            await ctx.send(f"**{mode_data['name']}** pug is empty!")
            return
        
        embed = discord.Embed(
            title=f"{mode_data['name']} Pug ({len(queue_list)}/{queue.team_size})", 
            color=discord.Color.blue()
        )
        
        players = []
        for i, uid in enumerate(queue_list):
            player_data = db_manager.get_player(uid, str(ctx.guild.id))
            elo = player_data['elo']
            rank = get_elo_rank(elo)
            member = ctx.guild.get_member(uid)
            name = member.display_name if member else f"Player_{uid}"
            players.append(f"{i+1}. {name} - {elo:.0f} ELO ({rank})")
        
        embed.add_field(name="Active Queue", value=" 🔶 ".join(players), inline=False)
        
        # Show waiting queue if not empty
        if queue.waiting_queue:
            waiting_players = []
            for i, uid in enumerate(queue.waiting_queue):
                player_data = db_manager.get_player(uid, str(ctx.guild.id))
                elo = player_data['elo']
                rank = get_elo_rank(elo)
                member = ctx.guild.get_member(uid)
                name = member.display_name if member else f"Player_{uid}"
                waiting_players.append(f"{i+1}. {name} - {elo:.0f} ELO ({rank})")
            
            embed.add_field(
                name=f"Waiting List ({len(queue.waiting_queue)} player{'s' if len(queue.waiting_queue) != 1 else ''})",
                value=" 🔶 ".join(waiting_players),
                inline=False
            )
        
        # Add timestamp footer
        current_time = datetime.now()
        embed.set_footer(text=f"Local Time: {current_time.strftime('%I:%M:%S %p')} • {current_time.strftime('%B %d, %Y')}")
        
        await ctx.send(embed=embed)
    else:
        # Show all active queues
        has_queues = False
        for queue_key, queue in channel_queues.items():
            if queue.queue:
                has_queues = True
                break
        
        if not has_queues:
            await ctx.send("No active pugs!")
            return
        
        embed = discord.Embed(title="Active Pugs", color=discord.Color.blue())
        
        for queue_key, queue in channel_queues.items():
            if queue.queue:
                mode_data = db_manager.get_game_mode(queue.game_mode_name)
                players = []
                for uid in queue.queue:
                    player_data = db_manager.get_player(uid, str(ctx.guild.id))
                    elo = player_data['elo']
                    rank = get_elo_rank(elo)
                    member = ctx.guild.get_member(uid)
                    name = member.display_name if member else f"Player_{uid}"
                    players.append(f"{name} - {elo:.0f} ({rank})")
                
                field_name = f"{mode_data['name']} ({len(queue.queue)}/{queue.team_size})"
                if queue.waiting_queue:
                    field_name += f" + {len(queue.waiting_queue)} waiting"
                
                embed.add_field(
                    name=field_name,
                    value=" 🔶 ".join(players),
                    inline=False
                )
        
        # Add timestamp footer
        current_time = datetime.now()
        embed.set_footer(text=f"Local Time: {current_time.strftime('%I:%M:%S %p')} • {current_time.strftime('%B %d, %Y')}")
        
        if embed.fields:
            await ctx.send(embed=embed)
        else:
            await ctx.send("All pugs are empty!")

@bot.command(name='who')
async def who_queue(ctx, game_mode: str = None):
    """List all players in the queue (alias for .list)"""
    await list_queue.callback(ctx, game_mode)

@bot.command(name='captain')
async def become_captain(ctx):
    """Volunteer to become a captain"""
    # Find which queue the user is in that's currently selecting captains
    channel_queues = get_channel_queues(ctx.channel)
    found_queue = None
    
    for queue_key, queue in channel_queues.items():
        if queue.state == 'selecting_captains' and ctx.author.id in queue.queue:
            found_queue = queue
            break
    
    if not found_queue:
        await ctx.send("❌ You are not in a pug that's currently selecting captains!")
        return
    
    success, error = await found_queue.volunteer_captain(ctx.author.id)
    if not success:
        await ctx.send(f"❌ {error}")

@bot.command(name='capfor')
async def takeover_captain(ctx, team: str):
    """Take over as captain for a team"""
    # Find which queue the user is in that's currently picking
    channel_queues = get_channel_queues(ctx.channel)
    found_queue = None
    
    for queue_key, queue in channel_queues.items():
        if queue.state == 'picking' and ctx.author.id in queue.queue:
            found_queue = queue
            break
    
    if not found_queue:
        await ctx.send("❌ You are not in a pug that's currently picking!")
        return
    
    team = team.lower()
    
    if team not in ['red-team', 'blue-team']:
        await ctx.send("❌ Use `.capfor red-team` or `.capfor blue-team`")
        return
    
    team_name = team.split('-')[0]
    success, error = await found_queue.takeover_captain(ctx.author.id, team_name)
    
    if not success:
        await ctx.send(f"❌ {error}")

@bot.command(name='pick', aliases=['p'])
async def pick_player(ctx, *, player_identifier: str):
    """Pick player(s) for your team (captain only) - use number or name. Can pick 2 during double pick: .pick 3 5"""
    # Find which queue the user is captain in
    channel_queues = get_channel_queues(ctx.channel)
    found_queue = None
    
    for queue_key, queue in channel_queues.items():
        if ctx.author.id == queue.red_captain or ctx.author.id == queue.blue_captain:
            found_queue = queue
            break
    
    if not found_queue:
        await ctx.send("❌ You are not a captain in any active pug!")
        return
    
    # Determine which team the captain is on
    team = None
    if ctx.author.id == found_queue.red_captain:
        team = 'red'
    elif ctx.author.id == found_queue.blue_captain:
        team = 'blue'
    
    # Get available players
    available = found_queue.get_available_players()
    
    if not available:
        await ctx.send("❌ No players available to pick!")
        return
    
    # Parse player identifier(s) - can be multiple numbers like "3 5"
    player_identifier = player_identifier.strip()
    picks = player_identifier.split()
    member_ids = []
    
    for pick in picks:
        member_id = None
        
        # Check if it's a number
        if pick.isdigit():
            pick_number = int(pick)
            
            # Use initial_queue for consistent numbering
            if found_queue.initial_queue:
                if 1 <= pick_number <= len(found_queue.initial_queue):
                    target_uid = found_queue.initial_queue[pick_number - 1]
                    if target_uid in available:
                        member_id = target_uid
                    else:
                        await ctx.send(f"❌ Player #{pick_number} is not available!")
                        return
                else:
                    await ctx.send(f"❌ Invalid number! Pick between 1 and {len(found_queue.initial_queue)}.")
                    return
            else:
                # Fallback if no initial_queue
                if 1 <= pick_number <= len(available):
                    member_id = available[pick_number - 1]
                else:
                    await ctx.send(f"❌ Invalid number! Pick between 1 and {len(available)}.")
                    return
        else:
            # Try to find by name
            for guild_member in ctx.guild.members:
                if (guild_member.display_name.lower() == pick.lower() or 
                    guild_member.name.lower() == pick.lower()):
                    if guild_member.id in available:
                        member_id = guild_member.id
                    else:
                        await ctx.send(f"❌ {guild_member.display_name} is not available!")
                        return
                    break
            
            if not member_id:
                await ctx.send(f"❌ Could not find player '{pick}'. Use player number or exact display name.")
                return
        
        member_ids.append(member_id)
    
    # Validate number of picks
    if len(member_ids) > 2:
        await ctx.send("❌ You can only pick up to 2 players at once!")
        return
    
    # Make the picks
    for member_id in member_ids:
        success, error = await found_queue.pick_player(ctx.author.id, member_id, team)
        if not success:
            await ctx.send(f"❌ {error}")
            return

@bot.command(name='addmode')
async def add_mode(ctx, name: str, team_size: int, *, description: str = ""):
    """Add a new game mode (Admin only). Example: .addmode 6v6 12 Larger teams"""
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    success, error = db_manager.add_game_mode(name.lower(), name, team_size, description)
    if success:
        await ctx.send(f"✅ Added game mode **{name}** with team size {team_size} ({team_size//2}v{team_size//2})!")
    else:
        await ctx.send(f"❌ {error}")

@bot.command(name='removemode')
async def remove_mode(ctx, name: str):
    """Remove a game mode (Admin only)"""
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    success, error = db_manager.remove_mode(name.lower())
    if success:
        await ctx.send(f"✅ Removed game mode **{name}**!")
    else:
        await ctx.send(f"❌ {error}")

@bot.command(name='addalias')
async def add_alias(ctx, mode: str, alias: str):
    """Add an alias for a game mode (Admin only). Example: .addalias 2v2 duos"""
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    mode = mode.lower()
    alias = alias.lower()
    
    success, error = db_manager.add_mode_alias(alias, mode)
    if success:
        await ctx.send(f"✅ Added alias **{alias}** for mode **{mode}**!\nPlayers can now use `.j {alias}`, `.list{alias}`, `.autopick{alias}`, etc.")
    else:
        await ctx.send(f"❌ {error}")

@bot.command(name='removealias')
async def remove_alias(ctx, alias: str):
    """Remove a mode alias (Admin only)"""
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    alias = alias.lower()
    
    success, error = db_manager.remove_mode_alias(alias)
    if success:
        await ctx.send(f"✅ Removed alias **{alias}**!")
    else:
        await ctx.send(f"❌ {error}")

@bot.command(name='addmap')
async def add_map(ctx, *, map_name: str):
    """Add a map to the map pool (Admin only). Example: .addmap DM-Deck16"""
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Check if map already exists
    if map_name in MAP_POOL:
        await ctx.send(f"❌ **{map_name}** is already in the map pool!")
        return
    
    # Add to map pool
    MAP_POOL.append(map_name)
    MAP_POOL.sort()  # Keep alphabetically sorted
    
    await ctx.send(f"✅ Added **{map_name}** to the map pool! (Total: {len(MAP_POOL)} maps)")

@bot.command(name='removemap')
async def remove_map(ctx, *, map_name: str):
    """Remove a map from the map pool (Admin only). Example: .removemap DM-Deck16"""
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Check if map exists
    if map_name not in MAP_POOL:
        await ctx.send(f"❌ **{map_name}** is not in the map pool!")
        return
    
    # Remove from map pool
    MAP_POOL.remove(map_name)
    
    # Also remove from all server cooldown lists
    for server_id in list(recent_tiebreakers.keys()):
        if map_name in recent_tiebreakers[server_id]:
            recent_tiebreakers[server_id].remove(map_name)
    
    await ctx.send(f"✅ Removed **{map_name}** from the map pool! (Total: {len(MAP_POOL)} maps)")

@bot.command(name='maps', aliases=['maplist'])
async def list_maps(ctx):
    """Show all maps in the tiebreaker pool with cooldown status"""
    if not MAP_POOL:
        await ctx.send("📋 No maps in the pool!")
        return
    
    server_id = str(ctx.guild.id)
    
    embed = discord.Embed(
        title=f"🗺️ Tiebreaker Map Pool ({len(MAP_POOL)} maps)",
        color=discord.Color.blue()
    )
    
    # Get cooldown maps for this server
    on_cooldown = recent_tiebreakers.get(server_id, [])
    
    # Separate available and cooldown maps
    available_maps = []
    cooldown_maps = []
    
    for map_name in sorted(MAP_POOL):
        if map_name in on_cooldown:
            # Show position in cooldown (1 = most recent, can't be picked for 3 PUGs)
            position = on_cooldown.index(map_name) + 1
            cooldown_maps.append(f"~~{map_name}~~ ({position} PUG{'s' if position != 1 else ''} ago)")
        else:
            available_maps.append(map_name)
    
    # Show available maps
    if available_maps:
        embed.add_field(
            name=f"✅ Available ({len(available_maps)})",
            value=", ".join(available_maps),
            inline=False
        )
    
    # Show maps on cooldown
    if cooldown_maps:
        embed.add_field(
            name=f"⏳ On Cooldown ({len(cooldown_maps)})",
            value="\n".join(cooldown_maps),
            inline=False
        )
        embed.add_field(
            name="ℹ️ Cooldown Info",
            value="Maps are on cooldown for 3 completed PUGs to prevent repeats",
            inline=False
        )
    
    embed.set_footer(text="Use .addmap or .removemap to modify (Admin only)")
    
    await ctx.send(embed=embed)

    
    success, error = db_manager.remove_mode_alias(alias.lower())
    if success:
        await ctx.send(f"✅ Removed alias **{alias}**!")
    else:
        await ctx.send(f"❌ {error}")

@bot.command(name='aliases')
async def list_aliases(ctx, mode: str = None):
    """List all aliases or aliases for a specific mode"""
    if mode:
        # Show aliases for specific mode
        mode = db_manager.resolve_mode_alias(mode.lower())
        mode_data = db_manager.get_game_mode(mode)
        
        if not mode_data:
            await ctx.send(f"❌ Mode '{mode}' does not exist!")
            return
        
        aliases = db_manager.get_mode_aliases(mode)
        
        if aliases:
            alias_list = ", ".join([f"`{a}`" for a in aliases])
            await ctx.send(f"**{mode_data['name']}** aliases: {alias_list}")
        else:
            await ctx.send(f"**{mode_data['name']}** has no aliases.")
    else:
        # Show all aliases
        modes = db_manager.get_all_game_modes()
        embed = discord.Embed(title="🔖 Mode Aliases", color=discord.Color.blue())
        
        has_aliases = False
        for mode_name, mode_data in modes.items():
            aliases = db_manager.get_mode_aliases(mode_name)
            if aliases:
                has_aliases = True
                alias_list = ", ".join([f"`{a}`" for a in aliases])
                embed.add_field(
                    name=f"{mode_data['name']}",
                    value=alias_list,
                    inline=False
                )
        
        if has_aliases:
            await ctx.send(embed=embed)
        else:
            await ctx.send("📋 No mode aliases have been configured.")

@bot.command(name='modes')
async def list_modes(ctx):
    """List all available game modes"""
    modes = db_manager.get_all_game_modes()
    
    embed = discord.Embed(title="🎮 Available Game Modes", color=discord.Color.purple())
    
    for mode_name, mode_data in modes.items():
        # Get aliases for this mode
        aliases = db_manager.get_mode_aliases(mode_name)
        alias_text = f"\nAliases: {', '.join([f'`{a}`' for a in aliases])}" if aliases else ""
        
        embed.add_field(
            name=f"{mode_data['name']} ({mode_data['team_size']//2}v{mode_data['team_size']//2})",
            value=f"Total players: {mode_data['team_size']}\n{mode_data['description'] or 'No description'}{alias_text}",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='reset')
async def reset_queue(ctx, game_mode: str = None):
    """Reset the PUG queue (Admin only)"""
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    if game_mode:
        # Resolve alias
        game_mode_resolved = db_manager.resolve_mode_alias(game_mode.lower())
        
        queue = get_queue(ctx.channel, game_mode_resolved)
        queue.reset()
        mode_data = db_manager.get_game_mode(game_mode_resolved)
        await ctx.send(f"✅ **{mode_data['name']}** pug has been reset!")
        
        # Restart team selection if queue is still full
        if len(queue.queue) == queue.team_size:
            if queue.autopick_mode:
                # Autopick mode - go straight to team balancing
                await ctx.channel.send("Auto-balancing teams...")
                queue.state = 'picking'
                await queue.autopick_teams()
            elif queue.state == 'selecting_captains':
                # Manual pick mode - restart captain selection
                await queue.start_captain_selection()
    else:
        channel_queues = get_channel_queues(ctx.channel)
        for queue_key, queue in channel_queues.items():
            queue.reset()
            
            # Restart team selection for each full queue
            if len(queue.queue) == queue.team_size:
                if queue.autopick_mode:
                    # Autopick mode - go straight to team balancing
                    await ctx.channel.send(f"Auto-balancing **{db_manager.get_game_mode(queue.game_mode_name)['name']}** teams...")
                    queue.state = 'picking'
                    await queue.autopick_teams()
                elif queue.state == 'selecting_captains':
                    # Manual pick mode - restart captain selection
                    await queue.start_captain_selection()
        
        await ctx.send("✅ All pugs have been reset!")

@bot.command(name='addplayer')
async def add_player_admin(ctx, player_name: str, mode: str = 'default'):
    """Add a player to the queue (Admin only)
    
    Usage: 
    .addplayer @Player [mode]
    .addplayer PlayerName [mode]
    """
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Resolve player from @mention or name
    member, discord_id = await resolve_player(ctx, player_name)
    
    if not member:
        await ctx.send(f"❌ Could not find player '{player_name}'. Use @mention or exact display name.")
        return
    
    # Resolve alias
    mode_resolved = db_manager.resolve_mode_alias(mode.lower())
    
    # Validate mode exists
    mode_data = db_manager.get_game_mode(mode_resolved)
    if not mode_data:
        await ctx.send(f"❌ Mode '{mode}' does not exist! Use `.modes` to see available modes.")
        return
    
    queue = get_queue(ctx.channel, mode_resolved)
    success, error = await queue.add_player(member)
    
    if success:
        await ctx.send(f"✅ Added {member.mention} to the **{mode_data['name']}** pug! ({len(queue.queue)}/{queue.team_size})")
    else:
        await ctx.send(f"❌ {error}")

@bot.command(name='removeplayer')
async def remove_player_admin(ctx, player_name: str, mode: str = 'default'):
    """Remove a player from the queue (Admin only)
    
    Usage:
    .removeplayer @Player [mode]
    .removeplayer PlayerName [mode]
    """
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Resolve player from @mention or name
    member, discord_id = await resolve_player(ctx, player_name)
    
    if not member:
        await ctx.send(f"❌ Could not find player '{player_name}'. Use @mention or exact display name.")
        return
    
    # Resolve alias
    mode_resolved = db_manager.resolve_mode_alias(mode.lower())
    
    # Validate mode exists
    mode_data = db_manager.get_game_mode(mode_resolved)
    if not mode_data:
        await ctx.send(f"❌ Mode '{mode}' does not exist! Use `.modes` to see available modes.")
        return
    
    queue = get_queue(ctx.channel, mode_resolved)
    if await queue.remove_player(member.id):
        await ctx.send(f"✅ Removed {member.mention} from the **{mode_data['name']}** pug. ({len(queue.queue)}/{queue.team_size})")
    else:
        await ctx.send(f"❌ {member.mention} is not in the **{mode_data['name']}** pug!")

@bot.command(name='timeout')
async def timeout_player(ctx, player_name: str, duration: str):
    """Timeout a player (Admin only)
    
    Usage:
    .timeout @Player 30M
    .timeout PlayerName 30M
    """
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Resolve player from @mention or name
    member, discord_id = await resolve_player(ctx, player_name)
    
    if not member:
        await ctx.send(f"❌ Could not find player '{player_name}'. Use @mention or exact display name.")
        return
    
    # Parse duration
    duration = duration.upper()
    time_value = int(''.join(filter(str.isdigit, duration)))
    time_unit = ''.join(filter(str.isalpha, duration))
    
    if time_unit == 'S':
        delta = timedelta(seconds=time_value)
    elif time_unit == 'M':
        delta = timedelta(minutes=time_value)
    elif time_unit == 'H':
        delta = timedelta(hours=time_value)
    else:
        await ctx.send("❌ Invalid time format! Use S (seconds), M (minutes), or H (hours)")
        return
    
    timeout_end = datetime.now() + delta
    db_manager.add_timeout(member.id, timeout_end)
    
    await ctx.send(f"✅ {member.mention} has been timed out until {timeout_end.strftime('%Y-%m-%d %H:%M:%S')}")

@bot.command(name='sim')
async def simulation_mode(ctx, game_mode: str = 'default'):
    """Enable simulation mode with fake players (Admin only). Usage: .sim or .sim 2v2"""
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Resolve mode alias
    game_mode_resolved = db_manager.resolve_mode_alias(game_mode.lower())
    
    # Check if mode exists
    mode_data = db_manager.get_game_mode(game_mode_resolved)
    if not mode_data:
        await ctx.send(f"❌ Game mode '{game_mode}' not found!")
        return
    
    queue = get_queue(ctx.channel, game_mode_resolved)
    queue.simulation_mode = True
    
    # Get the correct number of players for this mode
    num_players = mode_data['team_size']  # team_size is total players
    
    # Add fake players
    fake_players = [1000 + i for i in range(num_players)]
    names = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf", "Hotel", 
             "India", "Juliet", "Kilo", "Lima", "Mike", "November", "Oscar", "Papa"]
    
    for i, fake_id in enumerate(fake_players):
        queue.queue.append(fake_id)
        # Create fake player in DB if not exists
        player_data = db_manager.get_player(fake_id, self.server_id)
        if player_data['total_pugs'] == 0:
            # Initialize with some stats
            conn = db_manager.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE players 
                SET elo = ?
                WHERE discord_id = ?
            ''', (700 + (i * 50), str(fake_id)))
            conn.commit()
            conn.close()
    
    await ctx.send(f"✅ Simulation mode enabled for **{mode_data['name']}** with {num_players} fake players!")
    await queue.check_queue_full()

@bot.command(name='simoff')
async def simulation_off(ctx, game_mode: str = 'default'):
    """Disable simulation mode (Admin only). Usage: .simoff or .simoff 2v2"""
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Resolve mode alias
    game_mode_resolved = db_manager.resolve_mode_alias(game_mode.lower())
    
    queue = get_queue(ctx.channel, game_mode_resolved)
    queue.simulation_mode = False
    queue.reset()
    
    mode_data = db_manager.get_game_mode(game_mode_resolved)
    await ctx.send(f"✅ Simulation mode disabled for **{mode_data['name']}**!")

@bot.command(name='skipcheckin')
async def skip_checkin(ctx, game_mode: str = 'default'):
    """Skip the ready check phase (Admin only, useful for simulation)"""
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    queue = get_queue(ctx.channel, game_mode.lower())
    
    if queue.state != 'ready_check':
        await ctx.send("❌ No ready check is currently in progress for this pug!")
        return
    
    # Cancel the ready check task
    if queue.ready_check_task:
        queue.ready_check_task.cancel()
    
    # Mark all players as ready
    for uid in queue.queue:
        queue.ready_responses[uid] = True
    
    # Save initial queue order for consistent numbering
    queue.initial_queue = queue.queue.copy()
    
    await ctx.send("✅ Ready check skipped! Moving to captain selection...")
    queue.state = 'selecting_captains'
    await queue.start_captain_selection()

@bot.command(name='winner')
async def report_winner(ctx, team_or_pug: str, team: str = None):
    """Report the winner of a PUG - Players vote, Admins override instantly
    
    Usage:
    .winner red - Reports red team won for your most recent PUG
    .winner blue - Reports blue team won for your most recent PUG
    .winner 5 red - Reports red team won for PUG #5
    """
    # Parse arguments
    pug_number = None
    winning_team = None
    
    if team is None:
        # Format: .winner red/blue (no PUG number specified)
        winning_team = team_or_pug.lower()
    else:
        # Format: .winner 5 red (PUG number specified)
        try:
            pug_number = int(team_or_pug)
            winning_team = team.lower()
        except ValueError:
            await ctx.send("❌ Invalid format! Use `.winner red/blue` or `.winner <pug#> red/blue`")
            return
    
    if winning_team not in ['red', 'blue']:
        await ctx.send("❌ Team must be 'red' or 'blue'")
        return
    
    # Find the PUG to report on
    recent_pugs = db_manager.get_recent_pugs(20)
    pug = None
    
    if pug_number is not None:
        # Find specific PUG by number
        for p in recent_pugs:
            if p['number'] == pug_number:
                pug = p
                break
        
        if not pug:
            await ctx.send(f"❌ Could not find PUG #{pug_number}!")
            return
        
        if pug.get('winner'):
            await ctx.send(f"❌ PUG #{pug_number} already has a winner recorded: {pug['winner'].upper()} team!")
            return
        
        if pug.get('status') == 'killed':
            await ctx.send(f"❌ PUG #{pug_number} was cancelled/killed!")
            return
    else:
        # Find most recent PUG that the player was in
        player_pugs = []
        for p in recent_pugs:
            if not p.get('winner') and p.get('status') != 'killed':
                all_players = p['red_team'] + p['blue_team']
                if str(ctx.author.id) in all_players:
                    player_pugs.append(p)
        
        if not player_pugs:
            # If player wasn't in any PUG and they're not admin, show error
            if not is_admin(ctx):
                await ctx.send("❌ You weren't in any recent unfinished PUGs! Use `.winner <pug#> <team>` to specify which PUG.")
                return
            
            # Admin can report on any PUG - find most recent unfinished
            for p in recent_pugs:
                if not p.get('winner') and p.get('status') != 'killed':
                    pug = p
                    break
            
            if not pug:
                await ctx.send("❌ No unfinished PUGs found!")
                return
        else:
            # Use the most recent PUG the player was in
            pug = player_pugs[0]
    
    # Check if user is admin
    if is_admin(ctx):
        # Admin override - instant result
        await process_winner(ctx, pug, winning_team, admin_override=True)
    else:
        # Player must be in the PUG to vote
        all_players = pug['red_team'] + pug['blue_team']
        
        if str(ctx.author.id) not in all_players:
            await ctx.send(f"❌ You weren't in PUG #{pug['number']}! Only players from that game can vote.")
            return
        
        # Start voting
        await start_winner_vote(ctx, pug, winning_team, all_players)

async def start_winner_vote(ctx, pug, team, all_players):
    """Start voting process for declaring winner"""
    votes_needed = len(all_players) // 2 + 1
    
    # Create vote message
    team_emoji = '🔴' if team == 'red' else '🔵'
    vote_msg = await ctx.send(
        f"🗳️ **Vote to declare {team_emoji} {team.upper()} team winner of PUG #{pug['number']}**\n"
        f"Players in this PUG, react with ✅ to confirm.\n"
        f"Requires **{votes_needed}/{len(all_players)}** votes to pass.\n"
        f"Vote ends in 60 seconds or when majority is reached."
    )
    
    # Add reactions
    await vote_msg.add_reaction("✅")
    await vote_msg.add_reaction("❌")
    
    # Monitor reactions for 60 seconds
    start_time = asyncio.get_event_loop().time()
    timeout = 60
    
    try:
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            remaining = timeout - elapsed
            
            if remaining <= 0:
                break
            
            # Check current vote count
            vote_msg = await ctx.channel.fetch_message(vote_msg.id)
            yes_votes = 0
            
            for reaction in vote_msg.reactions:
                if str(reaction.emoji) == "✅":
                    users = [user async for user in reaction.users()]
                    yes_votes = sum(1 for user in users if not user.bot and str(user.id) in all_players)
                    break
            
            # If majority reached, process winner immediately
            if yes_votes >= votes_needed:
                await process_winner(ctx, pug, team, admin_override=False)
                await ctx.send(f"✅ **Vote passed! {team.upper()} team wins PUG #{pug['number']}** ({yes_votes}/{len(all_players)} votes)")
                return
            
            # Wait before checking again
            await asyncio.sleep(min(2, remaining))
        
        # Timeout reached, count final votes
        vote_msg = await ctx.channel.fetch_message(vote_msg.id)
        yes_votes = 0
        
        for reaction in vote_msg.reactions:
            if str(reaction.emoji) == "✅":
                users = [user async for user in reaction.users()]
                yes_votes = sum(1 for user in users if not user.bot and str(user.id) in all_players)
                break
        
        if yes_votes >= votes_needed:
            await process_winner(ctx, pug, team, admin_override=False)
            await ctx.send(f"✅ **Vote passed! {team.upper()} team wins PUG #{pug['number']}** ({yes_votes}/{len(all_players)} votes)")
        else:
            await ctx.send(f"❌ **Vote failed.** Only {yes_votes}/{votes_needed} votes received. PUG #{pug['number']} result not recorded.")
    
    except Exception as e:
        await ctx.send(f"⚠️ Error during voting: {e}")

@bot.command(name='splitwin')
async def split_win(ctx, pug_number: int = None):
    """Declare a split result (1-1 in BO3) - both teams get small ELO change
    
    Usage: .splitwin or .splitwin <pug#>
    
    For Best-of-3 matches that end 1-1 without a tiebreaker.
    Both teams receive ELO as if they won 0.5 games (draw).
    Requires 50%+1 vote to pass.
    """
    
    # Find the PUG to report on
    recent_pugs = db_manager.get_recent_pugs(20)
    pug = None
    
    if pug_number is not None:
        # Find specific PUG by number
        for p in recent_pugs:
            if p['number'] == pug_number:
                pug = p
                break
        
        if not pug:
            await ctx.send(f"❌ Could not find PUG #{pug_number}!")
            return
        
        if pug.get('winner'):
            await ctx.send(f"❌ PUG #{pug_number} already has a result recorded!")
            return
        
        if pug.get('status') == 'killed':
            await ctx.send(f"❌ PUG #{pug_number} was cancelled/killed!")
            return
    else:
        # Find most recent PUG that the player was in
        player_pugs = []
        for p in recent_pugs:
            if not p.get('winner') and p.get('status') != 'killed':
                all_players = p['red_team'] + p['blue_team']
                if str(ctx.author.id) in all_players:
                    player_pugs.append(p)
        
        if not player_pugs:
            if not is_admin(ctx):
                await ctx.send("❌ You weren't in any recent unfinished PUGs! Use `.splitwin <pug#>` to specify which PUG.")
                return
            
            # Admin can split on any PUG - find most recent unfinished
            for p in recent_pugs:
                if not p.get('winner') and p.get('status') != 'killed':
                    pug = p
                    break
            
            if not pug:
                await ctx.send("❌ No recent unfinished PUGs found!")
                return
        else:
            pug = player_pugs[0]
    
    # Start voting
    all_players = pug['red_team'] + pug['blue_team']
    votes_needed = len(all_players) // 2 + 1
    
    # Create vote message
    vote_msg = await ctx.send(
        f"🤝 **Split Win Vote for PUG #{pug['number']}**\n"
        f"Declaring this match a 1-1 split (incomplete BO3).\n"
        f"Both teams will receive small ELO changes based on a draw.\n\n"
        f"Players in this PUG, react with ✅ to vote for split win.\n"
        f"Requires **{votes_needed}/{len(all_players)}** votes to pass.\n"
        f"Vote ends in 15 minutes or when majority is reached."
    )
    
    await vote_msg.add_reaction("✅")
    await vote_msg.add_reaction("❌")
    
    # Monitor voting
    start_time = asyncio.get_event_loop().time()
    timeout = 900  # 15 minutes
    
    try:
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            remaining = timeout - elapsed
            
            if remaining <= 0:
                break
            
            # Check current vote count
            vote_msg = await ctx.channel.fetch_message(vote_msg.id)
            yes_votes = 0
            
            for reaction in vote_msg.reactions:
                if str(reaction.emoji) == "✅":
                    users = [user async for user in reaction.users()]
                    yes_votes = sum(1 for user in users if not user.bot and str(user.id) in all_players)
                    break
            
            # If majority reached, process immediately
            if yes_votes >= votes_needed:
                await process_split_win(ctx, pug)
                return
            
            await asyncio.sleep(min(5, remaining))
        
        # Timeout reached, count final votes
        vote_msg = await ctx.channel.fetch_message(vote_msg.id)
        yes_votes = 0
        
        for reaction in vote_msg.reactions:
            if str(reaction.emoji) == "✅":
                users = [user async for user in reaction.users()]
                yes_votes = sum(1 for user in users if not user.bot and str(user.id) in all_players)
                break
        
        if yes_votes >= votes_needed:
            await process_split_win(ctx, pug)
        else:
            await ctx.send(f"❌ **Vote failed.** Only {yes_votes}/{votes_needed} votes received. PUG #{pug['number']} remains open.")
    
    except Exception as e:
        await ctx.send(f"⚠️ Error during voting: {e}")

async def process_split_win(ctx, pug):
    """Process split win (draw) and update ELO for both teams"""
    # Mark as split in database
    db_manager.update_pug_winner(pug['pug_id'], 'split')
    
    # Get server_id
    server_id = pug.get('server_id', str(ctx.guild.id))
    
    # Get teams
    red_team = pug['red_team']
    blue_team = pug['blue_team']
    
    # For a split, we DON'T update wins/losses (it's a draw)
    # But we DO update total_pugs for both teams
    for uid in red_team + blue_team:
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE players 
            SET total_pugs = total_pugs + 1
            WHERE discord_id = ? AND server_id = ?
        ''', (uid, server_id))
        conn.commit()
        conn.close()
    
    # Calculate ELO changes for a DRAW (score = 0.5 for both teams)
    K_FACTOR = 32
    avg_red_elo = pug['avg_red_elo']
    avg_blue_elo = pug['avg_blue_elo']
    
    # Calculate expected scores
    expected_red = 1 / (1 + 10 ** ((avg_blue_elo - avg_red_elo) / 400))
    expected_blue = 1 - expected_red
    
    # Store ELO changes
    elo_changes = {}
    
    # Update ELO for red team (score = 0.5 for draw)
    for uid in red_team:
        player = db_manager.get_player(uid, server_id)
        old_elo = player['elo']
        new_elo = player['elo'] + K_FACTOR * (0.5 - expected_red)
        db_manager.update_player_elo(uid, server_id, new_elo)
        elo_changes[uid] = {'old': old_elo, 'new': new_elo, 'change': new_elo - old_elo}
    
    # Update ELO for blue team (score = 0.5 for draw)
    for uid in blue_team:
        player = db_manager.get_player(uid, server_id)
        old_elo = player['elo']
        new_elo = player['elo'] + K_FACTOR * (0.5 - expected_blue)
        db_manager.update_player_elo(uid, server_id, new_elo)
        elo_changes[uid] = {'old': old_elo, 'new': new_elo, 'change': new_elo - old_elo}
    
    # Show results
    embed = discord.Embed(
        title=f"🤝 PUG #{pug['number']} Split Result",
        description=f"**Match ended 1-1 (Incomplete BO3)**\nBoth teams receive ELO for a draw.",
        color=discord.Color.purple()
    )
    
    # Show ELO changes for red team
    red_changes = []
    for uid in red_team:
        change = elo_changes[uid]
        player = db_manager.get_player(uid, server_id)
        rank = get_elo_rank(player['elo'])
        red_changes.append(f"<@{uid}>: {change['old']:.0f} → **{change['new']:.0f}** ({change['change']:+.0f}) - {rank}")
    
    # Show ELO changes for blue team
    blue_changes = []
    for uid in blue_team:
        change = elo_changes[uid]
        player = db_manager.get_player(uid, server_id)
        rank = get_elo_rank(player['elo'])
        blue_changes.append(f"<@{uid}>: {change['old']:.0f} → **{change['new']:.0f}** ({change['change']:+.0f}) - {rank}")
    
    embed.add_field(name="🔴 Red Team", value="\n".join(red_changes), inline=False)
    embed.add_field(name="🔵 Blue Team", value="\n".join(blue_changes), inline=False)
    
    await ctx.send(embed=embed)
    
    # Auto-update leaderboard after ELO changes
    try:
        print(f"🔄 Calling update_leaderboard from process_split_win for guild {ctx.guild.id}")
        await update_leaderboard(ctx.guild.id)
        print(f"✅ update_leaderboard completed from process_split_win")
    except Exception as e:
        print(f"❌ Error calling update_leaderboard from process_split_win: {e}")
        import traceback
        traceback.print_exc()

async def process_winner(ctx, pug, team, admin_override=False):
    """Process winner and update stats/ELO"""
    # Update winner in database
    db_manager.update_pug_winner(pug['pug_id'], team)
    
    # Get server_id from pug or ctx
    server_id = pug.get('server_id', str(ctx.guild.id))
    
    # Get teams
    winner_team = pug['red_team'] if team == 'red' else pug['blue_team']
    loser_team = pug['blue_team'] if team == 'red' else pug['red_team']
    
    # Update wins/losses
    for uid in winner_team:
        db_manager.update_player_stats(uid, server_id, won=True)
    
    for uid in loser_team:
        db_manager.update_player_stats(uid, server_id, won=False)
    
    # Update ELO
    K_FACTOR = 32
    avg_red_elo = pug['avg_red_elo']
    avg_blue_elo = pug['avg_blue_elo']
    
    # Calculate expected scores
    expected_red = 1 / (1 + 10 ** ((avg_blue_elo - avg_red_elo) / 400))
    expected_blue = 1 - expected_red
    
    # Store ELO changes
    elo_changes = {}
    
    # Update ELO for winners
    for uid in winner_team:
        player = db_manager.get_player(uid, server_id)
        old_elo = player['elo']
        if team == 'red':
            new_elo = player['elo'] + K_FACTOR * (1 - expected_red)
        else:
            new_elo = player['elo'] + K_FACTOR * (1 - expected_blue)
        db_manager.update_player_elo(uid, server_id, new_elo)
        elo_changes[uid] = {'old': old_elo, 'new': new_elo, 'change': new_elo - old_elo}
    
    # Update ELO for losers
    for uid in loser_team:
        player = db_manager.get_player(uid, server_id)
        old_elo = player['elo']
        if team == 'red':
            new_elo = player['elo'] + K_FACTOR * (0 - expected_blue)
        else:
            new_elo = player['elo'] + K_FACTOR * (0 - expected_red)
        db_manager.update_player_elo(uid, server_id, new_elo)
        elo_changes[uid] = {'old': old_elo, 'new': new_elo, 'change': new_elo - old_elo}
    
    # Show results
    embed = discord.Embed(
        title=f"🏆 PUG #{pug['number']} Result",
        description=f"**{'🔴 RED' if team == 'red' else '🔵 BLUE'} TEAM WINS!**" + (" ⚡ (Admin Override)" if admin_override else ""),
        color=discord.Color.red() if team == 'red' else discord.Color.blue()
    )
    
    # Show ELO changes for winners
    winner_changes = []
    for uid in winner_team:
        change = elo_changes[uid]
        player = db_manager.get_player(uid, server_id)
        rank = get_elo_rank(player['elo'])
        winner_changes.append(f"<@{uid}>: {change['old']:.0f} → **{change['new']:.0f}** ({change['change']:+.0f}) - {rank}")
    
    # Show ELO changes for losers
    loser_changes = []
    for uid in loser_team:
        change = elo_changes[uid]
        player = db_manager.get_player(uid, server_id)
        rank = get_elo_rank(player['elo'])
        loser_changes.append(f"<@{uid}>: {change['old']:.0f} → **{change['new']:.0f}** ({change['change']:+.0f}) - {rank}")
    
    if team == 'red':
        embed.add_field(name="🔴 Red Team (Winners)", value="\n".join(winner_changes), inline=False)
        embed.add_field(name="🔵 Blue Team (Losers)", value="\n".join(loser_changes), inline=False)
    else:
        embed.add_field(name="🔵 Blue Team (Winners)", value="\n".join(winner_changes), inline=False)
        embed.add_field(name="🔴 Red Team (Losers)", value="\n".join(loser_changes), inline=False)
    
    await ctx.send(embed=embed)
    
    # Auto-update leaderboard after ELO changes
    try:
        print(f"🔄 Calling update_leaderboard from process_winner for guild {ctx.guild.id}")
        await update_leaderboard(ctx.guild.id)
        print(f"✅ update_leaderboard completed from process_winner")
    except Exception as e:
        print(f"❌ Error calling update_leaderboard from process_winner: {e}")
        import traceback
        traceback.print_exc()

async def undo_winner_logic(ctx, pug):
    """Undo a PUG winner - reverses ELO and stats (shared logic)"""
    server_id = pug.get('server_id', str(ctx.guild.id))
    winning_team_name = pug['winner']
    winner_team = pug['red_team'] if winning_team_name == 'red' else pug['blue_team']
    loser_team = pug['blue_team'] if winning_team_name == 'red' else pug['red_team']
    
    # Calculate what the ELO changes were
    K_FACTOR = 32
    avg_red_elo = pug['avg_red_elo']
    avg_blue_elo = pug['avg_blue_elo']
    
    expected_red = 1 / (1 + 10 ** ((avg_blue_elo - avg_red_elo) / 400))
    expected_blue = 1 - expected_red
    
    # Reverse ELO changes for winners
    for uid in winner_team:
        player = db_manager.get_player(uid, server_id)
        current_elo = player['elo']
        
        # Calculate what the change was
        if winning_team_name == 'red':
            elo_change = K_FACTOR * (1 - expected_red)
        else:
            elo_change = K_FACTOR * (1 - expected_blue)
        
        # Reverse it
        new_elo = current_elo - elo_change
        db_manager.update_player_elo(uid, server_id, new_elo)
        
        # Reverse win counter
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE players 
            SET wins = wins - 1, total_pugs = total_pugs - 1
            WHERE discord_id = ? AND server_id = ?
        """, (uid, server_id))
        conn.commit()
        conn.close()
    
    # Reverse ELO changes for losers
    for uid in loser_team:
        player = db_manager.get_player(uid, server_id)
        current_elo = player['elo']
        
        # Calculate what the change was
        if winning_team_name == 'red':
            elo_change = K_FACTOR * (0 - expected_blue)
        else:
            elo_change = K_FACTOR * (0 - expected_red)
        
        # Reverse it
        new_elo = current_elo - elo_change
        db_manager.update_player_elo(uid, server_id, new_elo)
        
        # Reverse loss counter
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE players 
            SET losses = losses - 1, total_pugs = total_pugs - 1
            WHERE discord_id = ? AND server_id = ?
        """, (uid, server_id))
        conn.commit()
        conn.close()
    
    # Reset winner to NULL
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE pugs SET winner = NULL WHERE pug_id = ?", (pug['pug_id'],))
    conn.commit()
    conn.close()

@bot.command(name='undowinner')
async def undo_winner(ctx, pug_number: int = None):
    """Undo a PUG winner declaration - reverses ELO and stats (Admin only)
    
    Usage: .undowinner or .undowinner 5
    """
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    if pug_number is None:
        # Use most recent PUG with a winner
        recent_pugs = db_manager.get_recent_pugs(10)
        pug = None
        for p in recent_pugs:
            if p.get('winner') and p.get('status') != 'killed':
                pug = p
                break
        
        if not pug:
            await ctx.send("❌ No recent PUGs with winners found!")
            return
    else:
        # Find specific PUG
        recent_pugs = db_manager.get_recent_pugs(100)
        pug = None
        for p in recent_pugs:
            if p['number'] == pug_number:
                pug = p
                break
        
        if not pug:
            await ctx.send(f"❌ Could not find PUG #{pug_number}!")
            return
        
        if not pug.get('winner'):
            await ctx.send(f"❌ PUG #{pug['number']} doesn't have a winner set!")
            return
        
        if pug.get('status') == 'killed':
            await ctx.send(f"❌ PUG #{pug['number']} is already killed/dead!")
            return
    
    # Call shared undo logic
    await undo_winner_logic(ctx, pug)
    
    # Show what was reversed
    server_id = pug.get('server_id', str(ctx.guild.id))
    winning_team_name = pug['winner']
    
    embed = discord.Embed(
        title=f"↩️ PUG #{pug['number']} Winner Undone",
        description=f"Reversed {'🔴 RED' if winning_team_name == 'red' else '🔵 BLUE'} team victory",
        color=discord.Color.orange()
    )
    
    embed.add_field(
        name="Stats Updated",
        value=f"• Winners: -1 win, -1 total PUG\n• Losers: -1 loss, -1 total PUG",
        inline=False
    )
    
    embed.add_field(
        name="Next Steps",
        value=f"Players can now vote with `.winner red` or `.winner blue`\n"
              f"Or use `.deadpug {pug['number']}` to mark it as unplayed",
        inline=False
    )
    
    await ctx.send(embed=embed)
    
    # Auto-update leaderboard after ELO changes
    await update_leaderboard(ctx.guild.id)

@bot.command(name='setwinner')
async def set_winner_admin(ctx, pug_id: int, team: str):
    """Manually set/override winner for any PUG (Admin only)"""
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    team = team.lower()
    if team not in ['red', 'blue']:
        await ctx.send("❌ Use `.setwinner <pug_id> red` or `.setwinner <pug_id> blue`")
        return
    
    # Find the PUG
    recent_pugs = db_manager.get_recent_pugs(100)
    pug = None
    for p in recent_pugs:
        if p['number'] == pug_id:
            pug = p
            break
    
    if not pug:
        await ctx.send(f"❌ Could not find PUG #{pug_id}!")
        return
    
    if pug.get('status') == 'killed':
        await ctx.send(f"❌ Cannot set winner for killed PUG #{pug_id}!")
        return
    
    # Check if already has same winner
    if pug.get('winner') == team:
        await ctx.send(f"ℹ️ PUG #{pug_id} already has {team.upper()} team as winner!")
        return
    
    # If PUG already has a winner (different team), undo it first
    if pug.get('winner') and pug.get('winner') != team:
        old_winner = pug.get('winner')
        await ctx.send(f"⚠️ PUG #{pug_id} already has a winner ({old_winner.upper()} team). Undoing previous result...")
        
        # Undo the old winner using undowinner logic
        await undo_winner_logic(ctx, pug)
        
        # Refresh PUG data after undo
        recent_pugs = db_manager.get_recent_pugs(100)
        for p in recent_pugs:
            if p['number'] == pug_id:
                pug = p
                break
    
    # Process the new winner (this will update stats/ELO)
    await process_winner(ctx, pug, team, admin_override=True)
    await ctx.send(f"⚡ **Admin override - Set PUG #{pug_id} winner to {team.upper()} team**")

@bot.command(name='register')
async def register(ctx):
    """Register yourself for PUG tracking - Admins will set your starting ELO"""
    try:
        # Get user's Discord username and display name
        discord_username = ctx.author.name  # Discord username (e.g., "user123")
        display_name = ctx.author.display_name  # Server nickname or global display name
        
        # Check if player already exists
        player_data = db_manager.get_player(ctx.author.id, str(ctx.guild.id))
        
        if player_data:
            # Player already registered
            embed = discord.Embed(
                title="✅ Already Registered",
                description=f"{ctx.author.mention}, you are already registered for PUG tracking!",
                color=discord.Color.green()
            )
            embed.add_field(name="Discord Username", value=f"@{discord_username}", inline=True)
            embed.add_field(name="Display Name", value=display_name, inline=True)
            embed.add_field(name="Discord ID", value=ctx.author.id, inline=True)
            embed.add_field(name="Current ELO", value=f"{player_data['elo']:.0f}", inline=True)
            embed.add_field(name="Total PUGs", value=player_data['total_pugs'], inline=True)
            embed.add_field(name="Win/Loss", value=f"{player_data['wins']}W-{player_data['losses']}L", inline=True)
            
            await ctx.send(embed=embed)
        else:
            # New player - register them
            player_data = db_manager.register_player(
                ctx.author.id, 
                str(ctx.guild.id),
                discord_username,
                display_name
            )
            
            # User confirmation embed
            embed = discord.Embed(
                title="🎮 Registration Complete!",
                description=f"Welcome {ctx.author.mention}! You are now registered for PUG tracking.",
                color=discord.Color.blue()
            )
            embed.add_field(name="Discord Username", value=f"@{discord_username}", inline=True)
            embed.add_field(name="Display Name", value=display_name, inline=True)
            embed.add_field(name="Discord ID", value=ctx.author.id, inline=True)
            embed.add_field(name="Temporary ELO", value="1000 (pending admin review)", inline=True)
            embed.add_field(name="Server", value=ctx.guild.name, inline=True)
            embed.add_field(name="⏳ Next Step", value="An admin will set your starting ELO based on your skill level", inline=False)
            
            await ctx.send(embed=embed)
            
            # Get admin role mentions
            admin_roles = []
            for role in ctx.guild.roles:
                if role.name.lower() in ['admins', 'admin', 'administrator', 'pug admin']:
                    admin_roles.append(role)
            
            # Build admin mention string
            if admin_roles:
                admin_mentions = " ".join([role.mention for role in admin_roles])
            else:
                # Fallback: mention users with admin permissions
                admins = [member for member in ctx.guild.members if member.guild_permissions.administrator]
                if admins:
                    admin_mentions = " ".join([admin.mention for admin in admins[:5]])  # Limit to 5
                else:
                    admin_mentions = "@Admins"
            
            # Admin notification embed (no player mention, just their name)
            admin_embed = discord.Embed(
                title="🆕 New Player Registration",
                description=f"{admin_mentions} - A new player has registered and needs their ELO set!",
                color=discord.Color.orange()
            )
            admin_embed.add_field(name="Player", value=f"{display_name}", inline=False)
            admin_embed.add_field(name="Discord Username", value=f"@{discord_username}", inline=True)
            admin_embed.add_field(name="Discord ID", value=ctx.author.id, inline=True)
            admin_embed.add_field(name="Current ELO", value="1000 (temporary)", inline=True)
            admin_embed.add_field(
                name="📋 Action Required", 
                value=f"Use `.setelo {display_name} <elo>` to set their starting ELO\nExample: `.setelo {display_name} 1200`",
                inline=False
            )
            
            await ctx.send(embed=admin_embed)
            
    except Exception as e:
        await ctx.send(f"❌ Registration error: {e}")
        import traceback
        traceback.print_exc()
        import traceback
        traceback.print_exc()

@bot.command(name='mystats')
async def my_stats(ctx):
    """View your PUG statistics"""
    player_data = db_manager.get_player(ctx.author.id, str(ctx.guild.id))
    
    total = player_data['total_pugs']
    wins = player_data['wins']
    losses = player_data['losses']
    elo = player_data['elo']
    rank = get_elo_rank(elo)
    # Win rate based on actual games played (wins + losses), not total_pugs
    actual_games = wins + losses
    win_rate = (wins / actual_games * 100) if actual_games > 0 else 0
    
    # Get leaderboard position
    position, total_players = get_leaderboard_position(ctx.author.id, str(ctx.guild.id))
    
    # Find player's most recent PUG to show ELO change
    recent_pugs = db_manager.get_recent_pugs(20)
    last_elo_change = None
    
    for pug in recent_pugs:
        if pug.get('winner'):  # Only check PUGs with results
            player_id = str(ctx.author.id)
            if player_id in pug['red_team'] or player_id in pug['blue_team']:
                # Calculate what the ELO change was
                K_FACTOR = 32
                expected_red = 1 / (1 + 10 ** ((pug['avg_blue_elo'] - pug['avg_red_elo']) / 400))
                expected_blue = 1 - expected_red
                
                # Determine if player won
                won = (player_id in pug['red_team'] and pug['winner'] == 'red') or \
                      (player_id in pug['blue_team'] and pug['winner'] == 'blue')
                
                # Calculate change
                if pug['winner'] == 'red':
                    if player_id in pug['red_team']:
                        last_elo_change = K_FACTOR * (1 - expected_red)
                    else:
                        last_elo_change = K_FACTOR * (0 - expected_blue)
                else:  # blue won
                    if player_id in pug['blue_team']:
                        last_elo_change = K_FACTOR * (1 - expected_blue)
                    else:
                        last_elo_change = K_FACTOR * (0 - expected_red)
                break
    
    embed = discord.Embed(
        title=f"📊 Statistics for {ctx.author.display_name}",
        color=discord.Color.gold()
    )
    
    embed.add_field(name="Total PUGs", value=total, inline=True)
    embed.add_field(name="Wins", value=wins, inline=True)
    embed.add_field(name="Losses", value=losses, inline=True)
    embed.add_field(name="Win Rate", value=f"{win_rate:.1f}%", inline=True)
    
    # Show ELO with recent change
    if last_elo_change is not None:
        elo_display = f"{elo:.0f} ({last_elo_change:+.0f})"
    else:
        elo_display = f"{elo:.0f}"
    
    peak_elo = player_data.get('peak_elo')
    if peak_elo is None:
        peak_elo = elo
    
    # Calculate net ELO over last 10 PUGs
    recent_pugs_10 = db_manager.get_recent_pugs(100)  # Get more to find player's 10
    player_pugs = [p for p in recent_pugs_10 if (str(ctx.author.id) in p['red_team'] or str(ctx.author.id) in p['blue_team']) and p.get('winner')]
    player_pugs = player_pugs[:10]  # Take first 10
    
    net_elo_10 = 0
    if len(player_pugs) > 0:
        K_FACTOR = 32
        for pug in player_pugs:
            expected_red = 1 / (1 + 10 ** ((pug['avg_blue_elo'] - pug['avg_red_elo']) / 400))
            expected_blue = 1 - expected_red
            
            player_id = str(ctx.author.id)
            if pug['winner'] == 'red':
                if player_id in pug['red_team']:
                    net_elo_10 += K_FACTOR * (1 - expected_red)
                else:
                    net_elo_10 += K_FACTOR * (0 - expected_blue)
            else:  # blue won
                if player_id in pug['blue_team']:
                    net_elo_10 += K_FACTOR * (1 - expected_blue)
                else:
                    net_elo_10 += K_FACTOR * (0 - expected_red)
    
    net_elo_display = f"{net_elo_10:+.0f}" if net_elo_10 != 0 else "0"
    
    embed.add_field(name="ELO", value=elo_display, inline=True)
    embed.add_field(name="Peak ELO", value=f"{peak_elo:.0f}", inline=True)
    embed.add_field(name="Rank", value=rank, inline=True)
    embed.add_field(name="Last 10 PUGs", value=f"{net_elo_display} ELO", inline=True)
    
    # Add streak
    streak = player_data.get('current_streak', 0)
    if streak > 0:
        streak_display = f"🔥 {streak}W"
    elif streak < 0:
        streak_display = f"❄️ {abs(streak)}L"
    else:
        streak_display = "—"
    embed.add_field(name="Streak", value=streak_display, inline=True)
    
    # Add leaderboard position
    if position:
        embed.add_field(name="Leaderboard", value=f"#{position} of {total_players}", inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='topelo')
async def top_elo(ctx):
    """Show top 10 players by ELO for this server (excludes simulation players and 0-0 players)"""
    players = db_manager.get_all_players(str(ctx.guild.id))
    
    # Filter out simulation players AND players with 0 pugs (0-0 record)
    active_players = []
    for p in players:
        try:
            discord_id_int = int(p['discord_id'])
            # Exclude simulation players (1000-1999) AND players with 0 pugs
            if not (1000 <= discord_id_int <= 1999) and p['total_pugs'] > 0:
                active_players.append(p)
        except ValueError:
            # If discord_id is not numeric, include them if they have pugs
            if p['total_pugs'] > 0:
                active_players.append(p)
    
    if not active_players:
        await ctx.send("📊 No players with games played found on this server!")
        return
    
    # Sort by ELO (highest first) - ensure float comparison
    active_players.sort(key=lambda x: float(x['elo']), reverse=True)
    
    embed = discord.Embed(title="🏆 Top 10 Players by ELO", color=discord.Color.gold())
    
    for i, player in enumerate(active_players[:10]):
        try:
            user = await bot.fetch_user(int(player['discord_id']))
            name = user.display_name
        except:
            name = f"User_{player['discord_id']}"
        
        rank = get_elo_rank(player['elo'])
        stats = f"ELO: {player['elo']:.0f} ({rank} rank) | {player['wins']}W-{player['losses']}L"
        
        embed.add_field(
            name=f"{i+1}. {name}",
            value=stats,
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='top10')
async def top_10(ctx):
    """Show top 10 most active players for this server (excludes simulation players)"""
    players = db_manager.get_all_players(str(ctx.guild.id))
    
    # Filter out simulation players (IDs 1000-1999) and players with at least 1 pug
    active_players = [p for p in players if p['total_pugs'] > 0 and not (1000 <= int(p['discord_id']) <= 1999)]
    
    if not active_players:
        await ctx.send("📊 No players have completed any PUGs yet!")
        return
    
    # Sort by total pugs
    active_players.sort(key=lambda x: x['total_pugs'], reverse=True)
    
    embed = discord.Embed(title="🎮 Top 10 Most Active Players", color=discord.Color.blue())
    
    for i, player in enumerate(active_players[:10]):
        try:
            user = await bot.fetch_user(int(player['discord_id']))
            name = user.display_name
        except:
            name = f"User_{player['discord_id']}"
        
        # Win rate based on actual games (wins + losses), not total_pugs
        actual_games = player['wins'] + player['losses']
        win_rate = (player['wins'] / actual_games * 100) if actual_games > 0 else 0
        embed.add_field(
            name=f"{i+1}. {name}",
            value=f"{player['total_pugs']} PUGs | {player['wins']}W-{player['losses']}L ({win_rate:.1f}%)",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='playerelos')
async def player_elos_dm(ctx):
    """DM a list of all registered players with their ELOs"""
    # Send immediate feedback
    processing_msg = await ctx.send("📊 Gathering player data...")
    
    players = db_manager.get_all_players(str(ctx.guild.id))
    
    # Filter out simulation players
    active_players = []
    for p in players:
        try:
            discord_id_int = int(p['discord_id'])
            if not (1000 <= discord_id_int <= 1999):
                active_players.append(p)
        except ValueError:
            active_players.append(p)
    
    if not active_players:
        await processing_msg.edit(content="📊 No players found on this server!")
        return
    
    # Sort by ELO (highest first)
    active_players.sort(key=lambda x: float(x['elo']), reverse=True)
    
    # Cache guild members to avoid repeated API calls
    guild_members = {str(member.id): member for member in ctx.guild.members}
    
    # Build all lines in one pass
    message_lines = [f"📊 **All Player ELOs ({len(active_players)} players)**\n"]
    
    for i, player in enumerate(active_players):
        discord_id = player['discord_id']
        
        # Use cached guild members (no API call!)
        if discord_id in guild_members:
            name = guild_members[discord_id].display_name
        else:
            # Use stored name from database (no API call!)
            name = player.get('display_name') or player.get('discord_name') or f"User_{discord_id}"
        
        rank = get_elo_rank(player['elo'])
        
        if player['total_pugs'] > 0:
            line = f"{i+1}. {name}: {player['elo']:.0f} ELO ({rank}) | {player['wins']}W-{player['losses']}L"
        else:
            line = f"{i+1}. {name}: {player['elo']:.0f} ELO ({rank}) | No games"
        
        message_lines.append(line)
    
    # Split into chunks (Discord has 2000 char limit per message)
    chunks = []
    current_chunk = ""
    
    for line in message_lines:
        if len(current_chunk) + len(line) + 1 > 1900:
            chunks.append(current_chunk)
            current_chunk = line + "\n"
        else:
            current_chunk += line + "\n"
    
    if current_chunk:
        chunks.append(current_chunk)
    
    # Try to DM the user
    try:
        # Send first message with header
        await ctx.author.send(chunks[0])
        
        # Send remaining chunks if any
        for chunk in chunks[1:]:
            await ctx.author.send(chunk)
        
        await processing_msg.edit(content=f"✅ Sent ELO list to your DMs! ({len(active_players)} players)")
    except discord.Forbidden:
        await processing_msg.edit(content="❌ I couldn't DM you! Please enable DMs from server members and try again.")
    except Exception as e:
        await processing_msg.edit(content=f"❌ Error sending DM: {e}")

@bot.command(name='longestwin', aliases=['beststreak'])
async def longest_win_streak(ctx):
    """Show the player with the longest winning streak (all-time)"""
    players = db_manager.get_all_players(str(ctx.guild.id))
    
    # Filter out simulation players
    active_players = []
    for p in players:
        try:
            discord_id_int = int(p['discord_id'])
            if not (1000 <= discord_id_int <= 1999):
                active_players.append(p)
        except ValueError:
            active_players.append(p)
    
    if not active_players:
        await ctx.send("📊 No players found!")
        return
    
    # Find player with highest positive streak (current_streak field tracks this)
    # But we need to check historical max, not just current
    # For now, use current_streak and get_player data
    max_streak = 0
    max_streak_player = None
    
    for player in active_players:
        # Get best_win_streak from database if it exists, otherwise use current_streak if positive
        best_streak = player.get('best_win_streak', 0)
        current_streak = player.get('current_streak', 0)
        
        # Use the best available value
        player_best = max(best_streak, current_streak if current_streak > 0 else 0)
        
        if player_best > max_streak:
            max_streak = player_best
            max_streak_player = player
    
    if not max_streak_player or max_streak == 0:
        await ctx.send("📊 No winning streaks recorded yet!")
        return
    
    # Get Discord member
    try:
        member = await ctx.guild.fetch_member(int(max_streak_player['discord_id']))
        display_name = member.display_name
    except:
        display_name = f"Player {max_streak_player['discord_id']}"
    
    embed = discord.Embed(
        title="🔥 Longest Winning Streak",
        description=f"**{display_name}** holds the record!",
        color=discord.Color.gold()
    )
    
    embed.add_field(name="Streak", value=f"{max_streak} wins in a row", inline=True)
    embed.add_field(name="Player", value=display_name, inline=True)
    embed.add_field(name="Current ELO", value=f"{max_streak_player['elo']:.0f}", inline=True)
    
    current_streak = max_streak_player.get('current_streak', 0)
    if current_streak > 0:
        embed.add_field(name="Current Streak", value=f"🔥 {current_streak}W (Active!)", inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='longestloss', aliases=['worststreak'])
async def longest_loss_streak(ctx):
    """Show the player with the longest losing streak (all-time)"""
    players = db_manager.get_all_players(str(ctx.guild.id))
    
    # Filter out simulation players
    active_players = []
    for p in players:
        try:
            discord_id_int = int(p['discord_id'])
            if not (1000 <= discord_id_int <= 1999):
                active_players.append(p)
        except ValueError:
            active_players.append(p)
    
    if not active_players:
        await ctx.send("📊 No players found!")
        return
    
    # Find player with highest loss streak (stored as negative in current_streak or best_loss_streak)
    max_loss_streak = 0
    max_loss_player = None
    
    for player in active_players:
        # Get best_loss_streak from database if it exists, otherwise use current_streak if negative
        best_loss = player.get('best_loss_streak', 0)
        current_streak = player.get('current_streak', 0)
        
        # Use the best (worst) available value
        player_worst = max(best_loss, abs(current_streak) if current_streak < 0 else 0)
        
        if player_worst > max_loss_streak:
            max_loss_streak = player_worst
            max_loss_player = player
    
    if not max_loss_player or max_loss_streak == 0:
        await ctx.send("📊 No losing streaks recorded yet!")
        return
    
    # Get Discord member
    try:
        member = await ctx.guild.fetch_member(int(max_loss_player['discord_id']))
        display_name = member.display_name
    except:
        display_name = f"Player {max_loss_player['discord_id']}"
    
    embed = discord.Embed(
        title="❄️ Longest Losing Streak",
        description=f"**{display_name}** has the unfortunate record...",
        color=discord.Color.blue()
    )
    
    embed.add_field(name="Streak", value=f"{max_loss_streak} losses in a row", inline=True)
    embed.add_field(name="Player", value=display_name, inline=True)
    embed.add_field(name="Current ELO", value=f"{max_loss_player['elo']:.0f}", inline=True)
    
    current_streak = max_loss_player.get('current_streak', 0)
    if current_streak < 0:
        embed.add_field(name="Current Streak", value=f"❄️ {abs(current_streak)}L (Active!)", inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='last')
async def last_pug(ctx, *, player_name: str = None):
    """Show the most recent PUG (or a player's last PUG)
    
    Usage:
    .last - Show most recent PUG overall
    .last @Player - Show this player's most recent PUG
    .last PlayerName - Show this player's most recent PUG
    """
    if player_name:
        # Find player's last PUG
        member, discord_id = await resolve_player(ctx, player_name)
        
        if not member:
            await ctx.send(f"❌ Could not find player '{player_name}'!")
            return
        
        # Get all recent PUGs and find ones this player was in
        recent = db_manager.get_recent_pugs(100)
        player_pugs = [p for p in recent if str(discord_id) in p['red_team'] or str(discord_id) in p['blue_team']]
        
        if not player_pugs:
            await ctx.send(f"❌ {member.display_name} hasn't played any PUGs yet!")
            return
        
        await show_pug_info(ctx, player_pugs[0], f"{member.display_name}'s Last PUG")
    else:
        # Show most recent PUG overall
        recent = db_manager.get_recent_pugs(1)
        if not recent:
            await ctx.send("No PUGs have been played!")
            return
        
        await show_pug_info(ctx, recent[0])

@bot.command(name='mylast')
async def my_last_pug(ctx):
    """Show your most recent PUG
    
    Usage: .mylast
    """
    # Get all recent PUGs and find ones this player was in
    discord_id = str(ctx.author.id)
    recent = db_manager.get_recent_pugs(100)
    player_pugs = [p for p in recent if discord_id in p['red_team'] or discord_id in p['blue_team']]
    
    if not player_pugs:
        await ctx.send(f"❌ {ctx.author.display_name}, you haven't played any PUGs yet!")
        return
    
    await show_pug_info(ctx, player_pugs[0], f"{ctx.author.display_name}'s Last PUG")

@bot.command(name='lastt')
async def last_two_pugs(ctx):
    """Show the second most recent PUG"""
    recent = db_manager.get_recent_pugs(2)
    if len(recent) < 2:
        await ctx.send("Not enough PUGs have been played!")
        return
    
    await show_pug_info(ctx, recent[1])

@bot.command(name='lasttt')
async def last_three_pugs(ctx):
    """Show the third most recent PUG"""
    recent = db_manager.get_recent_pugs(3)
    if len(recent) < 3:
        await ctx.send("Not enough PUGs have been played!")
        return
    
    await show_pug_info(ctx, recent[2])

async def show_pug_info(ctx, pug, custom_title=None):
    # Set color based on status
    if pug.get('status') == 'killed':
        color = discord.Color.dark_red()
        title = custom_title if custom_title else f"PUG #{pug['number']} (CANCELLED)"
    else:
        color = discord.Color.blue()
        title = custom_title if custom_title else f"PUG #{pug['number']}"
    
    embed = discord.Embed(title=title, color=color)
    
    # Convert timestamp to local time and format in 12-hour
    timestamp = datetime.fromisoformat(pug['timestamp'])
    # SQLite CURRENT_TIMESTAMP is UTC, convert to local
    # timestamp is already naive (no timezone), treat as UTC and convert to local
    from datetime import timezone
    timestamp_utc = timestamp.replace(tzinfo=timezone.utc)
    timestamp_local = timestamp_utc.astimezone()
    
    # Format in 12-hour format with AM/PM
    formatted_time = timestamp_local.strftime('%Y-%m-%d %I:%M:%S %p')
    
    # Calculate time since pug
    now = datetime.now(timezone.utc)
    time_diff = now - timestamp_utc
    minutes_ago = int(time_diff.total_seconds() / 60)
    
    if minutes_ago < 60:
        time_ago_str = f"{minutes_ago} minute{'s' if minutes_ago != 1 else ''} ago"
    elif minutes_ago < 1440:  # Less than 24 hours
        hours_ago = minutes_ago // 60
        time_ago_str = f"{hours_ago} hour{'s' if hours_ago != 1 else ''} ago"
    else:
        days_ago = minutes_ago // 1440
        time_ago_str = f"{days_ago} day{'s' if days_ago != 1 else ''} ago"
    
    embed.add_field(name="Date", value=f"{formatted_time} ({time_ago_str})", inline=False)
    
    # Show PUG ID
    embed.add_field(name="PUG ID", value=f"#{pug['number']}", inline=True)
    
    # Show game mode if available
    if pug.get('game_mode'):
        mode_data = db_manager.get_game_mode(pug['game_mode'])
        if mode_data:
            embed.add_field(name="Mode", value=mode_data['name'], inline=False)
    
    # Get player names - try member first, then database, then API
    server_id = pug.get('server_id', str(ctx.guild.id))
    
    red_names = []
    for uid in pug['red_team']:
        member = ctx.guild.get_member(uid)
        if member:
            name = member.display_name
        else:
            # Player left server, try database first
            try:
                player_data = db_manager.get_player(uid, server_id)
                name = player_data.get('display_name') or player_data.get('discord_name')
                
                # If database doesn't have name, try to fetch from Discord API
                if not name:
                    try:
                        user = await bot.fetch_user(uid)
                        name = user.name  # Discord username
                    except:
                        name = f"Player_{uid}"
                else:
                    # Clean up the name if it has discriminator
                    if '#' in name:
                        name = name.split('#')[0]
            except:
                name = f"Player_{uid}"
        red_names.append(name)
    
    blue_names = []
    for uid in pug['blue_team']:
        member = ctx.guild.get_member(uid)
        if member:
            name = member.display_name
        else:
            # Player left server, try database first
            try:
                player_data = db_manager.get_player(uid, server_id)
                name = player_data.get('display_name') or player_data.get('discord_name')
                
                # If database doesn't have name, try to fetch from Discord API
                if not name:
                    try:
                        user = await bot.fetch_user(uid)
                        name = user.name  # Discord username
                    except:
                        name = f"Player_{uid}"
                else:
                    # Clean up the name if it has discriminator
                    if '#' in name:
                        name = name.split('#')[0]
            except:
                name = f"Player_{uid}"
        blue_names.append(name)
    
    red_team = ", ".join(red_names)
    blue_team = ", ".join(blue_names)
    
    embed.add_field(name="🔴 Red Team", value=red_team, inline=False)
    embed.add_field(name="🔵 Blue Team", value=blue_team, inline=False)
    
    # Show ELO averages if available
    if pug.get('avg_red_elo') and pug.get('avg_blue_elo'):
        embed.add_field(name="Average ELO", 
                       value=f"Red: {pug['avg_red_elo']:.0f} | Blue: {pug['avg_blue_elo']:.0f}", 
                       inline=False)
    
    # Show tiebreaker map if available (for 4v4 PUGs)
    if pug.get('tiebreaker_map'):
        embed.add_field(name="Tiebreaker", value=pug['tiebreaker_map'], inline=False)
    
    # Show status
    if pug.get('status') == 'killed':
        embed.add_field(name="Status", value="CANCELLED - No ELO impact", inline=False)
    elif pug.get('winner'):
        winner_text = f"{pug['winner'].upper()} Team Won"
        embed.add_field(name="Result", value=winner_text, inline=False)
    else:
        embed.add_field(name="Status", value="Awaiting result", inline=False)
    
    # Add timestamp footer with current local time
    current_time = datetime.now()
    embed.set_footer(text=f"Local Time: {current_time.strftime('%I:%M:%S %p')} • {current_time.strftime('%B %d, %Y')}")
    
    await ctx.send(embed=embed)

@bot.command(name='addpugadmin')
async def add_pugadmin(ctx, *, player_name: str):
    """Add a PUG Admin (Admin role only)
    
    Usage:
    .addpugadmin @Player
    .addpugadmin PlayerName
    """
    if not is_full_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Resolve player from @mention or name
    member, discord_id = await resolve_player(ctx, player_name)
    
    if not member:
        await ctx.send(f"❌ Could not find player '{player_name}'. Use @mention or exact display name.")
        return
    
    # Add as PUG admin for this server
    db_manager.add_pug_admin(str(member.id), str(ctx.guild.id))
    await ctx.send(f"✅ {member.mention} has been added as a PUG Admin for this server!")

@bot.command(name='removepugadmin')
async def remove_pugadmin(ctx, *, player_name: str):
    """Remove a PUG Admin (Admin role only)
    
    Usage:
    .removepugadmin @Player
    .removepugadmin PlayerName
    """
    if not is_full_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Resolve player from @mention or name
    member, discord_id = await resolve_player(ctx, player_name)
    
    if not member:
        await ctx.send(f"❌ Could not find player '{player_name}'. Use @mention or exact display name.")
        return
    
    # Check if they are a PUG admin on this server
    if not db_manager.is_pug_admin(str(member.id), str(ctx.guild.id)):
        await ctx.send(f"❌ {member.mention} is not a PUG Admin on this server!")
        return
    
    # Remove PUG admin from this server
    db_manager.remove_pug_admin(str(member.id), str(ctx.guild.id))
    await ctx.send(f"✅ {member.mention} has been removed as a PUG Admin from this server!")

@bot.command(name='showpugadmins')
async def show_pug_admins(ctx):
    """Show all PUG Admins for this server (Admin only)"""
    if not is_full_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Get all PUG admins for this server
    pug_admin_ids = db_manager.get_pug_admins(str(ctx.guild.id))
    
    if not pug_admin_ids:
        await ctx.send("📋 There are currently no PUG Admins on this server.")
        return
    
    # Build list of PUG admins
    admin_list = []
    for admin_id in pug_admin_ids:
        try:
            member = await ctx.guild.fetch_member(int(admin_id))
            admin_list.append(f"• {member.mention} ({member.display_name})")
        except:
            admin_list.append(f"• User ID: {admin_id} (Not in server)")
    
    embed = discord.Embed(
        title=f"👑 PUG Admins - {ctx.guild.name}",
        description="\n".join(admin_list),
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Total PUG Admins on this server: {len(pug_admin_ids)}")
    
    await ctx.send(embed=embed)

@bot.command(name='status')
async def bot_status(ctx):
    """Show bot status and statistics (Admin only)"""
    if not is_full_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Calculate uptime
    uptime = datetime.now() - bot_start_time
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    uptime_str = []
    if days > 0:
        uptime_str.append(f"{days} day{'s' if days != 1 else ''}")
    if hours > 0:
        uptime_str.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        uptime_str.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    
    uptime_text = ", ".join(uptime_str) if uptime_str else "less than a minute"
    
    # Get total players and PUGs for THIS SERVER
    server_players = db_manager.get_all_players(str(ctx.guild.id))
    total_players_count = len(server_players)
    all_pugs = db_manager.get_recent_pugs(10000)  # Get all PUGs
    total_pugs = len(all_pugs)
    
    # Count active queues
    active_queues = sum(1 for q in queues.values() if len(q.queue) > 0)
    
    # Get game modes (returns dict with mode_name as key)
    game_modes = db_manager.get_all_game_modes()
    mode_list = []
    for mode_name, mode_data in game_modes.items():
        # team_size is total players, not per team
        mode_total_players = mode_data['team_size']
        players_per_team = mode_total_players // 2
        mode_list.append(f"{mode_data['name']} ({players_per_team}v{players_per_team}, {mode_total_players} total)")
    modes_text = "\n".join(mode_list) if mode_list else "None"
    
    # Check simulation mode and autopick for default queue
    default_queue = get_queue(ctx.channel, 'default')
    sim_mode_status = "✅ Enabled" if default_queue.simulation_mode else "❌ Disabled"
    autopick_status = "✅ Enabled" if default_queue.autopick_mode else "❌ Disabled"
    
    # Check UT2K4 scraping
    scraping_enabled = db_manager.is_scraping_enabled()
    scraping_status = "✅ Enabled" if scraping_enabled else "❌ Disabled"
    
    # Get PUG admins for this server
    pug_admins = db_manager.get_pug_admins(str(ctx.guild.id))
    pug_admin_count = len(pug_admins)
    
    embed = discord.Embed(title="📊 Bot Status & Statistics", color=discord.Color.blue())
    
    # System Info
    embed.add_field(name="⏱️ Uptime", value=uptime_text, inline=True)
    embed.add_field(name="🎮 Active Queues", value=active_queues, inline=True)
    embed.add_field(name="👥 Total Players", value=total_players_count, inline=True)
    
    # Statistics
    embed.add_field(name="📈 Total PUGs Played", value=total_pugs, inline=True)
    embed.add_field(name="👑 PUG Admins", value=pug_admin_count, inline=True)
    embed.add_field(name="🎯 Game Modes", value=len(game_modes), inline=True)
    
    # Settings
    embed.add_field(name="🔧 Simulation Mode", value=sim_mode_status, inline=True)
    embed.add_field(name="🤖 Autopick (Default)", value=autopick_status, inline=True)
    embed.add_field(name="📡 Stats Scraping", value=scraping_status, inline=True)
    
    # Game Modes List
    embed.add_field(name="🎮 Available Game Modes", value=modes_text, inline=False)
    
    # Add timestamp footer with server time and bot time
    current_time = datetime.now()
    embed.set_footer(text=f"Server Time: {current_time.strftime('%I:%M:%S %p')} • {current_time.strftime('%A, %B %d, %Y')}")
    
    await ctx.send(embed=embed)

@bot.command(name='undoplayerpugs')
async def undo_player_pugs(ctx):
    """Revert all players' total_pugs to their actual wins+losses count (Admin only)
    
    This recalculates total_pugs from the actual wins and losses, undoing any imports.
    Use this if there was an issue with the CSV import.
    """
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Confirmation prompt
    confirm_msg = await ctx.send(
        "⚠️ **WARNING:** This will reset ALL players' total_pugs to match their actual win+loss counts.\n"
        "Any imported historical data will be lost.\n\n"
        "React with ✅ to confirm or ❌ to cancel."
    )
    
    await confirm_msg.add_reaction("✅")
    await confirm_msg.add_reaction("❌")
    
    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == confirm_msg.id
    
    try:
        reaction, user = await bot.wait_for('reaction_add', timeout=30.0, check=check)
        
        if str(reaction.emoji) == "❌":
            await ctx.send("❌ Undo cancelled.")
            return
        
        # User confirmed with ✅, proceed with undo
        server_id = str(ctx.guild.id)
        
        # Get all players for this server
        all_players = db_manager.get_all_players(server_id)
        
        if not all_players:
            await ctx.send("📊 No players found on this server!")
            return
        
        # Reset each player's total_pugs to wins + losses
        updated = 0
        errors = []
        
        for player in all_players:
            discord_id = player['discord_id']
            wins = player['wins']
            losses = player['losses']
            actual_total = wins + losses
            current_total = player['total_pugs']
            
            # Only update if different
            if current_total != actual_total:
                success = db_manager.update_player_total_pugs(discord_id, server_id, actual_total)
                if success:
                    updated += 1
                else:
                    errors.append(f"Failed to update player {discord_id}")
        
        # Build response
        embed = discord.Embed(
            title="🔄 PUG Count Reset Complete",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="👥 Total Players", value=len(all_players), inline=True)
        embed.add_field(name="✅ Updated", value=updated, inline=True)
        embed.add_field(name="⚠️ Errors", value=len(errors), inline=True)
        
        if errors:
            embed.add_field(name="Error Details", value="\n".join(errors[:10]), inline=False)
        
        embed.set_footer(text="All players' total_pugs now match their wins + losses")
        
        await ctx.send(embed=embed)
        
    except asyncio.TimeoutError:
        await ctx.send("❌ Confirmation timed out. Undo cancelled.")

@bot.command(name='exportstats')
async def export_stats(ctx):
    """Export player stats as CSV for this server (Admin only)"""
    if not is_full_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Get players for this server only
    players = db_manager.get_all_players(str(ctx.guild.id))
    
    if not players:
        await ctx.send("❌ No player data to export for this server!")
        return
    
    # Create CSV content in memory
    import io
    csv_buffer = io.StringIO()
    csv_buffer.write("Discord ID,Display Name,ELO,Peak ELO,Total PUGs,Wins,Losses,Win Rate,Current Streak\n")
    
    for player in players:
        discord_id = player['discord_id']
        try:
            member = await ctx.guild.fetch_member(int(discord_id))
            display_name = member.display_name
        except:
            display_name = f"User {discord_id}"
        
        elo = player['elo']
        peak_elo = player.get('peak_elo', elo)
        total = player['total_pugs']
        wins = player['wins']
        losses = player['losses']
        # Win rate based on actual games (wins + losses), not total_pugs
        actual_games = wins + losses
        win_rate = (wins / actual_games * 100) if actual_games > 0 else 0
        streak = player.get('current_streak', 0)
        
        # Escape display name for CSV (in case it has commas)
        display_name_escaped = f'"{display_name}"' if ',' in display_name else display_name
        
        csv_buffer.write(f"{discord_id},{display_name_escaped},{elo:.0f},{peak_elo:.0f},{total},{wins},{losses},{win_rate:.1f}%,{streak}\n")
    
    # Create filename
    filename = f"pug_stats_{ctx.guild.name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    # Convert StringIO to BytesIO for Discord
    csv_buffer.seek(0)
    file_bytes = io.BytesIO(csv_buffer.getvalue().encode('utf-8'))
    
    try:
        # Send file via DM
        await ctx.author.send(
            f"📊 Player statistics export for **{ctx.guild.name}**\n"
            f"Total players: {len(players)}\n"
            f"Exported: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}", 
            file=discord.File(file_bytes, filename)
        )
        await ctx.send(f"✅ {ctx.author.mention}, I've sent the export to your DMs!")
    except discord.Forbidden:
        # DMs disabled, send in channel
        file_bytes.seek(0)  # Reset buffer
        await ctx.send(f"⚠️ I couldn't DM you. Sending here instead:")
        await ctx.send(
            f"📊 Player statistics export for **{ctx.guild.name}**", 
            file=discord.File(file_bytes, filename)
        )
    except Exception as e:
        await ctx.send(f"❌ Error sending file: {str(e)}")

@bot.command(name='importelos')
async def import_elos(ctx):
    """Import ELO updates from CSV (Admin only - must be used in server channel)
    
    Usage: Use this command in #tampro and attach a CSV file
    CSV Format: discord_id,elo OR display_name,elo
    Example:
    123456789,1200
    PlayerName,850
    """
    if not is_full_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Must be used in a server channel, not DM
    if not ctx.guild:
        await ctx.send("❌ This command must be used in a server channel (like #tampro), not in DMs!")
        return
    
    # Check if message has attachment
    if not ctx.message.attachments:
        await ctx.send("""
❌ No CSV file attached!

**Usage:** In #tampro, use `.importelos` and attach a CSV file

**CSV Format (supports 2 formats):**

**Format 1: Discord ID + ELO**
```
123456789,1200
987654321,850
556677889,1050
```

**Format 2: Display Name + ELO**
```
PlayerOne,1200
PlayerTwo,850
ThirdPlayer,1050
```

**Format 3: Exported CSV (with headers)**
```
Discord ID,Display Name,ELO,Total PUGs,Wins,Losses,Win Rate
123456789,PlayerOne,1200,10,8,2,80.0%
```

**Steps:**
1. Export current ELOs: `.exportstats`
2. Edit the CSV file with new ELOs (column 3)
3. In #tampro: `.importelos` + attach edited CSV
4. Type CONFIRM to apply changes
        """)
        return
    
    attachment = ctx.message.attachments[0]
    
    # Check if it's a CSV file
    if not attachment.filename.endswith('.csv'):
        await ctx.send("❌ File must be a CSV (.csv extension)")
        return
    
    try:
        # Download and parse CSV
        import io
        file_content = await attachment.read()
        csv_text = file_content.decode('utf-8')
        
        elo_updates = []
        errors = []
        line_num = 0
        
        for line in csv_text.strip().split('\n'):
            line_num += 1
            line = line.strip()
            
            if not line or line.startswith('#'):  # Skip empty lines and comments
                continue
            
            # Skip header if present
            if 'discord' in line.lower() and 'elo' in line.lower():
                continue
            
            parts = line.split(',')
            if len(parts) < 2:
                errors.append(f"Line {line_num}: Invalid format (need at least 2 columns)")
                continue
            
            try:
                first_col = parts[0].strip()
                # ELO is in column 2 if using exported format (id,name,elo...) or column 1 if simple format
                elo_col = 2 if len(parts) >= 3 and not parts[1].replace('.','').replace('-','').isdigit() else 1
                elo_str = parts[elo_col].strip()
                
                # Remove % sign if present (from win rate column confusion)
                elo_str = elo_str.replace('%', '')
                elo = float(elo_str)
                
                # Validate ELO range
                if elo < 0 or elo > 3000:
                    errors.append(f"Line {line_num}: ELO {elo} out of range (0-3000)")
                    continue
                
                # Try to parse as discord_id first
                discord_id = None
                if first_col.isdigit():
                    discord_id = first_col
                else:
                    # Try to find player by display name in the guild
                    for member in ctx.guild.members:
                        if (member.display_name.lower() == first_col.lower() or 
                            member.name.lower() == first_col.lower()):
                            discord_id = str(member.id)
                            break
                    
                    if not discord_id:
                        errors.append(f"Line {line_num}: Could not find player '{first_col}' in server")
                        continue
                
                elo_updates.append((discord_id, elo))
            except ValueError as e:
                errors.append(f"Line {line_num}: {str(e)}")
        
        if not elo_updates:
            await ctx.send("❌ No valid ELO updates found in CSV!")
            if errors:
                error_msg = "\n".join(errors[:10])
                await ctx.send(f"**Errors:**\n```\n{error_msg}\n```")
            return
        
        # Confirm before updating
        await ctx.send(f"""
📋 **Import Preview**
Server: **{ctx.guild.name}**
Valid updates: **{len(elo_updates)}**
Errors: **{len(errors)}**

⚠️ Type `CONFIRM` to proceed with import, or `CANCEL` to abort.
You have 30 seconds to respond.
        """)
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel
        
        try:
            msg = await bot.wait_for('message', check=check, timeout=30.0)
            
            if msg.content.upper() != 'CONFIRM':
                await ctx.send("❌ Import cancelled.")
                return
        except asyncio.TimeoutError:
            await ctx.send("❌ Import cancelled (timeout).")
            return
        
        # Perform bulk update
        success_count, error_count, db_errors = db_manager.bulk_update_elos(str(ctx.guild.id), elo_updates)
        
        await ctx.send(f"""
✅ **ELO Import Complete**

**Results:**
✅ Successfully updated: **{success_count}** players
❌ Errors: **{error_count}**

Server: **{ctx.guild.name}**

Use `.topelo` to see the updated rankings!
        """)
        
        if db_errors:
            error_msg = "\n".join(db_errors[:10])
            await ctx.send(f"**Database Errors:**\n```\n{error_msg}\n```")
        
        # Auto-update leaderboard after ELO changes
        await update_leaderboard(ctx.guild.id)
        
    except Exception as e:
        await ctx.send(f"❌ Error processing CSV: {e}")
        import traceback
        traceback.print_exc()


@bot.command(name='examplepugcsv')
async def example_pug_csv(ctx):
    """Generate a template CSV with all players for PUG count updates (Admin only)
    
    Usage: .examplepugcsv
    
    Creates a CSV file with all registered players and their current PUG counts.
    You can edit the counts and upload with .updateplayerpugs
    """
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    try:
        server_id = str(ctx.guild.id)
        players = db_manager.get_all_players(server_id)
        
        # Filter out simulation players
        active_players = []
        for p in players:
            try:
                player_id = int(p['discord_id'])
                if player_id < 1000 or player_id >= 2000:
                    active_players.append(p)
            except (ValueError, TypeError):
                active_players.append(p)
        
        if not active_players:
            await ctx.send("❌ No players found in database!")
            return
        
        # Sort by display name
        active_players.sort(key=lambda x: (x.get('display_name') or x.get('discord_name') or f"Player_{x['discord_id']}").lower())
        
        # Build CSV with Discord ID in third column
        # Use apostrophe prefix to prevent Excel from converting to scientific notation
        csv_lines = ["PlayerName,AddPUGs,DiscordID"]
        
        for player in active_players:
            discord_id = player['discord_id']
            display_name = player.get('display_name') or player.get('discord_name') or f"Player_{discord_id}"
            
            # Clean up name (remove discriminator if present)
            if '#' in display_name:
                display_name = display_name.split('#')[0]
            
            # Add apostrophe prefix to Discord ID to force Excel to treat as text
            csv_lines.append(f"{display_name},0,'{discord_id}")
        
        csv_text = "\n".join(csv_lines)
        
        # Create file
        import io
        csv_file = io.BytesIO(csv_text.encode('utf-8'))
        csv_file.seek(0)
        
        # Send file
        file = discord.File(csv_file, filename=f"pug_counts_template_{ctx.guild.name.replace(' ', '_')}.csv")
        
        embed = discord.Embed(
            title="📊 PUG Count Template CSV",
            description=(
                f"Template CSV with all {len(active_players)} players.\n\n"
                "**How to use:**\n"
                "1. Download this CSV file\n"
                "2. Edit the `AddPUGs` column with counts to ADD\n"
                "3. Save the file (Excel safe - IDs prefixed with ')\n"
                "4. Upload with `.updateplayerpugs`\n\n"
                "**Format:** PlayerName,AddPUGs,DiscordID\n"
                "**Example:** ProGamer,150,'123456789\n\n"
                "**Excel Users:** The Discord IDs start with ' to prevent\n"
                "Excel from converting them to scientific notation.\n"
                "This is normal and will work correctly!\n\n"
                "**Alternative:** Use Google Sheets (no conversion issues)"
            ),
            color=discord.Color.blue()
        )
        
        await ctx.send(embed=embed, file=file)
        
    except Exception as e:
        await ctx.send(f"❌ Error generating CSV: {e}")
        import traceback
        traceback.print_exc()

@bot.command(name='updateplayerpugs')
async def update_player_pugs(ctx):
    """Bulk update player PUG counts from CSV (Admin only)
    
    Usage: .updateplayerpugs (attach CSV file)
    
    CSV Format (2-3 columns):
    
    Format 1: Name + Count
    PlayerName,PUGCount
    ProGamer,150
    SkillMaster,89
    
    Format 2: Name + Count + Discord ID (RECOMMENDED)
    PlayerName,PUGCount,DiscordID
    ProGamer,150,123456789
    SkillMaster,89,987654321
    
    Format 3: Discord ID + Count
    DiscordID,PUGCount
    123456789,150
    987654321,89
    
    The PUG count will be ADDED to the player's current count.
    Does NOT affect ELO, wins, or losses.
    Use .undoupdateplayerpugs to revert changes.
    
    TIP: Use .examplepugcsv to get a template CSV with all players!
    Discord ID in 3rd column provides most reliable matching!
    """
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Check for CSV attachment
    if not ctx.message.attachments:
        await ctx.send("❌ Please attach a CSV file with player PUG counts!")
        return
    
    attachment = ctx.message.attachments[0]
    if not attachment.filename.endswith('.csv'):
        await ctx.send("❌ File must be a CSV file!")
        return
    
    try:
        # Download CSV
        csv_data = await attachment.read()
        csv_text = csv_data.decode('utf-8')
        
        lines = csv_text.strip().split('\n')
        
        # Check if first line is header
        first_line = lines[0].strip().lower()
        if 'name' in first_line or 'id' in first_line or 'pug' in first_line:
            lines = lines[1:]  # Skip header
        
        if not lines:
            await ctx.send("❌ CSV file is empty!")
            return
        
        server_id = str(ctx.guild.id)
        updates = []
        errors = []
        
        # Clear previous backup and create new one
        global pug_count_backup
        pug_count_backup[server_id] = {}
        
        for line_num, line in enumerate(lines, start=2):
            line = line.strip()
            if not line:
                continue
            
            parts = line.split(',')
            if len(parts) < 2:
                errors.append(f"Line {line_num}: Invalid format (need Name,Count or ID,Count)")
                continue
            
            try:
                identifier = parts[0].strip()
                pug_count_str = parts[1].strip()
                
                # Remove leading apostrophe (used to force Excel text format)
                if identifier.startswith("'"):
                    identifier = identifier[1:]
                
                # Handle scientific notation in first column (Excel conversion)
                if 'E' in identifier.upper() or 'e' in identifier:
                    try:
                        from decimal import Decimal
                        identifier = str(int(Decimal(identifier)))
                    except:
                        pass  # Keep as-is if not valid scientific notation
                
                # Check if there's a Discord ID in the third column
                discord_id_override = None
                if len(parts) >= 3:
                    potential_id = parts[2].strip()
                    
                    # Remove leading apostrophe (used to force Excel text format)
                    if potential_id.startswith("'"):
                        potential_id = potential_id[1:]
                    
                    # Handle scientific notation from Excel (e.g., 8.64676E+16)
                    if 'E' in potential_id.upper() or 'e' in potential_id:
                        try:
                            # Use Decimal for precision (prevents digit loss)
                            from decimal import Decimal
                            potential_id = str(int(Decimal(potential_id)))
                        except:
                            pass  # Keep original if conversion fails
                    
                    # Check if it's a valid Discord ID (17-19 digits)
                    if potential_id.isdigit() and 17 <= len(potential_id) <= 19:
                        discord_id_override = potential_id
                
                # Parse PUG count
                pug_count = int(pug_count_str)
                if pug_count < 0:
                    errors.append(f"Line {line_num}: PUG count cannot be negative")
                    continue
                
                # Find player - prioritize Discord ID from third column
                discord_id = None
                player_name = None
                
                if discord_id_override:
                    # Use Discord ID from third column (most reliable)
                    discord_id = discord_id_override
                    player_data = db_manager.get_player(discord_id, server_id)
                    if not player_data:
                        errors.append(f"Line {line_num}: Player with ID {discord_id} not found")
                        continue
                    player_name = player_data.get('display_name') or player_data.get('discord_name') or f"Player_{discord_id}"
                elif identifier.isdigit():
                    # First column is Discord ID
                    discord_id = identifier
                    player_data = db_manager.get_player(discord_id, server_id)
                    if not player_data:
                        errors.append(f"Line {line_num}: Player with ID {discord_id} not found")
                        continue
                    player_name = player_data.get('display_name') or player_data.get('discord_name') or f"Player_{discord_id}"
                else:
                    # Player name - search in database first, then guild
                    discord_id = db_manager.find_player_by_name(server_id, identifier)
                    
                    if not discord_id:
                        # Try guild members
                        for member in ctx.guild.members:
                            if (member.display_name.lower() == identifier.lower() or 
                                member.name.lower() == identifier.lower()):
                                discord_id = str(member.id)
                                break
                    
                    if not discord_id:
                        errors.append(f"Line {line_num}: Player '{identifier}' not found")
                        continue
                    
                    player_data = db_manager.get_player(discord_id, server_id)
                    if not player_data:
                        errors.append(f"Line {line_num}: Player '{identifier}' not registered")
                        continue
                    
                    player_name = player_data.get('display_name') or identifier
                
                # Store backup of current count
                old_count = player_data['total_pugs']
                pug_count_backup[server_id][discord_id] = old_count
                
                # Calculate new total (ADD to existing count)
                new_total = old_count + pug_count
                
                # Update only the total_pugs field
                conn = db_manager.get_connection()
                cursor = conn.cursor()
                
                # Ensure immediate mode (no WAL delay)
                cursor.execute("PRAGMA synchronous = FULL")
                
                cursor.execute('''
                    UPDATE players 
                    SET total_pugs = ?
                    WHERE discord_id = ? AND server_id = ?
                ''', (new_total, discord_id, server_id))
                
                rows_affected = cursor.rowcount
                conn.commit()
                conn.close()
                
                # Verify the update worked
                verify_data = db_manager.get_player(discord_id, server_id)
                if verify_data:
                    actual_count = verify_data['total_pugs']
                    print(f"✅ Updated {player_name} (ID: {discord_id}): {old_count} → {new_total}, verified: {actual_count}, rows: {rows_affected}")
                    if actual_count != new_total:
                        print(f"⚠️ WARNING: Update verification failed for {player_name}! Expected {new_total}, got {actual_count}")
                        errors.append(f"Line {line_num}: Verification failed for {player_name}")
                else:
                    print(f"❌ ERROR: Could not verify update for {player_name}")
                    errors.append(f"Line {line_num}: Could not verify update for {player_name}")
                
                updates.append(f"{player_name}: {old_count} → {new_total} (+{pug_count})")
                
            except ValueError:
                errors.append(f"Line {line_num}: Invalid PUG count '{parts[1]}'")
            except Exception as e:
                errors.append(f"Line {line_num}: Error - {str(e)}")
        
        # Build result embed
        embed = discord.Embed(
            title="📊 Player PUG Counts Updated",
            color=discord.Color.green() if not errors else discord.Color.orange()
        )
        
        if updates:
            # Split updates into chunks if too long
            update_text = "\n".join(updates)
            if len(update_text) > 1024:
                update_text = "\n".join(updates[:20]) + f"\n... and {len(updates) - 20} more"
            embed.add_field(name=f"✅ Updated ({len(updates)} players)", value=update_text, inline=False)
        
        if errors:
            error_text = "\n".join(errors[:10])
            if len(errors) > 10:
                error_text += f"\n... and {len(errors) - 10} more errors"
            embed.add_field(name=f"❌ Errors ({len(errors)})", value=error_text, inline=False)
        
        embed.add_field(
            name="⚠️ Important", 
            value="PUG counts were ADDED to existing counts.\nELO, wins, and losses were NOT changed.\nUse `.undoupdateplayerpugs` to revert if needed.",
            inline=False
        )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error processing CSV: {e}")
        import traceback
        traceback.print_exc()

@bot.command(name='undoupdateplayerpugs')
async def undo_update_player_pugs(ctx):
    """Undo the last .updateplayerpugs operation (Admin only)
    
    Usage: .undoupdateplayerpugs
    
    Restores all player PUG counts to their values before the last update.
    Can only undo the most recent update per server.
    """
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    server_id = str(ctx.guild.id)
    
    # Check if there's a backup for this server
    global pug_count_backup
    if server_id not in pug_count_backup or not pug_count_backup[server_id]:
        await ctx.send("❌ No recent PUG count update to undo!")
        return
    
    try:
        backup = pug_count_backup[server_id]
        reverted = []
        
        # Get database connection once for all updates
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        
        for discord_id, old_count in backup.items():
            # Get current count
            player_data = db_manager.get_player(discord_id, server_id)
            if not player_data:
                continue
            
            current_count = player_data['total_pugs']
            player_name = player_data.get('display_name') or player_data.get('discord_name') or f"Player_{discord_id}"
            
            # Restore old count
            cursor.execute('''
                UPDATE players 
                SET total_pugs = ?
                WHERE discord_id = ? AND server_id = ?
            ''', (old_count, discord_id, server_id))
            
            reverted.append(f"{player_name}: {current_count} → {old_count}")
        
        # Commit all changes
        conn.commit()
        conn.close()
        
        # Clear the backup
        pug_count_backup[server_id] = {}
        
        # Build result embed
        embed = discord.Embed(
            title="↩️ PUG Count Update Reverted",
            description=f"Restored {len(reverted)} players to their previous PUG counts.",
            color=discord.Color.blue()
        )
        
        if reverted:
            revert_text = "\n".join(reverted)
            if len(revert_text) > 1024:
                revert_text = "\n".join(reverted[:20]) + f"\n... and {len(reverted) - 20} more"
            embed.add_field(name="✅ Reverted", value=revert_text, inline=False)
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error reverting changes: {e}")
        import traceback
        traceback.print_exc()

@bot.command(name='scrapestatus')
async def scrape_status(ctx):
    """Check if external stats scraping is enabled (Admin only)
    
    Shows whether the bot is configured to fetch stats from an external website.
    Admins can enable/disable this feature and configure which stats site to use.
    """
    if not is_full_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    enabled = db_manager.is_scraping_enabled()
    status = "✅ Enabled" if enabled else "❌ Disabled"
    
    await ctx.send(f"**External Stats Scraping Status:** {status}\n"
                   f"Configure scraper.py to set up your game's stats website.")

@bot.command(name='setelo')
async def set_elo(ctx, player_name: str, new_elo: int):
    """Set a player's ELO manually (Admin/PugAdmin only)
    
    Supports:
    - @mention (e.g., @username)
    - Discord username (e.g., user123)
    - Display name/nickname (e.g., CoolPlayer)
    - All methods work even if names differ
    """
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    discord_id = None
    member = None
    
    # Check if it's a mention
    if ctx.message.mentions:
        member = ctx.message.mentions[0]
        discord_id = str(member.id)
    else:
        # First, try to find player by name in database (checks both discord_name and display_name)
        discord_id = db_manager.find_player_by_name(str(ctx.guild.id), player_name)
        
        if discord_id:
            # Found in database - use that Discord ID
            try:
                member = await ctx.guild.fetch_member(int(discord_id))
            except:
                # Player in database but not in server anymore
                await ctx.send(f"⚠️ Found player '{player_name}' in database but they're no longer in the server. Updating anyway...")
                member = None
        else:
            # Not in database - search guild members by display name or username
            member = None
            for guild_member in ctx.guild.members:
                if (guild_member.display_name.lower() == player_name.lower() or 
                    guild_member.name.lower() == player_name.lower()):
                    member = guild_member
                    discord_id = str(member.id)
                    break
            
            if not member:
                await ctx.send(f"❌ Could not find player '{player_name}' in server or database!")
                return
    
    # Get current ELO
    player_data = db_manager.get_player(discord_id, str(ctx.guild.id))
    old_elo = player_data['elo']
    old_rank = get_elo_rank(old_elo)
    
    # Validate new ELO
    if new_elo < 0 or new_elo > 3000:
        await ctx.send("❌ ELO must be between 0 and 3000!")
        return
    
    # Update ELO
    db_manager.update_player_elo(discord_id, str(ctx.guild.id), new_elo)
    new_rank = get_elo_rank(new_elo)
    
    # Show confirmation
    embed = discord.Embed(
        title="⚙️ ELO Manually Updated",
        description=f"Updated ELO for {member.mention if member else player_name}",
        color=discord.Color.orange()
    )
    embed.add_field(name="Old ELO", value=f"{old_elo:.0f} ({old_rank} rank)", inline=True)
    embed.add_field(name="New ELO", value=f"{new_elo} ({new_rank} rank)", inline=True)
    
    change = new_elo - old_elo
    change_text = f"+{change}" if change > 0 else str(change)
    embed.add_field(name="Change", value=change_text, inline=True)
    
    await ctx.send(embed=embed)
    
    # Auto-update leaderboard after ELO change
    await update_leaderboard(ctx.guild.id)

@bot.command(name='setpugs')
async def set_pugs(ctx, player_name: str, total_pugs: int):
    """Set a player's total PUG count manually (Admin only)
    
    Usage:
    .setpugs @Player 150
    .setpugs PlayerName 89
    
    This updates the total_pugs count without affecting wins, losses, or ELO.
    """
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Resolve player
    member, discord_id = await resolve_player(ctx, player_name)
    
    if not member:
        await ctx.send(f"❌ Could not find player '{player_name}'!")
        return
    
    # Check if player exists
    player_data = db_manager.get_player(discord_id, str(ctx.guild.id))
    if not player_data:
        await ctx.send(f"❌ {member.mention} is not registered! They need to use `.register` first.")
        return
    
    # Validate total_pugs
    if total_pugs < 0:
        await ctx.send("❌ Total PUGs cannot be negative!")
        return
    
    old_total = player_data['total_pugs']
    
    # Update total_pugs
    success = db_manager.update_player_total_pugs(discord_id, str(ctx.guild.id), total_pugs)
    
    if not success:
        await ctx.send(f"❌ Failed to update PUG count for {member.mention}")
        return
    
    # Show confirmation
    embed = discord.Embed(
        title="⚙️ PUG Count Manually Updated",
        description=f"Updated total PUGs for {member.mention}",
        color=discord.Color.orange()
    )
    embed.add_field(name="Player", value=member.display_name, inline=True)
    embed.add_field(name="Old Total", value=old_total, inline=True)
    embed.add_field(name="New Total", value=total_pugs, inline=True)
    
    change = total_pugs - old_total
    change_text = f"+{change}" if change > 0 else str(change)
    embed.add_field(name="Change", value=change_text, inline=True)
    
    embed.add_field(
        name="ℹ️ Note",
        value=f"Wins/Losses/ELO were not changed. Current record: {player_data['wins']}W-{player_data['losses']}L",
        inline=False
    )
    
    await ctx.send(embed=embed)

@bot.command(name='setpeak')
async def set_peak(ctx, player_name: str, peak_elo: int):
    """Set a player's peak ELO manually (Admin only)
    
    Usage:
    .setpeak @Player 1500
    .setpeak PlayerName 1200
    
    This sets the peak_elo value directly.
    """
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Resolve player
    member, discord_id = await resolve_player(ctx, player_name)
    
    if not member:
        await ctx.send(f"❌ Could not find player '{player_name}'!")
        return
    
    # Check if player exists
    player_data = db_manager.get_player(discord_id, str(ctx.guild.id))
    if not player_data:
        await ctx.send(f"❌ {member.mention} is not registered!")
        return
    
    # Validate peak_elo
    if peak_elo < 0 or peak_elo > 3000:
        await ctx.send("❌ Peak ELO must be between 0 and 3000!")
        return
    
    old_peak = player_data.get('peak_elo', player_data['elo'])
    current_elo = player_data['elo']
    
    # Update peak_elo directly
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE players 
        SET peak_elo = ?
        WHERE discord_id = ? AND server_id = ?
    """, (peak_elo, discord_id, str(ctx.guild.id)))
    conn.commit()
    conn.close()
    
    # Show confirmation
    embed = discord.Embed(
        title="⚙️ Peak ELO Manually Updated",
        description=f"Updated peak ELO for {member.mention}",
        color=discord.Color.orange()
    )
    embed.add_field(name="Player", value=member.display_name, inline=True)
    embed.add_field(name="Current ELO", value=f"{current_elo:.0f}", inline=True)
    embed.add_field(name="Old Peak", value=f"{old_peak:.0f}", inline=True)
    embed.add_field(name="New Peak", value=peak_elo, inline=True)
    
    change = peak_elo - old_peak
    change_text = f"+{change}" if change > 0 else str(change)
    embed.add_field(name="Change", value=change_text, inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='deleteplayer')
async def delete_player(ctx, player_name: str):
    """Delete a player from the database (Admin role only)
    
    Usage:
    .deleteplayer @Player
    .deleteplayer PlayerName
    
    WARNING: This permanently removes all stats for this player!
    """
    if not is_full_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Resolve player from @mention or name
    member, discord_id = await resolve_player(ctx, player_name)
    
    if not member and not discord_id:
        # Try to find in database if not in server
        discord_id = db_manager.find_player_by_name(str(ctx.guild.id), player_name)
        if not discord_id:
            await ctx.send(f"❌ Could not find player '{player_name}'. Use @mention or exact display name.")
            return
    
    # Check if player exists in database
    if not db_manager.player_exists(discord_id, str(ctx.guild.id)):
        await ctx.send(f"❌ Player is not registered in the database!")
        return
    
    # Get player stats before deletion
    player_data = db_manager.get_player(discord_id, str(ctx.guild.id))
    
    # Confirm deletion
    embed = discord.Embed(
        title="⚠️ Confirm Player Deletion",
        description=f"Are you sure you want to delete this player?",
        color=discord.Color.red()
    )
    
    player_display = member.mention if member else player_name
    embed.add_field(name="Player", value=player_display, inline=False)
    embed.add_field(name="ELO", value=f"{player_data['elo']:.0f}", inline=True)
    embed.add_field(name="Total PUGs", value=player_data['total_pugs'], inline=True)
    embed.add_field(name="Record", value=f"{player_data['wins']}W-{player_data['losses']}L", inline=True)
    embed.add_field(name="⚠️ Warning", value="This action cannot be undone!", inline=False)
    
    msg = await ctx.send(embed=embed)
    await msg.add_reaction('✅')
    await msg.add_reaction('❌')
    
    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in ['✅', '❌'] and reaction.message.id == msg.id
    
    try:
        reaction, user = await bot.wait_for('reaction_add', timeout=30.0, check=check)
        
        if str(reaction.emoji) == '✅':
            # Delete the player
            deleted = db_manager.delete_player(discord_id, str(ctx.guild.id))
            
            if deleted:
                await ctx.send(f"✅ Successfully deleted {player_display} from the database!")
            else:
                await ctx.send(f"❌ Failed to delete player (they may have already been removed).")
        else:
            await ctx.send("❌ Player deletion cancelled.")
    
    except TimeoutError:
        await ctx.send("⏱️ Deletion confirmation timed out. Player was NOT deleted.")

@bot.command(name='reseteloall')
async def reset_elo_all(ctx):
    """Reset all player ELOs to 700 (Admin role only)"""
    if not is_full_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Get all players for this server and reset their ELOs
    players = db_manager.get_all_players(str(ctx.guild.id))
    
    if not players:
        await ctx.send("❌ No players to reset!")
        return
    
    # Reset each player to 700
    for player in players:
        db_manager.update_player_elo(player['discord_id'], str(ctx.guild.id), 700)
    
    await ctx.send(f"✅ **Reset complete!** All {len(players)} players on this server now have 700 ELO.")
    
    # Auto-update leaderboard after ELO changes
    await update_leaderboard(ctx.guild.id)

@bot.command(name='resetplayerpugs')
async def reset_player_pugs(ctx):
    """Reset all player wins/losses to 0 (Admin only)"""
    if not is_full_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    await ctx.send("⚠️ **WARNING:** This will reset ALL player wins/losses to 0 for this server!\nType `CONFIRM` to proceed or `CANCEL` to abort.")
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        msg = await bot.wait_for('message', check=check, timeout=30.0)
        
        if msg.content.upper() != 'CONFIRM':
            await ctx.send("❌ Reset cancelled.")
            return
    except asyncio.TimeoutError:
        await ctx.send("❌ Reset cancelled (timeout).")
        return
    
    # Get all players for this server
    players = db_manager.get_all_players(str(ctx.guild.id))
    
    if not players:
        await ctx.send("❌ No players to reset!")
        return
    
    # Reset wins and losses for each player
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE players 
        SET wins = 0, losses = 0
        WHERE server_id = ?
    ''', (str(ctx.guild.id),))
    
    conn.commit()
    conn.close()
    
    await ctx.send(f"✅ **Reset complete!** All {len(players)} players now have 0 wins and 0 losses.")

@bot.command(name='resetpugstats')
async def reset_pug_stats(ctx):
    """Reset total PUGs played count to 0 for this server (Admin only)"""
    if not is_full_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    await ctx.send("⚠️ **WARNING:** This will reset the total PUGs count to 0 for this server!\nType `CONFIRM` to proceed or `CANCEL` to abort.")
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        msg = await bot.wait_for('message', check=check, timeout=30.0)
        
        if msg.content.upper() != 'CONFIRM':
            await ctx.send("❌ Reset cancelled.")
            return
    except asyncio.TimeoutError:
        await ctx.send("❌ Reset cancelled (timeout).")
        return
    
    # Reset total_pugs for all players on this server
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE players 
        SET total_pugs = 0
        WHERE server_id = ?
    ''', (str(ctx.guild.id),))
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    await ctx.send(f"✅ **Reset complete!** Total PUGs count reset for {affected} players on this server.")

@bot.command(name='cleanduplicates')
async def clean_duplicates(ctx):
    """Remove duplicate player entries (keeps real Discord users, removes failures) (Admin only)"""
    if not is_full_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Get all players for this server
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT discord_id, elo FROM players 
        WHERE server_id = ?
        ORDER BY elo DESC
    ''', (str(ctx.guild.id),))
    
    all_players = cursor.fetchall()
    
    # Find duplicates: same ELO, but one user can't be fetched from Discord
    to_delete = []
    seen_elos = {}
    
    for discord_id, elo in all_players:
        # Try to fetch the user from Discord
        try:
            user = await bot.fetch_user(int(discord_id))
            # User exists in Discord - this is a valid entry
            if elo in seen_elos:
                # We have a duplicate ELO - keep this valid one, mark old one for deletion
                old_id = seen_elos[elo]
                if old_id not in to_delete:
                    to_delete.append(old_id)
            seen_elos[elo] = discord_id
        except:
            # Can't fetch user - this is likely an invalid/old entry
            to_delete.append(discord_id)
    
    if not to_delete:
        await ctx.send("✅ No duplicate or invalid entries found!")
        return
    
    # Show what will be deleted
    preview_msg = f"Found **{len(to_delete)}** entries to remove:\n"
    for i, discord_id in enumerate(to_delete[:10]):
        cursor.execute('SELECT elo FROM players WHERE discord_id = ? AND server_id = ?',
                      (discord_id, str(ctx.guild.id)))
        result = cursor.fetchone()
        if result:
            preview_msg += f"- ID: {discord_id} (ELO: {result[0]})\n"
    
    if len(to_delete) > 10:
        preview_msg += f"... and {len(to_delete) - 10} more\n"
    
    await ctx.send(preview_msg + "\n⚠️ Type `CONFIRM` to delete these entries, or `CANCEL` to abort.")
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        msg = await bot.wait_for('message', check=check, timeout=30.0)
        
        if msg.content.upper() != 'CONFIRM':
            await ctx.send("❌ Cleanup cancelled.")
            conn.close()
            return
    except asyncio.TimeoutError:
        await ctx.send("❌ Cleanup cancelled (timeout).")
        conn.close()
        return
    
    # Delete the invalid entries
    deleted_count = 0
    for discord_id in to_delete:
        cursor.execute('''
            DELETE FROM players 
            WHERE discord_id = ? AND server_id = ?
        ''', (discord_id, str(ctx.guild.id)))
        deleted_count += 1
    
    conn.commit()
    conn.close()
    
    await ctx.send(f"✅ **Cleanup complete!** Removed {deleted_count} duplicate/invalid player entries.")

@bot.command(name='cleartopelo')
async def clear_top_elo(ctx):
    """Delete ALL player ELO data for this server (Admin only - use before fresh import)"""
    if not is_full_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Get count of players to delete
    players = db_manager.get_all_players(str(ctx.guild.id))
    player_count = len(players)
    
    if player_count == 0:
        await ctx.send("✅ No players to delete - database is already empty for this server.")
        return
    
    await ctx.send(f"""
⚠️ **DANGER: COMPLETE DATA WIPE**

This will **PERMANENTLY DELETE** all player data for this server:
- **{player_count} player records** will be removed
- All ELOs, wins, losses, and total PUGs will be erased
- This action **CANNOT BE UNDONE**

**Use this before doing a fresh ELO import.**

Type `DELETE ALL DATA` to confirm, or `CANCEL` to abort.
You have 30 seconds to respond.
    """)
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        msg = await bot.wait_for('message', check=check, timeout=30.0)
        
        if msg.content != 'DELETE ALL DATA':
            await ctx.send("❌ Clear cancelled. (You must type exactly: DELETE ALL DATA)")
            return
    except asyncio.TimeoutError:
        await ctx.send("❌ Clear cancelled (timeout).")
        return
    
    # Delete all players for this server
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        DELETE FROM players 
        WHERE server_id = ?
    ''', (str(ctx.guild.id),))
    
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    
    await ctx.send(f"""
✅ **Complete wipe successful!**

Deleted: **{deleted} player records**

The player database for this server is now empty.
You can now import fresh ELO data with `.importelos`
    """)

@bot.command(name='autopick')
async def enable_autopick(ctx, game_mode: str = 'default'):
    """Enable automatic team balancing (Admin only)"""
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Resolve alias
    game_mode_resolved = db_manager.resolve_mode_alias(game_mode.lower())
    
    # Get mode data first to validate
    mode_data = db_manager.get_game_mode(game_mode_resolved)
    if not mode_data:
        await ctx.send(f"❌ Game mode '{game_mode}' not found!")
        return
    
    queue = get_queue(ctx.channel, game_mode_resolved)
    
    if queue.autopick_mode:
        await ctx.send(f"✅ Autopick is already enabled for **{mode_data['name']}** mode!")
        return
    
    queue.autopick_mode = True
    await ctx.send(f"✅ **Autopick enabled** for **{mode_data['name']}** mode! Teams will be automatically balanced by ELO when the queue fills.")

@bot.command(name='autopickoff')
async def autopick_off(ctx, game_mode: str = 'default'):
    """Disable automatic team balancing (Admin only)"""
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Resolve alias
    game_mode_resolved = db_manager.resolve_mode_alias(game_mode.lower())
    
    # Get mode data first to validate
    mode_data = db_manager.get_game_mode(game_mode_resolved)
    if not mode_data:
        await ctx.send(f"❌ Game mode '{game_mode}' not found!")
        return
    
    queue = get_queue(ctx.channel, game_mode_resolved)
    
    if not queue.autopick_mode:
        await ctx.send(f"✅ Autopick is already disabled for **{mode_data['name']}** mode!")
        return
    
    queue.autopick_mode = False
    await ctx.send(f"✅ **Autopick disabled** for **{mode_data['name']}** mode! Teams will be picked manually by captains.")

# External Stats Integration Commands
# NOTE: This section is for integrating with external game stat tracking websites
# Configure the scraper.py file to match your game's stats website
# Examples: stats.ut2k4.com, tracker.gg, op.gg, etc.

@bot.command(name='linkstats')
async def link_stats(ctx, player_name: str):
    """Link your Discord account to your in-game player name for stat tracking
    
    Usage: .linkstats YourGameName
    
    This allows the bot to fetch your stats from the configured stats website.
    Ask your admin which stats website is configured for your community.
    """
    # Update player's external game name
    db_manager.update_ut2k4_info(ctx.author.id, str(ctx.guild.id), player_name)
    
    embed = discord.Embed(
        title="🔗 Stats Account Linked",
        description=f"Linked {ctx.author.mention} to in-game player: **{player_name}**",
        color=discord.Color.green()
    )
    
    # Try to scrape stats if scraping is enabled
    if db_manager.is_scraping_enabled():
        embed.add_field(name="Status", value="⏳ Fetching stats from configured stats website...", inline=False)
        message = await ctx.send(embed=embed)
        
        # Scrape stats (configure scraper.py for your game's stats website)
        stats = await ut2k4_scraper.search_player(player_name)
        
        if stats:
            embed.clear_fields()
            embed.add_field(name="Status", value="✅ Stats retrieved successfully!", inline=False)
            embed.add_field(name="Kills", value=f"{stats['kills']:,}", inline=True)
            embed.add_field(name="Deaths", value=f"{stats['deaths']:,}", inline=True)
            embed.add_field(name="Efficiency", value=f"{stats['efficiency']:.2f}%", inline=True)
            embed.add_field(name="Matches Played", value=f"{stats['matches_played']:,}", inline=True)
            embed.add_field(name="Time Played", value=stats['time_played'], inline=True)
            embed.add_field(name="Favorite Weapon", value=stats['favorite_weapon'], inline=True)
            await message.edit(embed=embed)
        else:
            embed.clear_fields()
            embed.add_field(name="Status", value="⚠️ Could not find stats for this player", inline=False)
            embed.set_footer(text="Make sure the player name is correct")
            await message.edit(embed=embed)
    else:
        embed.add_field(name="Note", value="Stat scraping is currently disabled", inline=False)
        await ctx.send(embed=embed)

@bot.command(name='gamestats')
async def show_game_stats(ctx, target: discord.Member = None):
    """Show external game stats for yourself or another player
    
    Usage: .gamestats or .gamestats @player
    
    Displays stats fetched from the configured stats tracking website.
    Player must first link their account with .linkstats
    """
    target = target or ctx.author
    
    player_data = db_manager.get_player(target.id, str(ctx.guild.id))
    game_name = player_data.get('ut2k4_player_name')
    
    if not game_name:
        await ctx.send(f"❌ {target.mention} has not linked their game account yet! Use `.linkstats <playername>`")
        return
    
    if not db_manager.is_scraping_enabled():
        await ctx.send("❌ Stat scraping is currently disabled!")
        return
    
    # Show loading message
    embed = discord.Embed(
        title="🔍 Fetching Game Stats",
        description=f"Searching configured stats website for **{game_name}**...",
        color=discord.Color.blue()
    )
    message = await ctx.send(embed=embed)
    
    # Scrape stats (configure scraper.py for your game)
    stats = await ut2k4_scraper.search_player(game_name)
    
    if stats:
        embed = discord.Embed(
            title=f"📊 Game Stats for {game_name}",
            description=f"Discord: {target.mention}",
            color=discord.Color.gold()
        )
        embed.add_field(name="Kills", value=f"{stats['kills']:,}", inline=True)
        embed.add_field(name="Deaths", value=f"{stats['deaths']:,}", inline=True)
        embed.add_field(name="K/D Ratio", value=f"{stats['kills']/max(stats['deaths'],1):.2f}", inline=True)
        embed.add_field(name="Suicides", value=f"{stats['suicides']:,}", inline=True)
        embed.add_field(name="Efficiency", value=f"{stats['efficiency']:.2f}%", inline=True)
        embed.add_field(name="Matches Played", value=f"{stats['matches_played']:,}", inline=True)
        embed.add_field(name="Time Played", value=stats['time_played'], inline=True)
        embed.add_field(name="Favorite Weapon", value=stats['favorite_weapon'], inline=True)
        embed.set_footer(text="Data from configured stats website")
        await message.edit(embed=embed)
    else:
        embed = discord.Embed(
            title="❌ Stats Not Found",
            description=f"Could not find stats for **{game_name}** on the configured stats website",
            color=discord.Color.red()
        )
        embed.set_footer(text="The player name may be incorrect or have no recorded stats")
        await message.edit(embed=embed)

@bot.command(name='enablescrape')
async def enable_scrape(ctx):
    """Enable UT2K4 stat scraping (Admin role only)"""
    if not is_full_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    db_manager.set_scraping_enabled(True)
    await ctx.send("✅ UT2K4 stat scraping has been **enabled**!")

@bot.command(name='disablescrape')
async def disable_scrape(ctx):
    """Disable UT2K4 stat scraping (Admin role only)"""
    if not is_full_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    db_manager.set_scraping_enabled(False)
    await ctx.send("✅ UT2K4 stat scraping has been **disabled**!")

@bot.command(name='pickforred')
async def pick_for_red(ctx, *, player_identifier: str):
    """Pick player(s) for red team (Admin only) - use number or name. Can pick 2: .pickforred 3 5"""
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Find the queue that's currently in picking state
    channel_queues = get_channel_queues(ctx.channel)
    queue = None
    
    for q in channel_queues.values():
        if q.state == 'picking':
            queue = q
            break
    
    if not queue:
        await ctx.send("❌ No active PUG in picking phase! Start a PUG first.")
        return
    
    # Get available players
    available = queue.get_available_players()
    
    if not available:
        await ctx.send("❌ No players available to pick!")
        return
    
    # Parse player identifier(s) - can be multiple numbers like "3 5"
    player_identifier = player_identifier.strip()
    picks = player_identifier.split()
    member_ids = []
    
    for pick in picks:
        member_id = None
        
        # Check if it's a number
        if pick.isdigit():
            pick_number = int(pick)
            
            # Use initial_queue for consistent numbering
            if queue.initial_queue:
                if 1 <= pick_number <= len(queue.initial_queue):
                    target_uid = queue.initial_queue[pick_number - 1]
                    if target_uid in available:
                        member_id = target_uid
                    else:
                        await ctx.send(f"❌ Player #{pick_number} is not available!")
                        return
                else:
                    await ctx.send(f"❌ Invalid number! Pick between 1 and {len(queue.initial_queue)}.")
                    return
            else:
                # Fallback if no initial_queue
                if 1 <= pick_number <= len(available):
                    member_id = available[pick_number - 1]
                else:
                    await ctx.send(f"❌ Invalid number! Pick between 1 and {len(available)}.")
                    return
        else:
            # Try to find by name
            for guild_member in ctx.guild.members:
                if (guild_member.display_name.lower() == pick.lower() or 
                    guild_member.name.lower() == pick.lower()):
                    if guild_member.id in available:
                        member_id = guild_member.id
                    else:
                        await ctx.send(f"❌ {guild_member.display_name} is not available!")
                        return
                    break
            
            if not member_id:
                await ctx.send(f"❌ Could not find player '{pick}'. Use player number or exact display name.")
                return
        
        member_ids.append(member_id)
    
    # Validate number of picks
    if len(member_ids) > 2:
        await ctx.send("❌ You can only pick up to 2 players at once!")
        return
    
    # Make the picks
    for member_id in member_ids:
        success, error = await queue.pick_player(queue.red_captain, member_id, 'red', admin_override=True)
        if not success:
            await ctx.send(f"❌ {error}")
            return

@bot.command(name='pickforblue')
async def pick_for_blue(ctx, *, player_identifier: str):
    """Pick player(s) for blue team (Admin only) - use number or name. Can pick 2: .pickforblue 3 5"""
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Find the queue that's currently in picking state
    channel_queues = get_channel_queues(ctx.channel)
    queue = None
    
    for q in channel_queues.values():
        if q.state == 'picking':
            queue = q
            break
    
    if not queue:
        await ctx.send("❌ No active PUG in picking phase! Start a PUG first.")
        return
    
    # Get available players
    available = queue.get_available_players()
    
    if not available:
        await ctx.send("❌ No players available to pick!")
        return
    
    # Parse player identifier(s) - can be multiple numbers like "3 5"
    player_identifier = player_identifier.strip()
    picks = player_identifier.split()
    member_ids = []
    
    for pick in picks:
        member_id = None
        
        # Check if it's a number
        if pick.isdigit():
            pick_number = int(pick)
            
            # Use initial_queue for consistent numbering
            if queue.initial_queue:
                if 1 <= pick_number <= len(queue.initial_queue):
                    target_uid = queue.initial_queue[pick_number - 1]
                    if target_uid in available:
                        member_id = target_uid
                    else:
                        await ctx.send(f"❌ Player #{pick_number} is not available!")
                        return
                else:
                    await ctx.send(f"❌ Invalid number! Pick between 1 and {len(queue.initial_queue)}.")
                    return
            else:
                # Fallback if no initial_queue
                if 1 <= pick_number <= len(available):
                    member_id = available[pick_number - 1]
                else:
                    await ctx.send(f"❌ Invalid number! Pick between 1 and {len(available)}.")
                    return
        else:
            # Try to find by name
            for guild_member in ctx.guild.members:
                if (guild_member.display_name.lower() == pick.lower() or 
                    guild_member.name.lower() == pick.lower()):
                    if guild_member.id in available:
                        member_id = guild_member.id
                    else:
                        await ctx.send(f"❌ {guild_member.display_name} is not available!")
                        return
                    break
            
            if not member_id:
                await ctx.send(f"❌ Could not find player '{pick}'. Use player number or exact display name.")
                return
        
        member_ids.append(member_id)
    
    # Validate number of picks
    if len(member_ids) > 2:
        await ctx.send("❌ You can only pick up to 2 players at once!")
        return
    
    # Make the picks
    for member_id in member_ids:
        success, error = await queue.pick_player(queue.blue_captain, member_id, 'blue', admin_override=True)
        if not success:
            await ctx.send(f"❌ {error}")
            return

@bot.command(name='undopickforred')
async def undo_pick_for_red(ctx, *, player_identifier: str):
    """Undo a pick from red team (Admin only) - returns player to available pool"""
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Find the queue that's currently in picking state
    channel_queues = get_channel_queues(ctx.channel)
    queue = None
    
    for q in channel_queues.values():
        if q.state == 'picking':
            queue = q
            break
    
    if not queue:
        await ctx.send("❌ No active PUG in picking phase!")
        return
    
    # Check if red team has any players
    if not queue.red_team:
        await ctx.send("❌ Red team has no players to undo!")
        return
    
    # Find player to undo
    member_id = None
    player_identifier = player_identifier.strip()
    
    # Check if it's a number (position in team)
    if player_identifier.isdigit():
        team_position = int(player_identifier)
        if 1 <= team_position <= len(queue.red_team):
            member_id = queue.red_team[team_position - 1]
        else:
            await ctx.send(f"❌ Invalid position! Red team has {len(queue.red_team)} player(s). Use 1-{len(queue.red_team)}.")
            return
    else:
        # Try to find by name in red team
        for guild_member in ctx.guild.members:
            if (guild_member.display_name.lower() == player_identifier.lower() or 
                guild_member.name.lower() == player_identifier.lower()):
                if guild_member.id in queue.red_team:
                    member_id = guild_member.id
                else:
                    await ctx.send(f"❌ {guild_member.display_name} is not on red team!")
                    return
                break
        
        if not member_id:
            await ctx.send(f"❌ Could not find player '{player_identifier}' on red team.")
            return
    
    # Don't allow undoing captains
    if member_id == queue.red_captain:
        await ctx.send("❌ Cannot undo the red captain! They must remain on the team.")
        return
    
    # Remove from red team
    queue.red_team.remove(member_id)
    
    # Show updated teams
    await queue.show_teams()
    await ctx.send(f"✅ Removed <@{member_id}> from red team. Player is now available to pick.")

@bot.command(name='undopickforblue')
async def undo_pick_for_blue(ctx, *, player_identifier: str):
    """Undo a pick from blue team (Admin only) - returns player to available pool"""
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Find the queue that's currently in picking state
    channel_queues = get_channel_queues(ctx.channel)
    queue = None
    
    for q in channel_queues.values():
        if q.state == 'picking':
            queue = q
            break
    
    if not queue:
        await ctx.send("❌ No active PUG in picking phase!")
        return
    
    # Check if blue team has any players
    if not queue.blue_team:
        await ctx.send("❌ Blue team has no players to undo!")
        return
    
    # Find player to undo
    member_id = None
    player_identifier = player_identifier.strip()
    
    # Check if it's a number (position in team)
    if player_identifier.isdigit():
        team_position = int(player_identifier)
        if 1 <= team_position <= len(queue.blue_team):
            member_id = queue.blue_team[team_position - 1]
        else:
            await ctx.send(f"❌ Invalid position! Blue team has {len(queue.blue_team)} player(s). Use 1-{len(queue.blue_team)}.")
            return
    else:
        # Try to find by name in blue team
        for guild_member in ctx.guild.members:
            if (guild_member.display_name.lower() == player_identifier.lower() or 
                guild_member.name.lower() == player_identifier.lower()):
                if guild_member.id in queue.blue_team:
                    member_id = guild_member.id
                else:
                    await ctx.send(f"❌ {guild_member.display_name} is not on blue team!")
                    return
                break
        
        if not member_id:
            await ctx.send(f"❌ Could not find player '{player_identifier}' on blue team.")
            return
    
    # Don't allow undoing captains
    if member_id == queue.blue_captain:
        await ctx.send("❌ Cannot undo the blue captain! They must remain on the team.")
        return
    
    # Remove from blue team
    queue.blue_team.remove(member_id)
    
    # Show updated teams
    await queue.show_teams()
    await ctx.send(f"✅ Removed <@{member_id}> from blue team. Player is now available to pick.")

@bot.command(name='setcaptainred')
async def set_captain_red(ctx, *, player_name: str):
    """Set a specific player as red captain (Admin only)
    
    Usage:
    .setcaptainred @Player
    .setcaptainred PlayerName
    """
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Resolve player from @mention or name
    member, discord_id = await resolve_player(ctx, player_name)
    
    if not member:
        await ctx.send(f"❌ Could not find player '{player_name}'. Use @mention or exact display name.")
        return
    
    queue = get_queue(ctx.channel)
    queue.red_captain = member.id
    await ctx.send(f"✅ Set {member.mention} as Red Captain!")

@bot.command(name='setcaptainblue')
async def set_captain_blue(ctx, *, player_name: str):
    """Set a specific player as blue captain (Admin only)
    
    Usage:
    .setcaptainblue @Player
    .setcaptainblue PlayerName
    """
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Resolve player from @mention or name
    member, discord_id = await resolve_player(ctx, player_name)
    
    if not member:
        await ctx.send(f"❌ Could not find player '{player_name}'. Use @mention or exact display name.")
        return
    
    queue = get_queue(ctx.channel)
    queue.blue_captain = member.id
    await ctx.send(f"✅ Set {member.mention} as Blue Captain!")

@bot.command(name='dmon')
async def dm_notifications_on(ctx, game_mode: str = 'default'):
    """Enable DM notifications when queue fills (Admin only)"""
    if not is_full_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    queue = get_queue(ctx.channel, game_mode.lower())
    queue.dm_notifications = True
    mode_data = db_manager.get_game_mode(game_mode.lower())
    await ctx.send(f"✅ DM notifications **enabled** for **{mode_data['name']}** pug!")

@bot.command(name='dmoff')
async def dm_notifications_off(ctx, game_mode: str = 'default'):
    """Disable DM notifications when queue fills (Admin only)"""
    if not is_full_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    queue = get_queue(ctx.channel, game_mode.lower())
    queue.dm_notifications = False
    mode_data = db_manager.get_game_mode(game_mode.lower())
    await ctx.send(f"✅ DM notifications **disabled** for **{mode_data['name']}** pug!")

@bot.command(name='stats')
async def player_stats(ctx, *, player_name: str):
    """View stats for any player
    
    Usage:
    .stats @Player
    .stats PlayerName
    """
    # Resolve player from @mention or name
    member, discord_id = await resolve_player(ctx, player_name)
    
    if not member:
        await ctx.send(f"❌ Could not find player '{player_name}'. Use @mention or exact display name.")
        return
    
    # Check if player is registered (don't auto-create)
    if not db_manager.player_exists(str(member.id), str(ctx.guild.id)):
        await ctx.send(f"❌ {member.mention} is not registered! They need to join a queue first.")
        return
    
    player_data = db_manager.get_player(member.id, str(ctx.guild.id))
    total = player_data['total_pugs']
    wins = player_data['wins']
    losses = player_data['losses']
    elo = player_data['elo']
    rank = get_elo_rank(elo)
    # Win rate based on actual games (wins + losses), not total_pugs
    actual_games = wins + losses
    win_rate = (wins / actual_games * 100) if actual_games > 0 else 0
    
    # Find player's most recent PUG to show ELO change
    recent_pugs = db_manager.get_recent_pugs(20)
    last_elo_change = None
    
    for pug in recent_pugs:
        if pug.get('winner'):  # Only check PUGs with results
            player_id = str(member.id)
            if player_id in pug['red_team'] or player_id in pug['blue_team']:
                # Calculate what the ELO change was
                K_FACTOR = 32
                expected_red = 1 / (1 + 10 ** ((pug['avg_blue_elo'] - pug['avg_red_elo']) / 400))
                expected_blue = 1 - expected_red
                
                # Calculate change
                if pug['winner'] == 'red':
                    if player_id in pug['red_team']:
                        last_elo_change = K_FACTOR * (1 - expected_red)
                    else:
                        last_elo_change = K_FACTOR * (0 - expected_blue)
                else:  # blue won
                    if player_id in pug['blue_team']:
                        last_elo_change = K_FACTOR * (1 - expected_blue)
                    else:
                        last_elo_change = K_FACTOR * (0 - expected_red)
                break
    
    embed = discord.Embed(
        title=f"📊 Statistics for {member.display_name}",
        color=discord.Color.gold()
    )
    
    embed.add_field(name="Total PUGs", value=total, inline=True)
    embed.add_field(name="Wins", value=wins, inline=True)
    embed.add_field(name="Losses", value=losses, inline=True)
    embed.add_field(name="Win Rate", value=f"{win_rate:.1f}%", inline=True)
    
    # Show ELO with recent change
    if last_elo_change is not None:
        elo_display = f"{elo:.0f} ({last_elo_change:+.0f})"
    else:
        elo_display = f"{elo:.0f}"
    
    peak_elo = player_data.get('peak_elo')
    if peak_elo is None:
        peak_elo = elo
    
    # Calculate net ELO over last 10 PUGs
    recent_pugs_10 = db_manager.get_recent_pugs(100)  # Get more to find player's 10
    player_pugs = [p for p in recent_pugs_10 if (str(member.id) in p['red_team'] or str(member.id) in p['blue_team']) and p.get('winner')]
    player_pugs = player_pugs[:10]  # Take first 10
    
    net_elo_10 = 0
    if len(player_pugs) > 0:
        K_FACTOR = 32
        for pug in player_pugs:
            expected_red = 1 / (1 + 10 ** ((pug['avg_blue_elo'] - pug['avg_red_elo']) / 400))
            expected_blue = 1 - expected_red
            
            player_id = str(member.id)
            if pug['winner'] == 'red':
                if player_id in pug['red_team']:
                    net_elo_10 += K_FACTOR * (1 - expected_red)
                else:
                    net_elo_10 += K_FACTOR * (0 - expected_blue)
            else:  # blue won
                if player_id in pug['blue_team']:
                    net_elo_10 += K_FACTOR * (1 - expected_blue)
                else:
                    net_elo_10 += K_FACTOR * (0 - expected_red)
    
    net_elo_display = f"{net_elo_10:+.0f}" if net_elo_10 != 0 else "0"
    
    embed.add_field(name="ELO", value=elo_display, inline=True)
    embed.add_field(name="Peak ELO", value=f"{peak_elo:.0f}", inline=True)
    embed.add_field(name="Rank", value=rank, inline=True)
    embed.add_field(name="Last 10 PUGs", value=f"{net_elo_display} ELO", inline=True)
    
    # Add streak
    streak = player_data.get('current_streak', 0)
    if streak > 0:
        streak_display = f"🔥 {streak}W"
    elif streak < 0:
        streak_display = f"❄️ {abs(streak)}L"
    else:
        streak_display = "—"
    embed.add_field(name="Streak", value=streak_display, inline=True)
    
    # Add leaderboard position
    position, total_players = get_leaderboard_position(member.id, str(ctx.guild.id))
    if position:
        embed.add_field(name="Leaderboard", value=f"#{position} of {total_players}", inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='leaderboard')
async def leaderboard(ctx):
    """Display the server ELO leaderboard (only works in #leaderboard channel)"""
    global leaderboard_auto_update_data
    
    # Strict check: must be exactly "leaderboard" channel (case-insensitive)
    channel_name_lower = ctx.channel.name.lower()
    
    if channel_name_lower != 'leaderboard':
        await ctx.send(f"❌ The `.leaderboard` command can only be used in the #leaderboard channel! (Current channel: #{ctx.channel.name})")
        return
    
    str_guild_id = str(ctx.guild.id)
    
    # Only delete old leaderboard messages if they exist from previous .leaderboard call
    if str_guild_id in leaderboard_auto_update_data:
        old_data = leaderboard_auto_update_data[str_guild_id]
        if old_data['channel_id'] == ctx.channel.id:
            # Delete only the previous leaderboard messages
            for msg_id in old_data['message_ids']:
                try:
                    msg = await ctx.channel.fetch_message(msg_id)
                    await msg.delete()
                except:
                    pass
    
    players = db_manager.get_all_players(str(ctx.guild.id))
    
    # Filter out simulation players (IDs 1000-1999)
    active_players = []
    for p in players:
        try:
            player_id = int(p['discord_id'])
            if player_id < 1000 or player_id >= 2000:
                active_players.append(p)
        except (ValueError, TypeError):
            active_players.append(p)
    
    if not active_players:
        await ctx.send("No players found!")
        return
    
    # Sort by ELO (highest first)
    active_players.sort(key=lambda x: x['elo'], reverse=True)
    
    # Build player entries (format: #1 PlayerName 1850)
    entries = []
    
    for i, player in enumerate(active_players):
        discord_id = player['discord_id']
        elo = int(player['elo'])
        rank = i + 1
        
        # Try to get player name
        member = ctx.guild.get_member(int(discord_id))
        if member:
            name = member.display_name
        else:
            # Player left server, try database
            player_data = db_manager.get_player(discord_id, str(ctx.guild.id))
            name = player_data.get('display_name') or player_data.get('discord_name') or f"Player_{discord_id}"
            # Clean up discriminator
            if '#' in name:
                name = name.split('#')[0]
        
        # Truncate name if too long (max 8 chars for tight fit)
        if len(name) > 8:
            name = name[:5] + "..."
        
        entries.append({
            'rank': rank,
            'name': name,
            'elo': elo
        })
    
    # Build 3-column layout (going down columns instead of across)
    all_lines = []
    
    # Calculate how many rows we need (divide players into 3 columns)
    total_players = len(entries)
    rows_per_message = 60
    players_per_column = (total_players + 2) // 3  # Round up, divide by 3 columns
    
    # Build rows - each row has 3 players from different positions
    for row_idx in range(players_per_column):
        columns = []
        
        # Column 1: players 0, 1, 2, 3... (top of column 1)
        # Column 2: players N, N+1, N+2... (top of column 2)  
        # Column 3: players 2N, 2N+1, 2N+2... (top of column 3)
        for col_idx in range(3):
            player_idx = row_idx + (col_idx * players_per_column)
            
            if player_idx < total_players:
                entry = entries[player_idx]
                rank_str = f"#{entry['rank']}".ljust(4)      # "#1  " (4 chars)
                name_str = entry['name'].ljust(8)             # "Name    " (8 chars)
                elo_str = str(entry['elo']).ljust(4)          # "1850" (4 chars)
                
                # Total per column: 16 chars fixed
                column = f"{rank_str}{name_str}{elo_str}"
                columns.append(column)
            else:
                # Empty column if we run out of players
                columns.append(" " * 16)
        
        # Join columns with 2 spaces between (16+2+16+2+16 = 52 chars total)
        line = "  ".join(columns)
        all_lines.append(line.rstrip())  # Remove trailing spaces from incomplete rows
    
    # Split into chunks (60 lines per message = 180 players!)
    chunk_size = 60
    chunks = [all_lines[i:i + chunk_size] for i in range(0, len(all_lines), chunk_size)]
    
    # Send embeds and store message IDs for auto-update
    leaderboard_message_ids = []
    
    for chunk_idx, chunk in enumerate(chunks):
        # Join lines with newlines
        chunk_text = "\n".join(chunk)
        
        embed = discord.Embed(
            title="🏆 Server ELO Leaderboard" if chunk_idx == 0 else f"🏆 Leaderboard (continued)",
            description=f"```\n{chunk_text}\n```",
            color=discord.Color.gold()
        )
        
        if chunk_idx == 0:
            current_time = datetime.now()
            embed.set_footer(
                text=f"Total Players: {len(active_players)} • Last Updated: {current_time.strftime('%I:%M %p')}"
            )
        
        msg = await ctx.send(embed=embed)
        leaderboard_message_ids.append(msg.id)
    
    # Store message IDs and channel ID for auto-update
    leaderboard_auto_update_data[str_guild_id] = {
        'channel_id': ctx.channel.id,
        'message_ids': leaderboard_message_ids,
        'last_update': datetime.now()
    }

async def update_leaderboard(guild_id):
    """Auto-update the leaderboard when ELOs change"""
    try:
        str_guild_id = str(guild_id)
        
        print(f"🔄 update_leaderboard called for guild {str_guild_id}")
        
        # Check if leaderboard exists for this server
        if str_guild_id not in leaderboard_auto_update_data:
            print(f"⚠️ No leaderboard data found for guild {str_guild_id}")
            return
        
        data = leaderboard_auto_update_data[str_guild_id]
        channel_id = data['channel_id']
        message_ids = data['message_ids']
        
        print(f"📊 Leaderboard found - Channel: {channel_id}, Messages: {len(message_ids)}")
        
        # Get the channel
        channel = bot.get_channel(channel_id)
        if not channel:
            print(f"❌ Could not find channel {channel_id}")
            return
        
        # Get updated player list
        players = db_manager.get_all_players(str_guild_id)
        
        # Filter out simulation players
        active_players = []
        for p in players:
            try:
                player_id = int(p['discord_id'])
                if player_id < 1000 or player_id >= 2000:
                    active_players.append(p)
            except (ValueError, TypeError):
                active_players.append(p)
        
        if not active_players:
            return
        
        # Sort by ELO
        active_players.sort(key=lambda x: x['elo'], reverse=True)
        
        # Build player entries
        entries = []
        guild = bot.get_guild(int(guild_id))
        
        for i, player in enumerate(active_players):
            discord_id = player['discord_id']
            elo = int(player['elo'])
            rank = i + 1
            
            # Get player name
            if guild:
                member = guild.get_member(int(discord_id))
                if member:
                    name = member.display_name
                else:
                    player_data = db_manager.get_player(discord_id, str_guild_id)
                    name = player_data.get('display_name') or player_data.get('discord_name') or f"Player_{discord_id}"
                    if '#' in name:
                        name = name.split('#')[0]
            else:
                name = f"Player_{discord_id}"
            
            # Truncate name if too long (max 8 chars)
            if len(name) > 8:
                name = name[:5] + "..."
            
            entries.append({
                'rank': rank,
                'name': name,
                'elo': elo
            })
        
        # Build 3-column layout (going down columns)
        all_lines = []
        
        total_players = len(entries)
        players_per_column = (total_players + 2) // 3
        
        for row_idx in range(players_per_column):
            columns = []
            
            for col_idx in range(3):
                player_idx = row_idx + (col_idx * players_per_column)
                
                if player_idx < total_players:
                    entry = entries[player_idx]
                    rank_str = f"#{entry['rank']}".ljust(4)
                    name_str = entry['name'].ljust(8)
                    elo_str = str(entry['elo']).ljust(4)
                    
                    column = f"{rank_str}{name_str}{elo_str}"
                    columns.append(column)
                else:
                    columns.append(" " * 16)
            
            line = "  ".join(columns)
            all_lines.append(line.rstrip())
        
        # Split into chunks of 60 lines
        chunk_size = 60
        chunks = [all_lines[i:i + chunk_size] for i in range(0, len(all_lines), chunk_size)]
        
        # Update existing messages
        for chunk_idx, chunk in enumerate(chunks):
            if chunk_idx < len(message_ids):
                try:
                    msg = await channel.fetch_message(message_ids[chunk_idx])
                    chunk_text = "\n".join(chunk)
                    
                    embed = discord.Embed(
                        title="🏆 Server ELO Leaderboard" if chunk_idx == 0 else f"🏆 Leaderboard (continued)",
                        description=f"```\n{chunk_text}\n```",
                        color=discord.Color.gold()
                    )
                    
                    if chunk_idx == 0:
                        current_time = datetime.now()
                        embed.set_footer(
                            text=f"Total Players: {len(active_players)} • Last Updated: {current_time.strftime('%I:%M %p')}"
                        )
                    
                    await msg.edit(embed=embed)
                    print(f"✅ Updated leaderboard message {chunk_idx + 1}/{len(message_ids)}")
                except discord.NotFound:
                    print(f"❌ Leaderboard message {chunk_idx} not found (deleted?)")
                except discord.Forbidden:
                    print(f"❌ No permission to edit leaderboard message {chunk_idx}")
                except Exception as e:
                    print(f"❌ Error updating leaderboard message {chunk_idx}: {e}")
        
        # Update last update time
        leaderboard_auto_update_data[str_guild_id]['last_update'] = datetime.now()
        print(f"✅ Leaderboard auto-update completed for guild {str_guild_id}")
        
    except Exception as e:
        print(f"❌ Error in update_leaderboard: {e}")
        import traceback
        traceback.print_exc()

@bot.command(name='promote', aliases=['spam'])
async def promote_pugs(ctx):
    """Promote active PUGs showing remaining spots (3-minute cooldown)"""
    server_id = str(ctx.guild.id)
    
    # Check cooldown
    if server_id in promote_cooldowns:
        last_use = promote_cooldowns[server_id]
        time_since = datetime.now() - last_use
        cooldown_seconds = 180  # 3 minutes
        
        if time_since.total_seconds() < cooldown_seconds:
            remaining = cooldown_seconds - time_since.total_seconds()
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            await ctx.send(f"⏰ Promote command is on cooldown! Try again in {minutes}m {seconds}s")
            return
    
    channel_queues = get_channel_queues(ctx.channel)
    
    if not channel_queues:
        await ctx.send("📊 No active PUGs in this channel!")
        return
    
    embed = discord.Embed(title="🎮 Active PUGs - Join Now!", color=discord.Color.green())
    
    for queue_key, queue in channel_queues.items():
        mode_data = db_manager.get_game_mode(queue.game_mode_name)
        spots_filled = len(queue.queue)
        spots_remaining = queue.team_size - spots_filled
        
        # Only show queues that have players AND have spots remaining
        if spots_filled > 0 and spots_remaining > 0:
            status = f"**{spots_filled}/{queue.team_size}** players ({spots_remaining} spots remaining)"
            join_cmd = f"`.j {mode_data['name']}`" if queue.game_mode_name != 'default' else "`.j TAM4`"
            embed.add_field(
                name=f"🎯 {mode_data['name']} ({queue.max_per_team}v{queue.max_per_team})",
                value=f"{status}\nJoin: {join_cmd}",
                inline=False
            )
    
    if len(embed.fields) == 0:
        await ctx.send("📊 No active PUGs with open spots!")
    else:
        # Set cooldown
        promote_cooldowns[server_id] = datetime.now()
        await ctx.send("@here", embed=embed)

@bot.command(name='deadpug')
async def deadpug_vote(ctx):
    """Vote to cancel the last PUG you played in"""
    # Find the player's most recent PUG
    recent_pugs = db_manager.get_recent_pugs(10)
    
    player_pug = None
    for pug in recent_pugs:
        if str(ctx.author.id) in pug['red_team'] or str(ctx.author.id) in pug['blue_team']:
            player_pug = pug
            break
    
    if not player_pug:
        await ctx.send("❌ You haven't played in any recent PUGs!")
        return
    
    if player_pug.get('winner'):
        await ctx.send(f"❌ PUG #{player_pug['number']} already has a winner! Use admin `.forcedeadpug {player_pug['number']}` if needed.")
        return
    
    if player_pug.get('status') == 'killed':
        await ctx.send(f"❌ PUG #{player_pug['number']} is already cancelled!")
        return
    
    # Start voting
    all_players = player_pug['red_team'] + player_pug['blue_team']
    votes_needed = len(all_players) // 2 + 1
    
    # Create vote message
    vote_msg = await ctx.send(
        f"🗳️ **Deadpug Vote Started for PUG #{player_pug['number']}**\n"
        f"Players in this PUG, react with ✅ to vote to cancel.\n"
        f"Requires **{votes_needed}/{len(all_players)}** votes to pass.\n"
        f"Vote ends in 60 seconds or when majority is reached."
    )
    
    # Add reactions
    await vote_msg.add_reaction("✅")
    await vote_msg.add_reaction("❌")
    
    # Monitor reactions for 60 seconds
    start_time = asyncio.get_event_loop().time()
    timeout = 60
    
    try:
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            remaining = timeout - elapsed
            
            if remaining <= 0:
                break
            
            # Check current vote count
            vote_msg = await ctx.channel.fetch_message(vote_msg.id)
            yes_votes = 0
            
            for reaction in vote_msg.reactions:
                if str(reaction.emoji) == "✅":
                    users = [user async for user in reaction.users()]
                    yes_votes = sum(1 for user in users if not user.bot and str(user.id) in all_players)
                    break
            
            # If majority reached, end voting immediately
            if yes_votes >= votes_needed:
                db_manager.delete_pug(player_pug['pug_id'])
                await ctx.send(f"✅ **Vote passed! PUG #{player_pug['number']} has been cancelled.** ({yes_votes}/{len(all_players)} votes)")
                return
            
            # Wait a bit before checking again (every 2 seconds)
            await asyncio.sleep(min(2, remaining))
        
        # Timeout reached, count final votes
        vote_msg = await ctx.channel.fetch_message(vote_msg.id)
        yes_votes = 0
        
        for reaction in vote_msg.reactions:
            if str(reaction.emoji) == "✅":
                users = [user async for user in reaction.users()]
                yes_votes = sum(1 for user in users if not user.bot and str(user.id) in all_players)
                break
        
        if yes_votes >= votes_needed:
            db_manager.delete_pug(player_pug['pug_id'])
            await ctx.send(f"✅ **Vote passed! PUG #{player_pug['number']} has been cancelled.** ({yes_votes}/{len(all_players)} votes)")
        else:
            await ctx.send(f"❌ **Vote failed.** Only {yes_votes}/{votes_needed} votes received. PUG #{player_pug['number']} stands.")
    
    except Exception as e:
        await ctx.send(f"⚠️ Error during voting: {e}")


@bot.command(name='forcedeadpug')
async def force_deadpug(ctx, pug_id: int):
    """Force cancel a PUG by ID (Admin/PugAdmin only)"""
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Get the PUG
    recent_pugs = db_manager.get_recent_pugs(100)
    target_pug = None
    for pug in recent_pugs:
        if pug['number'] == pug_id:
            target_pug = pug
            break
    
    if not target_pug:
        await ctx.send(f"❌ Could not find PUG #{pug_id}!")
        return
    
    if target_pug.get('winner'):
        await ctx.send(f"❌ PUG #{pug_id} already has a winner and cannot be cancelled!")
        return
    
    # Get the actual pug_id from the database
    actual_pug_id = target_pug.get('pug_id')
    
    # Mark as killed instead of deleting
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE pugs SET status = 'killed' WHERE pug_id = ?", (actual_pug_id,))
    conn.commit()
    conn.close()
    
    await ctx.send(f"✅ **PUG #{pug_id} has been cancelled!** ELO changes have been prevented.")

@bot.command(name='undodeadpug')
async def undo_deadpug(ctx, pug_number: int):
    """Restore a cancelled PUG back to awaiting result (Admin only)
    
    Usage: .undodeadpug 5
    """
    if not is_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    # Find the PUG
    recent_pugs = db_manager.get_recent_pugs(100)
    pug = None
    for p in recent_pugs:
        if p['number'] == pug_number:
            pug = p
            break
    
    if not pug:
        await ctx.send(f"❌ Could not find PUG #{pug_number}!")
        return
    
    if pug.get('status') != 'killed':
        await ctx.send(f"❌ PUG #{pug_number} is not cancelled/dead! Current status: {pug.get('status', 'active')}")
        return
    
    if pug.get('winner'):
        await ctx.send(f"❌ PUG #{pug_number} has a winner ({pug['winner'].upper()} team)! Use `.undowinner {pug_number}` first if needed.")
        return
    
    # Restore the PUG to active status
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE pugs SET status = 'active' WHERE pug_id = ?", (pug['pug_id'],))
    conn.commit()
    conn.close()
    
    # Show teams
    embed = discord.Embed(
        title=f"↩️ PUG #{pug_number} Restored",
        description=f"PUG has been restored from cancelled status",
        color=discord.Color.green()
    )
    
    red_team = "\n".join([f"<@{uid}>" for uid in pug['red_team']])
    blue_team = "\n".join([f"<@{uid}>" for uid in pug['blue_team']])
    
    embed.add_field(name="🔴 Red Team", value=red_team, inline=True)
    embed.add_field(name="🔵 Blue Team", value=blue_team, inline=True)
    
    if pug.get('avg_red_elo') and pug.get('avg_blue_elo'):
        embed.add_field(
            name="Average ELO", 
            value=f"🔴 Red: {pug['avg_red_elo']:.0f}\n🔵 Blue: {pug['avg_blue_elo']:.0f}", 
            inline=False
        )
    
    embed.add_field(
        name="Next Steps",
        value=f"Players can now vote with `.winner red` or `.winner blue`",
        inline=False
    )
    
    await ctx.send(embed=embed)

@bot.command(name='help', aliases=['commands'])
async def help_command(ctx):
    """Show all available commands"""
    is_user_admin = is_full_admin(ctx)
    is_user_pugadmin = is_pug_admin(ctx)
    
    # Player commands (shown to everyone)
    player_embed = discord.Embed(title="🎮 PUG Bot Commands", color=discord.Color.green())
    
    player_embed.add_field(name="**Pug Commands**", value="""
`.j TAM4` or `.J TAM4` - Join the 4v4 pug
`.j <mode>` - Join a specific game mode (e.g., .j 6v6)
`.j` - Join ALL active queues with players
`++` or `.++` - Join ALL pugs with 1+ players
`++ <mode>` - Join specific mode (if 1+ players)
`.leave [mode]` / `.l [mode]` - Leave pug(s)
`--` or `.--` - Leave ALL pugs
`.lva` - Leave ALL pugs
`.expire 10m [mode]` - Auto-remove after time (e.g., 30m, 1h)
`.cancelexpire [mode]` - Cancel your expire timer
`.list [mode]` / `.who [mode]` - Show pug players + waiting list
`.list4v4` / `.list2v2` / etc - Show specific mode queue
`.modes` - Show all available game modes
`.register` - Register for PUG tracking (REQUIRED before joining)
`.promote` / `.spam` - Show all active PUGs with open spots (3min cooldown)
    """, inline=False)
    
    player_embed.add_field(name="**Captain Commands**", value="""
`.captain` - Become a captain
`.capfor red-team` / `.capfor blue-team` - Takeover captain spot
`.pick <number>` or `.p <number>` - Pick a player by number (e.g., .p 3)
`.pick <number> <number>` or `.p <n> <n>` - Pick 2 players during double pick (e.g., .p 3 5)
`.pick <name>` - Pick a player by name
    """, inline=False)
    
    player_embed.add_field(name="**Stats Commands**", value="""
`.mystats` - View your statistics
`.stats @player` / `.stats PlayerName` - View another player's stats
`.topelo` - Top 10 ELO players
`.top10` - Top 10 most active players
`.leaderboard` - Full ELO leaderboard (only in #leaderboard channel)
`.playerelos` - DM list of all player ELOs
`.longestwin` / `.beststreak` - Player with longest winning streak
`.longestloss` / `.worststreak` - Player with longest losing streak
`.last` - View most recent PUG (shows PUG ID & tiebreaker)
`.mylast` - View your most recent PUG (shows PUG ID)
`.last @player` - View a player's most recent PUG (shows PUG ID)
`.lastt` / `.lasttt` - View 2nd/3rd most recent PUG
    """, inline=False)
    
    player_embed.add_field(name="**Match Result Commands**", value="""
`.winner red` / `.winner blue` - Vote for team win (50%+1 required)
`.deadpug` - Vote to cancel your last PUG
    """, inline=False)
    
    player_embed.add_field(name="**External Stats Integration**", value="""
`.linkstats <name>` - Link your UT2K4 player account
`.gamestats [@user]` - View UT2K4 stats
    """, inline=False)
    
    # If player, send via DM
    if not is_user_admin and not is_user_pugadmin:
        try:
            # Split into two embeds to avoid Discord's size limits
            embed1 = discord.Embed(title="🎮 PUG Bot Commands (1/2)", color=discord.Color.green())
            embed1.add_field(name="**Pug Commands**", value=player_embed.fields[0].value, inline=False)
            embed1.add_field(name="**Captain Commands**", value=player_embed.fields[1].value, inline=False)
            embed1.add_field(name="**Stats Commands**", value=player_embed.fields[2].value, inline=False)
            
            embed2 = discord.Embed(title="🎮 PUG Bot Commands (2/2)", color=discord.Color.green())
            embed2.add_field(name="**Match Result Commands**", value=player_embed.fields[3].value, inline=False)
            embed2.add_field(name="**External Stats Integration**", value=player_embed.fields[4].value, inline=False)
            
            await ctx.author.send(embed=embed1)
            await ctx.author.send(embed=embed2)
            await ctx.send(f"✅ {ctx.author.mention}, I've sent you a DM with available commands!")
        except discord.Forbidden:
            # User has DMs disabled
            await ctx.send(f"⚠️ {ctx.author.mention}, I couldn't DM you (your DMs are disabled). Here are the commands:")
            await ctx.send(embed=player_embed)
        except discord.HTTPException as e:
            # Discord API error
            print(f"HTTPException sending DM: {e}")
            await ctx.send(f"⚠️ Discord error sending DM (Code: {e.code}). Here are the commands:")
            await ctx.send(embed=player_embed)
        except Exception as e:
            # Other error, send in channel
            print(f"Error sending help DM: {type(e).__name__}: {e}")
            await ctx.send(f"⚠️ Error: {type(e).__name__}. Here are the commands:")
            await ctx.send(embed=player_embed)
        return
    
    # Admin/PugAdmin commands - send via DM
    admin_embed = discord.Embed(title="🎮 PUG Bot Commands (Admin)", color=discord.Color.gold())
    
    # Copy player commands to admin embed
    admin_embed.add_field(name="**Pug Commands**", value=player_embed.fields[0].value, inline=False)
    admin_embed.add_field(name="**Captain Commands**", value=player_embed.fields[1].value, inline=False)
    admin_embed.add_field(name="**Stats Commands**", value=player_embed.fields[2].value, inline=False)
    admin_embed.add_field(name="**Match Result Commands**", value=player_embed.fields[3].value, inline=False)
    admin_embed.add_field(name="**External Stats Integration**", value=player_embed.fields[4].value, inline=False)
    
    # PUG Admin commands - Part 1 (Queue & Player Management)
    admin_embed.add_field(name="**PUG Admin - Queue Management**", value="""
`.reset [mode]` - Reset the pug (back to captain selection)
`.autopick [mode]` / `.autopickoff [mode]` - Auto team balancing
`.skipreadycheck [mode]` - Skip ready check phase
`.addplayer @Player [mode]` - Add player to queue (supports @mention)
`.removeplayer @Player [mode]` - Remove player from queue (supports @mention)
`.timeout @Player 30M` - Timeout player (supports @mention, 5m/30m/1h/24h/7d)
`.setelo @Player 1500` - Set player ELO (supports @mention, 0-3000)
`.setpugs @Player 150` - Set player total PUG count (doesn't affect W/L/ELO)
`.sim [mode]` / `.simoff [mode]` - Simulation mode with fake players
    """, inline=False)
    
    # PUG Admin commands - Part 2 (Team & Picking Management)
    admin_embed.add_field(name="**PUG Admin - Team Management**", value="""
`.pickforred <number/name>` - Pick for red (can pick 2: .pickforred 3 5)
`.pickforblue <number/name>` - Pick for blue (can pick 2)
`.undopickforred <number/name>` - Undo pick from red team
`.undopickforblue <number/name>` - Undo pick from blue team
`.setcaptainred @Player` - Set red captain (supports @mention)
`.setcaptainblue @Player` - Set blue captain (supports @mention)
    """, inline=False)
    
    # PUG Admin commands - Part 3 (Mode & Match Management)
    admin_embed.add_field(name="**PUG Admin - Mode & Match Management**", value="""
`.addmode name size [desc]` - Add game mode (e.g., .addmode 6v6 12 "Large")
`.removemode name` - Remove game mode
`.addalias <mode> <alias>` - Add alias (e.g., .addalias 2v2 duos)
`.removealias <alias>` - Remove mode alias
`.aliases [mode]` - Show mode aliases
`.addmap <name>` - Add map to tiebreaker pool
`.removemap <name>` - Remove map from tiebreaker pool
`.maps` / `.maplist` - Show all tiebreaker maps with cooldown status
`.forcedeadpug <pug_id>` - Force cancel specific PUG
`.undodeadpug <pug_id>` - Restore cancelled PUG
    """, inline=False)
    
    # Full Admin only commands
    if is_user_admin:
        admin_embed.add_field(name="**Admin Only Commands - Part 1**", value="""
`.tamproon` / `.tamprooff` - Enable/disable bot
`.status` - Show bot status & statistics
`.exportstats` - Export player stats as CSV (DMs admin)
`.importelos` - Import ELO updates from CSV (attach file)
`.exportelos` - Export all ELOs to CSV
`.examplepugcsv` - Generate template CSV for PUG count updates
`.updateplayerpugs` - Bulk add PUG counts from CSV (attach file)
`.undoupdateplayerpugs` - Undo last PUG count update
`.setpugs @Player 150` - Set player's total PUG count
`.setpeak @Player 1500` - Set player's peak ELO
`.reseteloall` - Reset ALL players to 1000 ELO
`.deleteplayer @Player` - Permanently delete player from database
    """, inline=False)
        
        admin_embed.add_field(name="**Admin Only Commands - Part 2**", value="""
`.enablescrape` / `.disablescrape` - Control UT2K4 scraping
`.scrapestatus` - Check UT2K4 scraping status
`.dmon` / `.dmoff` - Enable/disable queue full DM notifications
`.addpugadmin @Player` - Add PUG Admin role (supports @mention)
`.removepugadmin @Player` - Remove PUG Admin role (supports @mention)
`.showpugadmins` - Show all PUG Admins (server-specific)
`.undowinner [pug_id]` - Reset PUG winner (allows re-voting)
`.setwinner <pug_id> <team>` - Set specific PUG winner (override)
`.cleanduplicates` - Remove duplicate topelo entries
`.cleartopelo` - Clear all topelo entries
    """, inline=False)
    
    admin_embed.add_field(name="**Usage Examples**", value="""
`.register` - Required before joining any queue
`.j` - Join all active queues with players
`.j TAM4` - Join 4v4 pug
`.j 6v6` - Join 6v6 pug (joins waiting list if full)
`.expire 30m` - Auto-remove in 30 minutes
`.cancelexpire` - Cancel your timer
`++` - Join ALL active pugs
`.spam` - Promote active pugs (@here ping, 3min cooldown)
`.winner blue` - Vote for blue win (players vote, admins instant)
`.setelo @NewPlayer 1200` - Set new player's starting ELO
`.setpugs @Player 150` - Set historical PUG count
`.addmap DM-Deck16` - Add tiebreaker map
`.undopickforred 2` - Undo red team pick position 2
`.setwinner 145 red` - Set PUG #145 winner to red team
    """, inline=False)
    
    # Send DM to admin in multiple embeds to avoid size limits
    try:
        # Embed 1: Player commands
        embed1 = discord.Embed(title="🎮 PUG Bot Commands - Player (1/3)", color=discord.Color.gold())
        embed1.add_field(name="**Pug Commands**", value=player_embed.fields[0].value, inline=False)
        embed1.add_field(name="**Captain Commands**", value=player_embed.fields[1].value, inline=False)
        embed1.add_field(name="**Stats Commands**", value=player_embed.fields[2].value, inline=False)
        embed1.add_field(name="**Match Result Commands**", value=player_embed.fields[3].value, inline=False)
        embed1.add_field(name="**External Stats Integration**", value=player_embed.fields[4].value, inline=False)
        
        # Embed 2: PUG Admin commands
        embed2 = discord.Embed(title="🎮 PUG Bot Commands - PUG Admin (2/3)", color=discord.Color.gold())
        embed2.add_field(name="**PUG Admin - Queue Management**", value=admin_embed.fields[5].value, inline=False)
        embed2.add_field(name="**PUG Admin - Team Management**", value=admin_embed.fields[6].value, inline=False)
        embed2.add_field(name="**PUG Admin - Mode & Match Management**", value=admin_embed.fields[7].value, inline=False)
        
        # Embed 3: Full Admin commands (if admin)
        if is_user_admin:
            embed3 = discord.Embed(title="🎮 PUG Bot Commands - Admin (3/3)", color=discord.Color.gold())
            embed3.add_field(name="**Admin Only Commands - Part 1**", value=admin_embed.fields[8].value, inline=False)
            embed3.add_field(name="**Admin Only Commands - Part 2**", value=admin_embed.fields[9].value, inline=False)
            embed3.add_field(name="**Usage Examples**", value=admin_embed.fields[10].value, inline=False)
            
            await ctx.author.send(embed=embed1)
            await ctx.author.send(embed=embed2)
            await ctx.author.send(embed=embed3)
        else:
            # PUG Admin only - no full admin commands
            await ctx.author.send(embed=embed1)
            await ctx.author.send(embed=embed2)
        
        await ctx.send(f"✅ {ctx.author.mention}, I've sent you a DM with all available commands!")
    except discord.Forbidden:
        # User has DMs disabled
        await ctx.send(f"⚠️ {ctx.author.mention}, I couldn't DM you (your DMs are disabled). Here are the commands:")
        await ctx.send(embed=admin_embed)
    except discord.HTTPException as e:
        # Discord API error
        print(f"HTTPException sending admin DM: {e}")
        await ctx.send(f"⚠️ Discord error sending DM (Code: {e.code}). Here are the commands:")
        await ctx.send(embed=admin_embed)
    except Exception as e:
        # Other error, send in channel
        print(f"Error sending admin help DM: {type(e).__name__}: {e}")
        await ctx.send(f"⚠️ Error: {type(e).__name__}. Here are the commands:")
        await ctx.send(embed=admin_embed)

@bot.command(name='tamproon')
async def tampro_on(ctx):
    """Enable the bot (Admin only)"""
    if not is_full_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    global bot_enabled
    bot_enabled = True
    await ctx.send("✅ **TAM PRO Bot is now ONLINE!** Commands are now active.")

@bot.command(name='tamprooff')
async def tampro_off(ctx):
    """Disable the bot (Admin only)"""
    if not is_full_admin(ctx):
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    global bot_enabled
    bot_enabled = False
    await ctx.send("⚠️ **TAM PRO Bot is now OFFLINE!** Commands are disabled.")

# Run the bot
if __name__ == '__main__':
    # Check if token is configured
    if BOT_TOKEN == "your-bot-token-here":
        print("=" * 70)
        print("❌ ERROR: Bot token not configured!")
        print("=" * 70)
        print("Please edit pug_bot.py and set your Discord bot token:")
        print("  1. Find the line: BOT_TOKEN = \"your-bot-token-here\"")
        print("  2. Replace with:  BOT_TOKEN = \"paste-your-actual-token-here\"")
        print("")
        print("Get your bot token from: https://discord.com/developers/applications")
        print("=" * 70)
        exit(1)
    
    print("=" * 70)
    print("PUG Pro Discord Bot - Starting...")
    print("Developed by: fallacy")
    print("For: Competitive Gaming Communities")
    print("=" * 70)
    print("")
    
    bot.run(BOT_TOKEN)
