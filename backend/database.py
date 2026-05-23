import os
import sqlite3
import json
from datetime import datetime

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DB_DIR, "scraped_data.db")

def get_db_connection():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tower TEXT NOT NULL,
            floor INTEGER,
            business_name TEXT NOT NULL,
            category TEXT,
            keywords TEXT,
            phone TEXT,
            whatsapp TEXT,
            representative TEXT,
            entrance TEXT,
            site_url TEXT,
            careers_url TEXT,
            search_status TEXT DEFAULT 'PENDING',
            open_positions TEXT DEFAULT '[]',
            raw_positions_text TEXT,
            llm_filtered_positions TEXT DEFAULT '[]',
            last_scraped_at TEXT,
            UNIQUE(tower, business_name)
        )
    """)
    conn.commit()
    
    # Safe migration: Add careers_url column to existing database if it doesn't exist
    try:
        cursor.execute("ALTER TABLE companies ADD COLUMN careers_url TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        # Column already exists, safe to ignore
        pass
        
    conn.close()

def upsert_company(tower, floor, name, category, keywords, phone, whatsapp, representative, entrance):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check if company exists to preserve state
        cursor.execute(
            "SELECT id, site_url, search_status FROM companies WHERE tower = ? AND business_name = ?",
            (tower, name)
        )
        row = cursor.fetchone()
        
        if row:
            # Company exists, update basic details but preserve scraped state
            cursor.execute("""
                UPDATE companies 
                SET floor = ?, category = ?, keywords = ?, phone = ?, whatsapp = ?, representative = ?, entrance = ?
                WHERE id = ?
            """, (floor, category, keywords, phone, whatsapp, representative, entrance, row['id']))
            company_id = row['id']
        else:
            # New company, insert fresh
            cursor.execute("""
                INSERT INTO companies 
                (tower, floor, business_name, category, keywords, phone, whatsapp, representative, entrance, search_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
            """, (tower, floor, name, category, keywords, phone, whatsapp, representative, entrance))
            company_id = cursor.lastrowid
            
        conn.commit()
        return company_id
    except Exception as e:
        conn.rollback()
        print(f"Error upserting company {name}: {e}")
        return None
    finally:
        conn.close()

def get_all_companies():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM companies ORDER BY tower ASC, floor ASC, business_name ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_pending_companies():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM companies WHERE search_status IN ('PENDING', 'FAILED', 'RESOLVING_SITE', 'SEARCHING_JOBS') ORDER BY id ASC"
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_company_url(company_id, site_url):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Clean URL a bit (ensure https/http or leave as is)
        if site_url and not site_url.startswith(("http://", "https://")):
            site_url = "https://" + site_url
            
        cursor.execute("""
            UPDATE companies 
            SET site_url = ?, search_status = 'PENDING'
            WHERE id = ?
        """, (site_url, company_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error updating URL for company {company_id}: {e}")
    finally:
        conn.close()

def update_company_status(company_id, status):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE companies SET search_status = ? WHERE id = ?", (status, company_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error updating status for company {company_id}: {e}")
    finally:
        conn.close()

def save_scraped_data(company_id, site_url, careers_url, raw_text, open_positions, llm_filtered, status='COMPLETED'):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Ensure json string formatting
        open_positions_str = json.dumps(open_positions) if isinstance(open_positions, list) else open_positions
        llm_filtered_str = json.dumps(llm_filtered) if isinstance(llm_filtered, list) else llm_filtered
        timestamp = datetime.now().isoformat()
        
        cursor.execute("""
            UPDATE companies 
            SET site_url = ?, 
                careers_url = ?,
                raw_positions_text = ?, 
                open_positions = ?, 
                llm_filtered_positions = ?, 
                search_status = ?,
                last_scraped_at = ?
            WHERE id = ?
        """, (site_url, careers_url, raw_text, open_positions_str, llm_filtered_str, status, timestamp, company_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error saving scraped data for company {company_id}: {e}")
    finally:
        conn.close()

def reset_in_progress_statuses():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE companies SET search_status = 'PENDING' WHERE search_status IN ('RESOLVING_SITE', 'SEARCHING_JOBS')"
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error resetting statuses: {e}")
    finally:
        conn.close()

def clear_all_data():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM companies")
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error clearing data: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
