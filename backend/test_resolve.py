import os
import sys

# Ensure backend folder is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Force UTF-8 console encoding on Windows to prevent UnicodeEncodeError crashes
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import scraper

def test_resolve():
    print("=========================================")
    print("TESTING RESOLVER ON DELIMITED HEBREW NAME")
    target_name = "וויקאר שרותי רפואה/לפידות פיננסים"
    print(f"Target Name: '{target_name}'")
    print("=========================================\n")
    
    # We will test both search and normalization
    print("Running scraper search resolver...")
    resolved_url = scraper.search_website_for_business(target_name)
    
    print("\n=========================================")
    if resolved_url:
        print(f"SUCCESS! Resolved Website URL: {resolved_url}")
    else:
        print("Failed to resolve website URL.")
    print("=========================================")

if __name__ == "__main__":
    test_resolve()
