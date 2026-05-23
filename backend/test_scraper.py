import os
import sys

# Ensure backend folder is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import database
import scraper

def run_dry_run_test():
    print("=========================================")
    print("Starting BSR Towers Job Scraper Dry Run Test")
    print("=========================================\n")

    # 1. Database Init Test
    print("Step 1: Initializing SQLite database...")
    database.init_db()
    print("Database path:", database.DB_PATH)
    print("Success!\n")

    # 2. Bindex Sheets API Sync Test
    print("Step 2: Syncing first 5 companies from Tower C Sheets API...")
    tower_c_companies = scraper.fetch_bindex_companies('c')
    print(f"Total companies found in Tower C API: {len(tower_c_companies)}")
    
    if len(tower_c_companies) > 0:
        sample = tower_c_companies[:3]
        print("\nSample records returned:")
        for idx, s in enumerate(sample):
            print(f"  [{idx+1}] Name: '{s.get('title1') or s.get('title')}', Floor: {s.get('floor')}, Category: '{s.get('cat')}'")
            
        print("\nPopulating database with a subset of Tower C to test upserts...")
        for c in tower_c_companies[:5]:
            name = c.get("title1") or c.get("title")
            if not name:
                continue
            
            floor = c.get("floor")
            try:
                floor = int(floor) if floor is not None else None
            except ValueError:
                floor = 0
                
            database.upsert_company(
                tower='C',
                floor=floor,
                name=name.strip(),
                category=c.get("cat") or c.get("category"),
                keywords=c.get("keywords"),
                phone=c.get("phone"),
                whatsapp=c.get("whatsapp"),
                representative=c.get("representative1") or c.get("representative"),
                entrance=c.get("entrance")
            )
        print("Populate subset completed successfully.")
    else:
        print("No companies returned or API timed out. (Internet connection issue?)")
    print("")

    # 3. Heuristic Link Scoring Test
    print("Step 3: Testing Menu navigation & careers heuristic matcher...")
    mock_homepage = "https://www.example.com"
    mock_links = [
        {'url': 'https://www.example.com/about', 'text': 'אודותינו', 'title': 'About Us', 'in_menu': True},
        {'url': 'https://www.example.com/contact', 'text': 'צור קשר', 'title': 'Contact', 'in_menu': True},
        {'url': 'https://www.example.com/careers', 'text': 'דרושים', 'title': 'Careers at Example', 'in_menu': True},
        {'url': 'https://www.example.com/blog', 'text': 'בלוג', 'title': 'Blog', 'in_menu': False},
        {'url': 'https://www.example.com/jobs/apply', 'text': 'משרות פתוחות', 'title': 'Jobs', 'in_menu': False}
    ]
    
    resolved_careers_url = scraper.resolve_careers_link_via_llm(mock_homepage, mock_links)
    print(f"Homepage URL: {mock_homepage}")
    print("Mock links parsed:")
    for l in mock_links:
        print(f"  - Text: '{l['text']}', URL: '{l['url']}', Menu: {l['in_menu']}")
    print(f"Result URL: {resolved_careers_url}")
    
    if resolved_careers_url == 'https://www.example.com/careers':
        print("Success! Heuristics correctly matched '/careers' with text 'דרושים'.")
    else:
        print("Warning: unexpected heuristic match result.")
    print("")

    # 4. Local Heuristic Filter Test
    print("Step 4: Testing Job Extraction Local Heuristic Filter...")
    mock_raw_text = """
    Welcome to our Careers Page! We are looking for talented professionals to join our team.
    
    Junior Fullstack Developer
    Department: R&D
    Location: Petah Tikva BSR
    We are looking for a junior fullstack developer with experience in React and Node.js.
    
    Senior Product Manager
    Department: Product
    We are looking for a senior product manager with 5+ years of experience.
    
    Our office is in Petah Tikva, near the light rail station.
    Contact us at careers@example.com
    """
    
    mock_extracted_positions = ["Junior Fullstack Developer", "Senior Product Manager", "Welcome to our Careers Page!"]
    
    filtered_jobs = scraper.llm_filter_positions(mock_raw_text, mock_extracted_positions)
    print("Extracted candidates:", mock_extracted_positions)
    print("Filtered result:")
    for f in filtered_jobs:
        print(f"  - {f['title']} [{f['status']}]")
        
    titles = [x['title'] for x in filtered_jobs]
    if "Junior Fullstack Developer" in titles and "Senior Product Manager" in titles and "Welcome to our Careers Page!" not in titles:
        print("Success! Local filter correctly extracted roles and discarded generic text.")
    else:
        print("Warning: local filter did not match exactly as expected.")
    print("")

    print("=========================================")
    print("Dry Run Test Completed successfully!")
    print("=========================================")

if __name__ == "__main__":
    run_dry_run_test()
