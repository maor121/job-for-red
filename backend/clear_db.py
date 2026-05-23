import os
import sys

# Ensure backend folder is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import database

def clear():
    print("Clearing SQLite database at data/scraped_data.db...")
    database.clear_all_data()
    print("Database cleared successfully! You can now start completely fresh.")

if __name__ == "__main__":
    clear()
