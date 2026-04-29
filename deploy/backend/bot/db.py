import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    db_url = os.getenv("NEON")
    if not db_url:
        raise ValueError("NEON database URL not found in environment variables.")
    return psycopg2.connect(db_url)

def init_db():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trust_ledger (
                    id SERIAL PRIMARY KEY,
                    game_id VARCHAR(255) NOT NULL,
                    bot_country VARCHAR(50) NOT NULL,
                    agreed_with VARCHAR(50) NOT NULL,
                    agreement TEXT NOT NULL,
                    phase_made VARCHAR(50) NOT NULL,
                    followed BOOLEAN
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS game_messages (
                    id SERIAL PRIMARY KEY,
                    game_id VARCHAR(255) NOT NULL,
                    sender VARCHAR(50) NOT NULL,
                    recipient VARCHAR(50) NOT NULL,
                    message TEXT NOT NULL,
                    phase VARCHAR(50) NOT NULL,
                    time_sent TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        conn.commit()
    finally:
        conn.close()

def save_message(game_id: str, sender: str, recipient: str, message: str, phase: str):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO game_messages (game_id, sender, recipient, message, phase)
                VALUES (%s, %s, %s, %s, %s)
            """, (game_id, sender, recipient, message, phase))
        conn.commit()
    finally:
        conn.close()

def get_game_messages(game_id: str):
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT sender, recipient, message, phase, time_sent
                FROM game_messages
                WHERE game_id = %s
                ORDER BY time_sent ASC, id ASC
            """, (game_id,))
            return cur.fetchall()
    finally:
        conn.close()

def add_agreement(game_id: str, bot_country: str, agreed_with: str, agreement: str, phase_made: str):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO trust_ledger (game_id, bot_country, agreed_with, agreement, phase_made, followed)
                VALUES (%s, %s, %s, %s, %s, NULL)
            """, (game_id, bot_country, agreed_with, agreement, phase_made))
        conn.commit()
    finally:
        conn.close()

def get_pending_agreements(game_id: str):
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, bot_country, agreed_with, agreement, phase_made
                FROM trust_ledger
                WHERE game_id = %s AND followed IS NULL
            """, (game_id,))
            return cur.fetchall()
    finally:
        conn.close()

def update_agreement_status(agreement_id: int, followed: bool):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE trust_ledger
                SET followed = %s
                WHERE id = %s
            """, (followed, agreement_id))
        conn.commit()
    finally:
        conn.close()

def get_trust_history(bot_country: str, agreed_with: str):
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT agreement, followed, phase_made
                FROM trust_ledger
                WHERE bot_country = %s AND agreed_with = %s AND followed IS NOT NULL
                ORDER BY id DESC
                LIMIT 5
            """, (bot_country, agreed_with))
            return cur.fetchall()
    finally:
        conn.close()
