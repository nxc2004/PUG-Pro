"""
PUG Pro Discord Bot - Database Manager

A customizable version of the TAM Pro Bot
Originally developed for the UT2004 Unreal Fight Club Discord Community

Developed by: fallacy

Bot made for Competitive Gaming Communities to use for Pick Up Games (PUGs)
Any questions? Please message fallacy on Discord.
"""

import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Tuple
import json

class DatabaseManager:
    def __init__(self, db_path='pug_data.db'):
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        """Get a database connection"""
        return sqlite3.connect(self.db_path)
    
    def init_database(self):
        """Initialize the database schema"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Players table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS players (
                discord_id TEXT,
                server_id TEXT,
                discord_name TEXT,
                display_name TEXT,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                total_pugs INTEGER DEFAULT 0,
                elo REAL DEFAULT 1000,
                ut2k4_player_name TEXT,
                ut2k4_last_scraped TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (discord_id, server_id)
            )
        ''')
        
        # Migration: Add discord_name and display_name columns if they don't exist
        try:
            cursor.execute("SELECT discord_name FROM players LIMIT 1")
        except:
            print("⚠️  Adding discord_name and display_name columns to players table...")
            cursor.execute("ALTER TABLE players ADD COLUMN discord_name TEXT")
            cursor.execute("ALTER TABLE players ADD COLUMN display_name TEXT")
            conn.commit()
            print("✅ Added discord_name and display_name columns")
        
        # Migration: Add server_id to players if it doesn't exist
        try:
            cursor.execute("SELECT server_id FROM players LIMIT 1")
        except:
            # Column doesn't exist, need to migrate
            print("⚠️  Migrating players table to add server_id...")
            
            # Get existing players
            cursor.execute("SELECT discord_id, wins, losses, total_pugs, elo, ut2k4_player_name, ut2k4_last_scraped, created_at FROM players")
            old_players = cursor.fetchall()
            
            # Drop and recreate table
            cursor.execute("DROP TABLE IF EXISTS players")
            cursor.execute('''
                CREATE TABLE players (
                    discord_id TEXT,
                    server_id TEXT,
                    wins INTEGER DEFAULT 0,
                    losses INTEGER DEFAULT 0,
                    total_pugs INTEGER DEFAULT 0,
                    elo REAL DEFAULT 700,
                    ut2k4_player_name TEXT,
                    ut2k4_last_scraped TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (discord_id, server_id)
                )
            ''')
            
            conn.commit()
            print(f"✅ Players table migrated. Old player data cleared (ELOs are now server-specific)")
            print(f"   Players will be re-created as they join queues")

        # Migration: Add current_streak column if it doesn't exist
        try:
            cursor.execute("SELECT current_streak FROM players LIMIT 1")
        except:
            print("⚠️  Adding current_streak column to players table...")
            cursor.execute("ALTER TABLE players ADD COLUMN current_streak INTEGER DEFAULT 0")
            conn.commit()
            print("✅ Added current_streak column")
        
        # Migration: Add peak_elo column if it doesn't exist
        try:
            cursor.execute("SELECT peak_elo FROM players LIMIT 1")
        except:
            print("⚠️  Adding peak_elo column to players table...")
            cursor.execute("ALTER TABLE players ADD COLUMN peak_elo REAL DEFAULT 1000")
            # Update existing players' peak_elo to their current ELO
            cursor.execute("UPDATE players SET peak_elo = elo WHERE peak_elo IS NULL OR peak_elo < elo")
            conn.commit()
            print("✅ Added peak_elo column")
        
        # Migration already completed - peak_elo values have been reset
        # Skipping to avoid UNIQUE constraint error
        reset_done = True  # Force skip
        
        # if not reset_done:
        #     print("⚠️  Resetting all peak_elo values to current ELO (one-time fix)...")
        #     cursor.execute("UPDATE players SET peak_elo = elo")
        #     fixed_count = cursor.rowcount
        #     cursor.execute("INSERT INTO migrations (name) VALUES ('reset_peak_v2')")
        #     conn.commit()
        #     print(f"✅ Reset peak_elo for {fixed_count} player(s) - will track correctly going forward")
        
        # Migration: Add registered column if it doesn't exist
        try:
            cursor.execute("SELECT registered FROM players LIMIT 1")
        except:
            print("⚠️  Adding registered column to players table...")
            cursor.execute("ALTER TABLE players ADD COLUMN registered INTEGER DEFAULT 0")
            # Mark existing players (who have played PUGs) as registered
            cursor.execute("UPDATE players SET registered = 1 WHERE total_pugs > 0")
            conn.commit()
            print("✅ Added registered column")
        
        # Migration: Add best_win_streak column if it doesn't exist
        try:
            cursor.execute("SELECT best_win_streak FROM players LIMIT 1")
        except:
            print("⚠️  Adding best_win_streak column to players table...")
            cursor.execute("ALTER TABLE players ADD COLUMN best_win_streak INTEGER DEFAULT 0")
            conn.commit()
            print("✅ Added best_win_streak column")
        
        # Migration: Add best_loss_streak column if it doesn't exist
        try:
            cursor.execute("SELECT best_loss_streak FROM players LIMIT 1")
        except:
            print("⚠️  Adding best_loss_streak column to players table...")
            cursor.execute("ALTER TABLE players ADD COLUMN best_loss_streak INTEGER DEFAULT 0")
            conn.commit()
            print("✅ Added best_loss_streak column")
        
        # PUGs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pugs (
                pug_id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_mode TEXT NOT NULL,
                winner TEXT,
                avg_red_elo REAL,
                avg_blue_elo REAL,
                status TEXT DEFAULT 'active',
                tiebreaker_map TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Migration: Add status column if it doesn't exist (for existing databases)
        try:
            cursor.execute("SELECT status FROM pugs LIMIT 1")
        except:
            # Column doesn't exist, add it
            cursor.execute("ALTER TABLE pugs ADD COLUMN status TEXT DEFAULT 'active'")
            conn.commit()
            print("✅ Database migration: Added 'status' column to pugs table")
        
        # Migration: Add tiebreaker_map column if it doesn't exist
        try:
            cursor.execute("SELECT tiebreaker_map FROM pugs LIMIT 1")
        except:
            cursor.execute("ALTER TABLE pugs ADD COLUMN tiebreaker_map TEXT")
            conn.commit()
            print("✅ Database migration: Added 'tiebreaker_map' column to pugs table")
        
        # PUG teams table (many-to-many relationship)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pug_teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pug_id INTEGER NOT NULL,
                discord_id TEXT NOT NULL,
                team TEXT NOT NULL,
                FOREIGN KEY (pug_id) REFERENCES pugs (pug_id),
                FOREIGN KEY (discord_id) REFERENCES players (discord_id)
            )
        ''')
        
        # Timeouts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS timeouts (
                discord_id TEXT PRIMARY KEY,
                timeout_end TEXT NOT NULL,
                FOREIGN KEY (discord_id) REFERENCES players (discord_id)
            )
        ''')
        
        # PUG Admins table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pug_admins (
                discord_id TEXT,
                server_id TEXT,
                PRIMARY KEY (discord_id, server_id)
            )
        ''')
        
        # Migration: Add server_id column if it doesn't exist
        try:
            cursor.execute("SELECT server_id FROM pug_admins LIMIT 1")
        except:
            # Column doesn't exist, need to migrate
            # Get existing admins
            cursor.execute("SELECT discord_id FROM pug_admins")
            old_admins = cursor.fetchall()
            
            # Drop and recreate table
            cursor.execute("DROP TABLE IF EXISTS pug_admins")
            cursor.execute('''
                CREATE TABLE pug_admins (
                    discord_id TEXT,
                    server_id TEXT,
                    PRIMARY KEY (discord_id, server_id)
                )
            ''')
            
            # Re-add old admins with a default server_id
            # Note: Old admins won't have server association - admins need to re-add them
            conn.commit()
            print("✅ Database migration: Added 'server_id' to pug_admins table")
            print("⚠️  Previous PUG admins were cleared - please re-add them per server")
        
        # Game Modes table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS game_modes (
                mode_name TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                team_size INTEGER NOT NULL,
                description TEXT
            )
        ''')
        
        # Mode Aliases table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mode_aliases (
                alias TEXT PRIMARY KEY,
                mode_name TEXT NOT NULL,
                FOREIGN KEY (mode_name) REFERENCES game_modes(mode_name) ON DELETE CASCADE
            )
        ''')
        
        # Bot Settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')
        
        # NOTE: No default game modes are created
        # Admins must create game modes with .addmode command
        # Example: .addmode 4v4 8 (creates a 4v4 mode with 8 total players)
        
        # Initialize scraping setting
        cursor.execute('''
            INSERT OR IGNORE INTO bot_settings (key, value)
            VALUES ('scraping_enabled', 'false')
        ''')
        
        # Initialize pug counter
        cursor.execute('''
            INSERT OR IGNORE INTO bot_settings (key, value)
            VALUES ('pug_counter', '0')
        ''')
        
        conn.commit()
        conn.close()
    
    # Player operations
    def get_player(self, discord_id: str, server_id: str = None) -> Dict:
        """Get player (server-scoped) - does NOT auto-create"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # If no server_id provided, this is an error in new system
        if not server_id:
            raise ValueError("server_id is required for get_player")
        
        cursor.execute('''
            SELECT discord_id, server_id, discord_name, display_name, 
                   wins, losses, total_pugs, elo, 
                   ut2k4_player_name, ut2k4_last_scraped, current_streak, registered, peak_elo
            FROM players 
            WHERE discord_id = ? AND server_id = ?
        ''', (str(discord_id), str(server_id)))
        row = cursor.fetchone()
        
        if row:
            player = {
                'discord_id': row[0],
                'server_id': row[1],
                'discord_name': row[2],
                'display_name': row[3],
                'wins': row[4],
                'losses': row[5],
                'total_pugs': row[6],
                'elo': row[7],
                'ut2k4_player_name': row[8],
                'ut2k4_last_scraped': row[9],
                'current_streak': row[10] if len(row) > 10 else 0,
                'registered': row[11] if len(row) > 11 else 0,
                'peak_elo': row[12] if len(row) > 12 else row[7]
            }
        else:
            player = None
        
        conn.close()
        return player
    
    def register_player(self, discord_id: str, server_id: str, discord_name: str = None, display_name: str = None) -> Dict:
        """Register a new player (creates with registered=1, elo needs to be set by admin)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Check if already exists
        existing = self.get_player(discord_id, server_id)
        if existing:
            # If already exists but not registered, mark as registered
            if not existing.get('registered'):
                cursor.execute('''
                    UPDATE players 
                    SET registered = 1
                    WHERE discord_id = ? AND server_id = ?
                ''', (str(discord_id), str(server_id)))
                conn.commit()
                existing['registered'] = 1
            conn.close()
            return existing
        
        # Create new registered player
        cursor.execute('''
            INSERT INTO players (discord_id, server_id, discord_name, display_name, wins, losses, total_pugs, elo, current_streak, registered, peak_elo)
            VALUES (?, ?, ?, ?, 0, 0, 0, 1000, 0, 1, NULL)
        ''', (str(discord_id), str(server_id), discord_name, display_name))
        conn.commit()
        
        player = {
            'discord_id': str(discord_id),
            'server_id': str(server_id),
            'discord_name': discord_name,
            'display_name': display_name,
            'wins': 0,
            'losses': 0,
            'total_pugs': 0,
            'elo': 1000.0,
            'ut2k4_player_name': None,
            'ut2k4_last_scraped': None,
            'current_streak': 0,
            'registered': 1,
            'peak_elo': None
        }
        
        conn.close()
        return player
    
    def player_exists(self, discord_id: str, server_id: str) -> bool:
        """Check if a player is registered without creating them"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT discord_id FROM players WHERE discord_id = ? AND server_id = ?', 
                      (str(discord_id), str(server_id)))
        exists = cursor.fetchone() is not None
        
        conn.close()
        return exists
    
    def update_player_names(self, discord_id: str, server_id: str, discord_name: str, display_name: str):
        """Update player's Discord username and display name"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE players 
            SET discord_name = ?, display_name = ?
            WHERE discord_id = ? AND server_id = ?
        ''', (discord_name, display_name, str(discord_id), str(server_id)))
        
        conn.commit()
        conn.close()
    
    def find_player_by_name(self, server_id: str, name: str) -> str:
        """Find a player's Discord ID by their Discord username or display name (case-insensitive)
        Returns discord_id if found, None otherwise"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT discord_id FROM players 
            WHERE server_id = ? 
            AND (LOWER(discord_name) = LOWER(?) OR LOWER(display_name) = LOWER(?))
            LIMIT 1
        ''', (str(server_id), name, name))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else None
    
    def delete_player(self, discord_id: str, server_id: str) -> bool:
        """Delete a player from the database (server-scoped)
        Returns True if player was deleted, False if player didn't exist"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Check if player exists
        cursor.execute('SELECT discord_id FROM players WHERE discord_id = ? AND server_id = ?', 
                      (str(discord_id), str(server_id)))
        exists = cursor.fetchone() is not None
        
        if exists:
            # Delete player
            cursor.execute('DELETE FROM players WHERE discord_id = ? AND server_id = ?', 
                          (str(discord_id), str(server_id)))
            conn.commit()
        
        conn.close()
        return exists
    
    def update_player_stats(self, discord_id: str, server_id: str, won: bool):
        """Update player win/loss stats and streak (server-scoped)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Get current streak and best streaks
        cursor.execute('''
            SELECT current_streak, best_win_streak, best_loss_streak 
            FROM players 
            WHERE discord_id = ? AND server_id = ?
        ''', (str(discord_id), str(server_id)))
        result = cursor.fetchone()
        current_streak = result[0] if result and result[0] is not None else 0
        best_win_streak = result[1] if result and len(result) > 1 and result[1] is not None else 0
        best_loss_streak = result[2] if result and len(result) > 2 and result[2] is not None else 0
        
        if won:
            # Win: increment positive streak or start new one
            new_streak = current_streak + 1 if current_streak >= 0 else 1
            
            # Update best win streak if this is a new record
            new_best_win = max(best_win_streak, new_streak)
            
            cursor.execute('''
                UPDATE players 
                SET wins = wins + 1, 
                    total_pugs = total_pugs + 1, 
                    current_streak = ?,
                    best_win_streak = ?
                WHERE discord_id = ? AND server_id = ?
            ''', (new_streak, new_best_win, str(discord_id), str(server_id)))
        else:
            # Loss: decrement negative streak or start new one
            new_streak = current_streak - 1 if current_streak <= 0 else -1
            
            # Update best loss streak if this is a new record (stored as positive number)
            new_best_loss = max(best_loss_streak, abs(new_streak))
            
            cursor.execute('''
                UPDATE players 
                SET losses = losses + 1, 
                    total_pugs = total_pugs + 1, 
                    current_streak = ?,
                    best_loss_streak = ?
                WHERE discord_id = ? AND server_id = ?
            ''', (new_streak, new_best_loss, str(discord_id), str(server_id)))
        
        conn.commit()
        conn.close()
    
    def update_player_elo(self, discord_id: str, server_id: str, new_elo: float):
        """Update player ELO and peak ELO if new high (server-scoped)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Update ELO and peak_elo
        # If peak_elo is NULL (first game), set it to new_elo
        # Otherwise, only update if new_elo is higher
        cursor.execute('''
            UPDATE players 
            SET elo = ?,
                peak_elo = CASE 
                    WHEN peak_elo IS NULL THEN ?
                    WHEN ? > peak_elo THEN ? 
                    ELSE peak_elo 
                END
            WHERE discord_id = ? AND server_id = ?
        ''', (new_elo, new_elo, new_elo, new_elo, str(discord_id), str(server_id)))
        
        conn.commit()
        conn.close()
    
    def update_ut2k4_info(self, discord_id: str, server_id: str, ut2k4_name: str):
        """Update player's UT2K4 name (server-scoped)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE players 
            SET ut2k4_player_name = ?, ut2k4_last_scraped = ?
            WHERE discord_id = ? AND server_id = ?
        ''', (ut2k4_name, datetime.now().isoformat(), str(discord_id), str(server_id)))
        
        conn.commit()
        conn.close()
    
    def update_player_total_pugs(self, discord_id: str, server_id: str, total_pugs: int) -> bool:
        """Update player's total PUG count without affecting ELO or win/loss (server-scoped)
        
        This is used for importing historical data from previous bots.
        Returns True if successful, False otherwise.
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Update only the total_pugs field
            cursor.execute('''
                UPDATE players 
                SET total_pugs = ?
                WHERE discord_id = ? AND server_id = ?
            ''', (total_pugs, str(discord_id), str(server_id)))
            
            # Check if any row was actually updated
            if cursor.rowcount == 0:
                conn.close()
                return False
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error updating player total_pugs: {e}")
            return False
    
    def get_all_players(self, server_id: str = None) -> List[Dict]:
        """Get all players, optionally filtered by server"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if server_id:
            cursor.execute('''
                SELECT discord_id, server_id, discord_name, display_name,
                       wins, losses, total_pugs, elo, peak_elo,
                       ut2k4_player_name, ut2k4_last_scraped, current_streak, registered,
                       best_win_streak, best_loss_streak
                FROM players 
                WHERE server_id = ?
            ''', (str(server_id),))
        else:
            cursor.execute('''
                SELECT discord_id, server_id, discord_name, display_name,
                       wins, losses, total_pugs, elo, peak_elo,
                       ut2k4_player_name, ut2k4_last_scraped, current_streak, registered,
                       best_win_streak, best_loss_streak
                FROM players
            ''')
        
        rows = cursor.fetchall()
        
        players = []
        for row in rows:
            players.append({
                'discord_id': row[0],
                'server_id': row[1],
                'discord_name': row[2],
                'display_name': row[3],
                'wins': row[4],
                'losses': row[5],
                'total_pugs': row[6],
                'elo': row[7],
                'peak_elo': row[8] if len(row) > 8 else row[7],  # Default to current elo
                'ut2k4_player_name': row[9] if len(row) > 9 else None,
                'ut2k4_last_scraped': row[10] if len(row) > 10 else None,
                'current_streak': row[11] if len(row) > 11 else 0,
                'registered': row[12] if len(row) > 12 else 0,
                'best_win_streak': row[13] if len(row) > 13 else 0,
                'best_loss_streak': row[14] if len(row) > 14 else 0
            })
        
        conn.close()
        return players
    
    def bulk_update_elos(self, server_id: str, elo_updates: List[tuple]) -> tuple:
        """
        Bulk update ELOs for a server
        elo_updates: List of (discord_id, new_elo) tuples
        Returns: (success_count, error_count, errors_list)
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        success_count = 0
        error_count = 0
        errors = []
        
        for discord_id, new_elo in elo_updates:
            try:
                # Validate that discord_id is numeric
                if not str(discord_id).isdigit():
                    error_count += 1
                    errors.append(f"Invalid Discord ID '{discord_id}': must be numeric")
                    continue
                
                # Check if player exists for this server
                cursor.execute('SELECT discord_id FROM players WHERE discord_id = ? AND server_id = ?',
                              (str(discord_id), str(server_id)))
                if cursor.fetchone():
                    # Update existing player
                    cursor.execute('UPDATE players SET elo = ? WHERE discord_id = ? AND server_id = ?',
                                  (float(new_elo), str(discord_id), str(server_id)))
                    success_count += 1
                else:
                    # Create new player with this ELO
                    cursor.execute('''
                        INSERT INTO players (discord_id, server_id, wins, losses, total_pugs, elo)
                        VALUES (?, ?, 0, 0, 0, ?)
                    ''', (str(discord_id), str(server_id), float(new_elo)))
                    success_count += 1
            except Exception as e:
                error_count += 1
                errors.append(f"Discord ID {discord_id}: {str(e)}")
        
        conn.commit()
        conn.close()
        
        return (success_count, error_count, errors)
    
    # PUG operations
    def add_pug(self, red_team: List[str], blue_team: List[str], game_mode: str, 
                avg_red_elo: float, avg_blue_elo: float, tiebreaker_map: str = None) -> int:
        """Add a new PUG and return the pug_id"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Insert PUG
        cursor.execute('''
            INSERT INTO pugs (game_mode, avg_red_elo, avg_blue_elo, tiebreaker_map)
            VALUES (?, ?, ?, ?)
        ''', (game_mode, avg_red_elo, avg_blue_elo, tiebreaker_map))
        
        pug_id = cursor.lastrowid
        
        # Insert red team members
        for discord_id in red_team:
            cursor.execute('''
                INSERT INTO pug_teams (pug_id, discord_id, team)
                VALUES (?, ?, 'red')
            ''', (pug_id, str(discord_id)))
        
        # Insert blue team members
        for discord_id in blue_team:
            cursor.execute('''
                INSERT INTO pug_teams (pug_id, discord_id, team)
                VALUES (?, ?, 'blue')
            ''', (pug_id, str(discord_id)))
        
        conn.commit()
        conn.close()
        
        # Return the pug_id which serves as the PUG number
        return pug_id
    
    def update_pug_winner(self, pug_id: int, winner: str):
        """Update PUG winner"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('UPDATE pugs SET winner = ? WHERE pug_id = ?', 
                      (winner, pug_id))
        
        conn.commit()
        conn.close()
    
    def delete_pug(self, pug_id: int):
        """Mark a PUG as killed (don't actually delete it)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Mark the PUG as killed instead of deleting
        cursor.execute("UPDATE pugs SET status = 'killed' WHERE pug_id = ?", (pug_id,))
        
        conn.commit()
        conn.close()
    
    def get_recent_pugs(self, limit: int = 3) -> List[Dict]:
        """Get recent PUGs"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT pug_id, game_mode, winner, avg_red_elo, avg_blue_elo, timestamp, status, tiebreaker_map
            FROM pugs
            ORDER BY pug_id DESC
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        pugs = []
        
        for row in rows:
            pug_id = row[0]
            
            # Get team members
            cursor.execute('''
                SELECT discord_id, team 
                FROM pug_teams 
                WHERE pug_id = ?
            ''', (pug_id,))
            
            team_rows = cursor.fetchall()
            red_team = [r[0] for r in team_rows if r[1] == 'red']
            blue_team = [r[0] for r in team_rows if r[1] == 'blue']
            
            pugs.append({
                'pug_id': pug_id,
                'number': pug_id,
                'game_mode': row[1],
                'winner': row[2],
                'avg_red_elo': row[3],
                'avg_blue_elo': row[4],
                'timestamp': row[5],
                'status': row[6] if len(row) > 6 else 'active',
                'tiebreaker_map': row[7] if len(row) > 7 else None,
                'red_team': red_team,
                'blue_team': blue_team
            })
        
        conn.close()
        return pugs
    
    def get_last_pug_id(self) -> Optional[int]:
        """Get the last PUG ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT MAX(pug_id) FROM pugs')
        result = cursor.fetchone()[0]
        
        conn.close()
        return result
    
    # Timeout operations
    def add_timeout(self, discord_id: str, timeout_end: datetime):
        """Add a timeout for a player"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO timeouts (discord_id, timeout_end)
            VALUES (?, ?)
        ''', (str(discord_id), timeout_end.isoformat()))
        
        conn.commit()
        conn.close()
    
    def is_timed_out(self, discord_id: str) -> Tuple[bool, Optional[datetime]]:
        """Check if player is timed out"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT timeout_end FROM timeouts WHERE discord_id = ?', 
                      (str(discord_id),))
        row = cursor.fetchone()
        
        if row:
            timeout_end = datetime.fromisoformat(row[0])
            if datetime.now() < timeout_end:
                conn.close()
                return True, timeout_end
            else:
                # Timeout expired, remove it
                cursor.execute('DELETE FROM timeouts WHERE discord_id = ?', 
                             (str(discord_id),))
                conn.commit()
        
        conn.close()
        return False, None
    
    # PUG Admin operations
    def add_pug_admin(self, discord_id: str, server_id: str):
        """Add a PUG admin for a specific server"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('INSERT OR IGNORE INTO pug_admins (discord_id, server_id) VALUES (?, ?)', 
                      (str(discord_id), str(server_id)))
        
        conn.commit()
        conn.close()
    
    def remove_pug_admin(self, discord_id: str, server_id: str):
        """Remove a PUG admin from a specific server"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM pug_admins WHERE discord_id = ? AND server_id = ?', 
                      (str(discord_id), str(server_id)))
        
        conn.commit()
        conn.close()
    
    def is_pug_admin(self, discord_id: str, server_id: str) -> bool:
        """Check if user is a PUG admin on a specific server"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT discord_id FROM pug_admins WHERE discord_id = ? AND server_id = ?', 
                      (str(discord_id), str(server_id)))
        result = cursor.fetchone()
        
        conn.close()
        return result is not None
    
    def get_pug_admins(self, server_id: str = None) -> List[str]:
        """Get all PUG admins for a specific server"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if server_id:
            cursor.execute('SELECT discord_id FROM pug_admins WHERE server_id = ?', (str(server_id),))
        else:
            cursor.execute('SELECT discord_id FROM pug_admins')
        
        rows = cursor.fetchall()
        
        conn.close()
        return [row[0] for row in rows]
    
    # Game Mode operations
    def add_game_mode(self, mode_name: str, display_name: str, team_size: int, 
                     description: str = "") -> Tuple[bool, Optional[str]]:
        """Add a game mode"""
        if team_size < 2 or team_size % 2 != 0:
            return False, "Team size must be an even number of at least 2!"
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO game_modes (mode_name, display_name, team_size, description)
                VALUES (?, ?, ?, ?)
            ''', (mode_name.lower(), display_name, team_size, description))
            conn.commit()
            conn.close()
            return True, None
        except sqlite3.IntegrityError:
            conn.close()
            return False, "Game mode already exists!"
    
    def remove_game_mode(self, mode_name: str) -> Tuple[bool, Optional[str]]:
        """Remove a game mode"""
        if mode_name.lower() == 'default':
            return False, "Cannot remove the default game mode!"
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM game_modes WHERE mode_name = ?', 
                      (mode_name.lower(),))
        
        if cursor.rowcount == 0:
            conn.close()
            return False, "Game mode does not exist!"
        
        conn.commit()
        conn.close()
        return True, None
    
    def get_game_mode(self, mode_name: str) -> Optional[Dict]:
        """Get a game mode"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT mode_name, display_name, team_size, description 
            FROM game_modes 
            WHERE mode_name = ?
        ''', (mode_name.lower(),))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'name': row[1],  # display_name
                'team_size': row[2],
                'description': row[3]
            }
        return None
    
    def get_all_game_modes(self) -> Dict:
        """Get all game modes sorted by player count (descending)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT mode_name, display_name, team_size, description FROM game_modes ORDER BY team_size DESC')
        rows = cursor.fetchall()
        
        modes = {}
        for row in rows:
            modes[row[0]] = {
                'name': row[1],
                'team_size': row[2],
                'description': row[3]
            }
        
        conn.close()
        return modes
    
    def add_mode_alias(self, alias: str, mode_name: str) -> tuple[bool, str]:
        """Add an alias for a game mode"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Check if mode exists
        cursor.execute('SELECT mode_name FROM game_modes WHERE mode_name = ?', (mode_name,))
        if not cursor.fetchone():
            conn.close()
            return False, f"Mode '{mode_name}' does not exist!"
        
        # Check if alias already exists
        cursor.execute('SELECT mode_name FROM mode_aliases WHERE alias = ?', (alias,))
        if cursor.fetchone():
            conn.close()
            return False, f"Alias '{alias}' already exists!"
        
        # Check if alias conflicts with existing mode name
        cursor.execute('SELECT mode_name FROM game_modes WHERE mode_name = ?', (alias,))
        if cursor.fetchone():
            conn.close()
            return False, f"'{alias}' is already a mode name!"
        
        # Add alias
        try:
            cursor.execute('INSERT INTO mode_aliases (alias, mode_name) VALUES (?, ?)', (alias, mode_name))
            conn.commit()
            conn.close()
            return True, None
        except Exception as e:
            conn.close()
            return False, str(e)
    
    def remove_mode_alias(self, alias: str) -> tuple[bool, str]:
        """Remove a mode alias"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT mode_name FROM mode_aliases WHERE alias = ?', (alias,))
        if not cursor.fetchone():
            conn.close()
            return False, f"Alias '{alias}' does not exist!"
        
        cursor.execute('DELETE FROM mode_aliases WHERE alias = ?', (alias,))
        conn.commit()
        conn.close()
        return True, None
    
    def get_mode_aliases(self, mode_name: str) -> list:
        """Get all aliases for a mode"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT alias FROM mode_aliases WHERE mode_name = ?', (mode_name,))
        rows = cursor.fetchall()
        
        conn.close()
        return [row[0] for row in rows]
    
    def resolve_mode_alias(self, name: str) -> str:
        """Resolve an alias to its actual mode name, or return the name if it's not an alias"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Check if it's an alias
        cursor.execute('SELECT mode_name FROM mode_aliases WHERE alias = ?', (name,))
        row = cursor.fetchone()
        
        conn.close()
        return row[0] if row else name
    
    # Bot Settings operations
    def get_setting(self, key: str) -> Optional[str]:
        """Get a bot setting"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT value FROM bot_settings WHERE key = ?', (key,))
        row = cursor.fetchone()
        
        conn.close()
        return row[0] if row else None
    
    def set_setting(self, key: str, value: str):
        """Set a bot setting"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO bot_settings (key, value)
            VALUES (?, ?)
        ''', (key, value))
        
        conn.commit()
        conn.close()
    
    def is_scraping_enabled(self) -> bool:
        """Check if scraping is enabled"""
        value = self.get_setting('scraping_enabled')
        return value == 'true' if value else False
    
    def set_scraping_enabled(self, enabled: bool):
        """Enable or disable scraping"""
        self.set_setting('scraping_enabled', 'true' if enabled else 'false')
