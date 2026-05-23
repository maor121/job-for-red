import os
import threading
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

import database
import scraper

# Initialize database
database.init_db()

app = FastAPI(
    title="BSR Towers Job Scraper Dashboard",
    description="A premium control panel for managing BSR Towers company job scraping.",
    version="1.0.0"
)

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request Models
class UrlUpdateRequest(BaseModel):
    url: str

# 1. API Endpoints for Company Data
@app.get("/api/companies")
def get_companies():
    try:
        return database.get_all_companies()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/companies/{company_id}/url")
def update_company_url(company_id: int, request: UrlUpdateRequest):
    try:
        database.update_company_url(company_id, request.url)
        return {"status": "success", "message": f"URL updated successfully for company {company_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2. Control Endpoints for Scraper
@app.get("/api/scraper/status")
def get_scraper_status():
    return {
        "is_running": scraper.ScrapingProgress.is_running,
        "total": scraper.ScrapingProgress.total,
        "current_index": scraper.ScrapingProgress.current_index,
        "current_company": scraper.ScrapingProgress.current_company,
        "logs": scraper.ScrapingProgress.logs,
        "progress_percent": (
            (scraper.ScrapingProgress.current_index / scraper.ScrapingProgress.total * 100)
            if scraper.ScrapingProgress.total > 0 else 0
        )
    }

def bg_scraper_task():
    scraper.run_scraper_process()

@app.post("/api/scraper/start")
def start_scraper(background_tasks: BackgroundTasks):
    if scraper.ScrapingProgress.is_running:
        return {"status": "already_running", "message": "Scraper is already active."}
        
    # Start the scraper loop in a background thread
    background_tasks.add_task(bg_scraper_task)
    return {"status": "started", "message": "Scraper engine initialized in background."}

@app.post("/api/scraper/stop")
def stop_scraper():
    if not scraper.ScrapingProgress.is_running:
        return {"status": "idle", "message": "Scraper is already idle."}
        
    scraper.stop_scraper_process()
    return {"status": "stopping", "message": "Stop signal sent to scraper loop."}

@app.post("/api/companies/{company_id}/re-scrape")
def re_scrape_company(company_id: int):
    """
    Triggers an immediate, synchronous scrape of a single company.
    """
    # Fetch company from DB
    companies = database.get_all_companies()
    company = next((c for c in companies if c['id'] == company_id), None)
    
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
        
    name = company['business_name']
    
    # Run scraping process for just this company
    try:
        # 1. Resolve URL if empty
        site_url = company['site_url']
        if not site_url:
            database.update_company_status(company_id, 'RESOLVING_SITE')
            site_url = scraper.search_website_for_business(name)
            if not site_url:
                database.save_scraped_data(company_id, None, None, "", [], [], 'FAILED')
                return {"status": "failed", "message": "Could not resolve company website url"}
            else:
                database.update_company_url(company_id, site_url)
                
        # 2. Crawl Careers Page
        database.update_company_status(company_id, 'SEARCHING_JOBS')
        links, homepage_raw = scraper.find_menu_and_career_links(site_url)
        
        careers_url = None
        raw_jobs_text = ""
        positions_list = []
        filtered_jobs = []
        
        if links:
            careers_url = scraper.resolve_careers_link_via_llm(site_url, links)
            
        if careers_url:
            raw_jobs_text, positions_list = scraper.extract_jobs_from_page(careers_url)
        else:
            raw_jobs_text, positions_list = scraper.extract_jobs_from_page(site_url)
            careers_url = site_url
            
        if positions_list:
            filtered_jobs = scraper.llm_filter_positions(raw_jobs_text, positions_list)
            
        database.save_scraped_data(
            company_id=company_id,
            site_url=site_url,
            careers_url=careers_url,
            raw_text=raw_jobs_text,
            open_positions=positions_list,
            llm_filtered=filtered_jobs,
            status='COMPLETED'
        )
        
        # Reload and return updated company
        updated_companies = database.get_all_companies()
        updated_company = next((c for c in updated_companies if c['id'] == company_id), None)
        
        return {
            "status": "completed",
            "message": f"Successfully scraped {name}",
            "company": updated_company
        }
    except Exception as e:
        database.update_company_status(company_id, 'FAILED')
        raise HTTPException(status_code=500, detail=f"Failed to scrape company: {e}")

# 3. Serve Frontend Web Application
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

# Serve static folders
if os.path.exists(FRONTEND_DIR):
    app.mount("/css", StaticFiles(directory=os.path.join(FRONTEND_DIR, "css")), name="css")
    app.mount("/js", StaticFiles(directory=os.path.join(FRONTEND_DIR, "js")), name="js")

    @app.get("/")
    def read_root():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
else:
    @app.get("/")
    def read_root():
        return {
            "message": "Welcome to BSR Towers Scraper API. Frontend directory is missing. Please create the 'frontend' folder."
        }

if __name__ == "__main__":
    import uvicorn
    # Reset in-progress statuses on boot to prevent locked states
    database.reset_in_progress_statuses()
    uvicorn.run(app, host="127.0.0.1", port=8000)
