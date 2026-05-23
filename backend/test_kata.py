import os
import sys

# Ensure backend folder is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import scraper

def test_kata_crawl():
    print("=========================================")
    print("TESTING SCRAPER ENGINE ON KATA GROUP")
    print("Target Site: https://katagroup.co.il/")
    print("=========================================\n")

    # 1. Inspect navigation links
    print("[STEP 1] Crawling homepage to find navigation links...")
    homepage_url = "https://katagroup.co.il/"
    links, raw_html = scraper.find_menu_and_career_links(homepage_url)
    
    print(f"Total unique local links found: {len(links)}")
    print("\nSample links extracted (top 15):")
    for idx, l in enumerate(links[:15]):
        print(f"  [{idx+1}] Text: '{l['text']}', URL: '{l['url']}', InMenu: {l['in_menu']}")
        
    print("\n[STEP 2] Resolving Careers/Jobs page URL using link solver...")
    careers_url = scraper.resolve_careers_link_via_llm(homepage_url, links)
    
    if careers_url:
        print(f"\nSUCCESS! Careers URL resolved: {careers_url}")
    else:
        print("\nFailed to resolve careers page. (Check heuristics)")
        careers_url = homepage_url
        
    print("\n[STEP 3] Fetching and extracting raw positions from resolved Careers URL...")
    raw_text, raw_positions = scraper.extract_jobs_from_page(careers_url)
    
    print(f"Total raw position candidates found: {len(raw_positions)}")
    print("Raw candidates extracted:")
    for idx, p in enumerate(raw_positions):
        print(f"  - {p}")
        
    print("\n[STEP 4] Filtering raw positions using Local Heuristic / Gemini filter...")
    filtered_jobs = scraper.llm_filter_positions(raw_text, raw_positions)
    
    print(f"Total structured jobs verified: {len(filtered_jobs)}")
    print("Structured verified jobs:")
    for idx, f in enumerate(filtered_jobs):
        print(f"  [{idx+1}] Title: '{f['title']}' | Dept: '{f['department']}' | Status: '{f['status']}'")
        
    print("\n=========================================")
    print("KATA GROUP TEST COMPLETED SUCCESSFULLY!")
    print("=========================================")

if __name__ == "__main__":
    test_kata_crawl()
