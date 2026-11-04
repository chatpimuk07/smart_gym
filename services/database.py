import os
import sqlite3
from datetime import date
from typing import Optional, List, Dict, Any, Tuple

# Root directory of the smart_gym project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "gym.db")


class GymDatabase:

    def __init__(self, db_name: Optional[str] = None):
        self.db_name = db_name if db_name is not None else DEFAULT_DB_PATH
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
                timestamp DATETIME DEFAULT (datetime('now', 'localtime')),
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

        # Migration: Ensure username and password columns exist in users table
        self.cursor.execute("PRAGMA table_info(users)")
        existing_cols = [col[1] for col in self.cursor.fetchall()]
        if "username" not in existing_cols:
            self.cursor.execute("ALTER TABLE users ADD COLUMN username TEXT")
        if "password" not in existing_cols:
            self.cursor.execute("ALTER TABLE users ADD COLUMN password TEXT DEFAULT '1234'")

        # Populate username and default password for existing users if empty
        self.cursor.execute("SELECT user_id, name, username, password FROM users")
        for u in self.cursor.fetchall():
            uid = u["user_id"]
            uname = u["username"]
            upass = u["password"]
            needs_update = False
            new_uname = uname
            new_upass = upass or "1234"
            if not uname:
                base_name = u["name"].strip().lower().replace(" ", "_")
                new_uname = base_name if base_name else f"user_{uid}"
                needs_update = True
            if not upass:
                needs_update = True
            if needs_update:
                self.cursor.execute(
                    "UPDATE users SET username = ?, password = ? WHERE user_id = ?",
                    (new_uname, new_upass, uid)
                )

        self.conn.commit()

    # ==========================================
    # USER METHODS & AUTH
    # ==========================================

    def add_user(
        self,
        nfc_uid: Optional[str],
        name: str,
        fitness_level: str,
        target_goal: str,
        injury_note: Optional[str] = None,
        gender: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = "1234"
    ) -> Optional[int]:
        """Register a new user. Returns user_id on success, or None on failure."""
        if not all([name, fitness_level, target_goal]):
            return None
        import secrets
        clean_nfc = nfc_uid.strip().upper() if (nfc_uid and nfc_uid.strip()) else f"PENDING_{secrets.token_hex(4).upper()}"
        clean_username = username.strip().lower() if username else name.strip().lower().replace(" ", "_")
        clean_password = password if password else "1234"
        try:
            # Check if username already exists
            self.cursor.execute("SELECT user_id FROM users WHERE lower(username) = ?", (clean_username,))
            if self.cursor.fetchone():
                return None

            self.cursor.execute("""
                INSERT INTO users (nfc_uid, name, fitness_level, target_goal, injury_note, gender, username, password)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (clean_nfc, name, fitness_level, target_goal, injury_note, gender, clean_username, clean_password))
            self.conn.commit()
            return self.cursor.lastrowid
        except sqlite3.Error as e:
            self.conn.rollback()
            print(f"Database Error (add_user): {e}")
            return None

    def authenticate_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Validate username/name and password. Returns user dict without password if valid, else None."""
        clean_user = username.strip().lower()
        self.cursor.execute("""
            SELECT user_id, nfc_uid, name, username, fitness_level, target_goal, injury_note, gender, password
            FROM users 
            WHERE lower(username) = ? OR lower(name) = ?
        """, (clean_user, clean_user))
        row = self.cursor.fetchone()
        if not row:
            return None
        
        user_dict = dict(row)
        stored_password = user_dict.get("password") or "1234"
        if stored_password == password:
            user_dict.pop("password", None)
            return user_dict
        return None

    def change_user_password(self, user_id: int, old_password: str, new_password: str) -> Tuple[bool, str]:
        """Change user password after verifying old password."""
        if not new_password or len(new_password) < 4:
            return False, "รหัสผ่านใหม่ต้องมีความยาวอย่างน้อย 4 ตัวอักษร"
            
        self.cursor.execute("SELECT password FROM users WHERE user_id = ?", (user_id,))
        row = self.cursor.fetchone()
        if not row:
            return False, "ไม่พบข้อมูลผู้ใช้งาน"
            
        stored_pass = row["password"] or "1234"
        if stored_pass != old_password:
            return False, "รหัสผ่านเดิมไม่ถูกต้อง"
            
        try:
            self.cursor.execute("UPDATE users SET password = ? WHERE user_id = ?", (new_password, user_id))
            self.conn.commit()
            return True, "เปลี่ยนรหัสผ่านสำเร็จ"
        except sqlite3.Error as e:
            self.conn.rollback()
            return False, f"Database Error: {e}"

    def get_user_summary(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve complete dashboard summary for user: profile, today's routines, and recent history."""
        user = self.get_user_by_id(user_id)
        if not user:
            return None
        user.pop("password", None)
        
        # 1. Today's AI routines
        self.cursor.execute("""
            SELECT c.*, s.station_name, s.target_muscles
            FROM daily_routines_cache c
            JOIN stations s ON c.station_id = s.station_id
            WHERE c.user_id = ?
            ORDER BY c.cache_id DESC
        """, (user_id,))
        routines = [dict(r) for r in self.cursor.fetchall()]
        
        # 2. Recent workout history (last 5)
        self.cursor.execute("""
            SELECT h.*, s.station_name, s.target_muscles
            FROM workout_history h
            LEFT JOIN stations s ON h.station_id = s.station_id
            WHERE h.user_id = ?
            ORDER BY h.log_id DESC
            LIMIT 5
        """, (user_id,))
        recent_history = [dict(h) for h in self.cursor.fetchall()]
        
        # 3. Total workout count
        self.cursor.execute("SELECT COUNT(*) as count FROM workout_history WHERE user_id = ?", (user_id,))
        total_count = self.cursor.fetchone()["count"]
        
        return {
            "user": user,
            "today_routines": routines,
            "recent_history": recent_history,
            "total_workouts": total_count
        }

    def get_user_workout_history(self, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Get full workout history for user."""
        self.cursor.execute("""
            SELECT h.*, s.station_name, s.target_muscles
            FROM workout_history h
            LEFT JOIN stations s ON h.station_id = s.station_id
            WHERE h.user_id = ?
            ORDER BY h.timestamp DESC, h.log_id DESC
            LIMIT ?
        """, (user_id, limit))
        return [dict(r) for r in self.cursor.fetchall()]

    def get_user_by_nfc(self, nfc_uid: str) -> Optional[Dict[str, Any]]:
        """Fetch user profile using their physical NFC card UID."""
        self.cursor.execute("SELECT * FROM users WHERE nfc_uid = ?", (nfc_uid,))
        row = self.cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d.pop("password", None)
        return d

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Fetch user profile by internal user_id."""
        self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = self.cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d.pop("password", None)
        return d

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
                SET status = ?, current_user_id = ?, last_active = datetime('now', 'localtime')
                WHERE station_id = ?
            """, (status, user_id, station_id))
            self.conn.commit()
        except sqlite3.Error as e:
            self.conn.rollback()
            print(f"Database Error (update_station_status): {e}")

    def get_all_stations(self) -> List[Dict[str, Any]]:
        """Return all gym stations and their current active states, including current user details."""
        self.cursor.execute("""
            SELECT 
                s.station_id,
                s.station_name,
                s.target_muscles,
                s.status,
                s.current_user_id,
                s.last_active,
                u.name AS current_user_name,
                u.fitness_level AS current_user_level,
                u.target_goal AS current_user_goal
            FROM stations s
            LEFT JOIN users u ON s.current_user_id = u.user_id
            ORDER BY s.station_id ASC
        """)
        return [dict(row) for row in self.cursor.fetchall()]

    def reset_station_status(self, station_id: str) -> bool:
        """Reset station status back to 'idle' and clear current user."""
        try:
            self.cursor.execute("""
                UPDATE stations 
                SET status = 'idle', current_user_id = NULL
                WHERE station_id = ?
            """, (station_id,))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            self.conn.rollback()
            print(f"Database Error (reset_station_status): {e}")
            return False

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
    
    def get_all_users(self) -> List[Dict[str, Any]]:
        """Retrieve all users ordered by newest first."""
        self.cursor.execute("SELECT * FROM users ORDER BY user_id DESC")
        return [dict(row) for row in self.cursor.fetchall()]

    def update_user(
        self,
        user_id: int,
        nfc_uid: str,
        name: str,
        fitness_level: str,
        target_goal: str,
        injury_note: Optional[str] = None,
        gender: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None
    ) -> bool:
        """Update an existing user's information."""
        try:
            clean_username = username.strip().lower() if username else name.strip().lower().replace(" ", "_")
            if password and password.strip():
                self.cursor.execute("""
                    UPDATE users 
                    SET nfc_uid = ?, name = ?, fitness_level = ?, target_goal = ?, injury_note = ?, gender = ?, username = ?, password = ?
                    WHERE user_id = ?
                """, (nfc_uid, name, fitness_level, target_goal, injury_note, gender, clean_username, password, user_id))
            else:
                self.cursor.execute("""
                    UPDATE users 
                    SET nfc_uid = ?, name = ?, fitness_level = ?, target_goal = ?, injury_note = ?, gender = ?, username = ?
                    WHERE user_id = ?
                """, (nfc_uid, name, fitness_level, target_goal, injury_note, gender, clean_username, user_id))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            self.conn.rollback()
            print(f"Database Error (update_user): {e}")
            return False

    def delete_user(self, user_id: int) -> bool:
        """Delete a user and associated cache/history records."""
        try:
            self.cursor.execute("DELETE FROM daily_routines_cache WHERE user_id = ?", (user_id,))
            self.cursor.execute("DELETE FROM workout_history WHERE user_id = ?", (user_id,))
            self.cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            self.conn.rollback()
            print(f"Database Error (delete_user): {e}")
            return False

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
                INSERT INTO workout_history (user_id, station_id, exercise_name, weight_kg, sets_completed, reps_completed, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
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