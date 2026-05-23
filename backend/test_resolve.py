import os
import sys

# Ensure backend folder is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

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
