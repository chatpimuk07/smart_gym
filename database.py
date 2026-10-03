import sqlite3
from datetime import date
from typing import Optional, List, Dict, Any


class GymDatabase:

    def __init__(self, db_name="gym.db"):
        self.db_name = db_name
        # check_same_thread=False is required for FastAPI / multi-threaded environments
        self.conn = sqlite3.connect(self.db_name, check_same_thread=False)
        # Enables accessing columns by name like dictionary keys
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        # Enable foreign key constraint enforcement
        self.cursor.execute("PRAGMA foreign_keys = ON;")
        self.create_tables()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def create_tables(self):
        """Create all four core tables if they do not already exist."""
        # 1. Users table: Stores demographic data, goals, and physical limitations
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                nfc_uid TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                fitness_level TEXT NOT NULL,
                target_goal TEXT NOT NULL,
                injury_note TEXT,
                gender TEXT
            );
        """)

        # 2. Stations table: Tracks machine configurations and live usage states
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS stations (
                station_id TEXT PRIMARY KEY,
                station_name TEXT NOT NULL,
                target_muscles TEXT NOT NULL,
                status TEXT DEFAULT 'idle',
                current_user_id INTEGER,
                last_active DATETIME,
                FOREIGN KEY (current_user_id) REFERENCES users(user_id)
            );
        """)

        # 3. Workout history table: Logs completed sessions for progressive overload calculation
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS workout_history (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                station_id TEXT NOT NULL,
                exercise_name TEXT NOT NULL,
                weight_kg REAL NOT NULL,
                sets_completed INTEGER NOT NULL,
                reps_completed INTEGER NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (station_id) REFERENCES stations(station_id)
            );
        """)

        # 4. Daily routines cache table: Prevents redundant AI generation within the same day
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_routines_cache (
                cache_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                station_id TEXT NOT NULL,
                routine_date DATE NOT NULL,
                ai_response_json TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (station_id) REFERENCES stations(station_id),
                UNIQUE(user_id, station_id, routine_date)
            );
        """)
        self.conn.commit()

    # ==========================================
    # USER METHODS
    # ==========================================

    def add_user(
        self,
        nfc_uid: str,
        name: str,
        fitness_level: str,
        target_goal: str,
        injury_note: Optional[str] = None,
        gender: Optional[str] = None
    ) -> Optional[int]:
        """Register a new user. Returns user_id on success, or None on failure."""
        if not all([nfc_uid, name, fitness_level, target_goal]):
            return None
        try:
            self.cursor.execute("""
                INSERT INTO users (nfc_uid, name, fitness_level, target_goal, injury_note, gender)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (nfc_uid, name, fitness_level, target_goal, injury_note, gender))
            self.conn.commit()
            return self.cursor.lastrowid
        except sqlite3.Error as e:
            self.conn.rollback()
            print(f"Database Error (add_user): {e}")
            return None

    def get_user_by_nfc(self, nfc_uid: str) -> Optional[Dict[str, Any]]:
        """Fetch user profile using their physical NFC card UID."""
        self.cursor.execute("SELECT * FROM users WHERE nfc_uid = ?", (nfc_uid,))
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Fetch user profile by internal user_id."""
        self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = self.cursor.fetchone()
        return dict(row) if row else None

    # ==========================================
    # STATION METHODS
    # ==========================================

    def register_station(self, station_id: str, station_name: str, target_muscles: str):
        """Register a new workout station in the system."""
        try:
            self.cursor.execute("""
                INSERT OR IGNORE INTO stations (station_id, station_name, target_muscles)
                VALUES (?, ?, ?)
            """, (station_id, station_name, target_muscles))
            self.conn.commit()
        except sqlite3.Error as e:
            self.conn.rollback()
            print(f"Database Error (register_station): {e}")

    def get_station(self, station_id: str) -> Optional[Dict[str, Any]]:
        """Fetch station metadata by station_id."""
        self.cursor.execute("SELECT * FROM stations WHERE station_id = ?", (station_id,))
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def update_station_status(self, station_id: str, status: str, user_id: Optional[int] = None):
        """Update live station status (e.g., 'idle' or 'in_use') for desktop monitoring."""
        try:
            self.cursor.execute("""
                UPDATE stations 
                SET status = ?, current_user_id = ?, last_active = CURRENT_TIMESTAMP
                WHERE station_id = ?
            """, (status, user_id, station_id))
            self.conn.commit()
        except sqlite3.Error as e:
            self.conn.rollback()
            print(f"Database Error (update_station_status): {e}")

    def get_all_stations(self) -> List[Dict[str, Any]]:
        """Return all gym stations and their current active states."""
        self.cursor.execute("SELECT * FROM stations")
        return [dict(row) for row in self.cursor.fetchall()]

    # ==========================================
    # WORKOUT HISTORY & AI CONTEXT
    # ==========================================

    def get_last_workout(self, user_id: int, station_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve the most recent workout entry for progressive overload computation."""
        self.cursor.execute("""
            SELECT weight_kg, sets_completed, reps_completed, timestamp
            FROM workout_history
            WHERE user_id = ? AND station_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (user_id, station_id))
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def log_workout(
        self,
        user_id: int,
        station_id: str,
        exercise_name: str,
        weight_kg: float,
        sets: int,
        reps: int
    ) -> bool:
        """Log a completed exercise session to the database."""
        try:
            self.cursor.execute("""
                INSERT INTO workout_history (user_id, station_id, exercise_name, weight_kg, sets_completed, reps_completed)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, station_id, exercise_name, weight_kg, sets, reps))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            self.conn.rollback()
            print(f"Database Error (log_workout): {e}")
            return False

    def get_user_history_all(self, user_id: int) -> List[Dict[str, Any]]:
        """Fetch complete chronological workout history for dashboard charts."""
        self.cursor.execute("""
            SELECT h.*, s.station_name 
            FROM workout_history h
            JOIN stations s ON h.station_id = s.station_id
            WHERE h.user_id = ?
            ORDER BY h.timestamp ASC
        """, (user_id,))
        return [dict(row) for row in self.cursor.fetchall()]

    # ==========================================
    # CACHE METHODS
    # ==========================================

    def get_cached_routine(self, user_id: int, station_id: str) -> Optional[str]:
        """Check if an AI routine was already generated for this user and station today."""
        today = date.today().isoformat()
        self.cursor.execute("""
            SELECT ai_response_json FROM daily_routines_cache
            WHERE user_id = ? AND station_id = ? AND routine_date = ?
        """, (user_id, station_id, today))
        row = self.cursor.fetchone()
        return row["ai_response_json"] if row else None

    def save_cached_routine(self, user_id: int, station_id: str, ai_response_json: str):
        """Save generated AI routine into the daily cache table."""
        today = date.today().isoformat()
        try:
            self.cursor.execute("""
                INSERT OR REPLACE INTO daily_routines_cache (user_id, station_id, routine_date, ai_response_json)
                VALUES (?, ?, ?, ?)
            """, (user_id, station_id, today, ai_response_json))
            self.conn.commit()
        except sqlite3.Error as e:
            self.conn.rollback()
            print(f"Database Error (save_cached_routine): {e}")

    def close(self):
        """Safely terminate the database connection."""
        if self.conn:
            self.conn.close()