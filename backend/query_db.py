import sqlite3
import json
import os

def query():
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "scraped_data.db")
    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        return
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, business_name, site_url, careers_url, open_positions, llm_filtered_positions, search_status FROM companies")
    rows = cursor.fetchall()
    
    print(f"--- BSR Towers Scraper Database Dump (Total records: {len(rows)}) ---\n")
    
    completed = [r for r in rows if r['search_status'] == 'COMPLETED']
    print(f"Successfully processed companies: {len(completed)}\n")
    
    for r in completed:
        try:
            jobs = json.loads(r['llm_filtered_positions'])
        except:
            jobs = []
            
        print(f"ID: #{r['id']} | Business: {r['business_name']}")
        print(f"  Domain resolved: {r['site_url']}")
        print(f"  Careers page URL: {r['careers_url']}")
        print(f"  Jobs found ({len(jobs)}):")
        for j in jobs:
            print(f"    - {j.get('title')} ({j.get('department')})")
        print("-" * 60)
        
    conn.close()

if __name__ == "__main__":
    query()
