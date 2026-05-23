import os
import re
import json
import time
import urllib.parse
import requests
from bs4 import BeautifulSoup
import database

# Try to load environment variables from a local .env file
try:
    from dotenv import load_dotenv
    # Seek .env in root directory (parent of backend/)
    dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
    else:
        load_dotenv() # Fallback to default loading
except ImportError:
    pass

# Try to load Google Gemini Generative AI SDK
HAS_GEMINI = False
gemini_model = None

try:
    import google.generativeai as genai
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_model = genai.GenerativeModel('gemini-1.5-flash')
        HAS_GEMINI = True
        print("[LLM ENGINE] Google Gemini SDK successfully loaded and configured with API Key.")
    else:
        print("[LLM ENGINE] GEMINI_API_KEY variable is not set in environment or .env. Falling back to local heuristic engines.")
except ImportError:
    print("[LLM ENGINE] google-generativeai SDK is not installed. Falling back to local heuristic engines.")

# Constants
BINDEX_API_URL = "https://script.google.com/macros/s/AKfycbw6n-WunPuTDmYE2-JuYcDsEDNt7_rkOCKaQzNp7FGbw2YFKx4z0CzoT2WYxuxEH1N2/exec"
SHEET_ID = "1qV0t8i-D9uBzHIJ01pfsJH0SFN4wncig_454Zxel2tc"
TOWERS = ['c', 'i', 't', 'y']

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Accept-Language': 'he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8'
}

# -----------------
# 1. Fetching Bindex Data
# -----------------
def fetch_bindex_companies(tower):
    """
    Fetches the companies in a specific BSR tower from the Google Sheets API.
    """
    print(f"Fetching companies for Tower {tower.upper()}...")
    params = {
        "building": tower,
        "sheet": SHEET_ID
    }
    try:
        response = requests.get(BINDEX_API_URL, params=params, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") and "values" in data:
                return data["values"]
            else:
                print(f"No active data in API response for Tower {tower.upper()}.")
        else:
            print(f"API Error {response.status_code} for Tower {tower.upper()}.")
    except Exception as e:
        print(f"Failed to fetch from Bindex API for Tower {tower.upper()}: {e}")
    return []

def populate_database_from_bindex():
    """
    Fetches all companies for C, I, T, Y and populates the SQLite database.
    """
    database.init_db()
    total_added = 0
    for tower in TOWERS:
        companies = fetch_bindex_companies(tower)
        for c in companies:
            # Bindex API returns:
            # floor, title1 (or title2/keywords), cat, phone, whatsapp, representative1, entrance, keywords etc.
            name = c.get("title1") or c.get("title")
            if not name:
                continue
            
            floor = c.get("floor")
            try:
                floor = int(floor) if floor is not None else None
            except ValueError:
                floor = 0
                
            category = c.get("cat") or c.get("category")
            keywords = c.get("keywords")
            phone = c.get("phone")
            whatsapp = c.get("whatsapp")
            representative = c.get("representative1") or c.get("representative")
            entrance = c.get("entrance")
            
            # Upsert into database (will preserve site_url / job results if already completed)
            db_id = database.upsert_company(
                tower=tower.upper(),
                floor=floor,
                name=name.strip(),
                category=category,
                keywords=keywords,
                phone=phone,
                whatsapp=whatsapp,
                representative=representative,
                entrance=entrance
            )
            if db_id:
                total_added += 1
                
    print(f"Finished populating database. Upserted {total_added} companies.")

# -----------------
# 2. Website URL Resolution (Web Search)
# -----------------
def clean_domain(url):
    """
    Checks if a URL belongs to a directory, social media, or other noise that isn't a business website.
    """
    if not url:
        return None
    
    parsed = urllib.parse.urlparse(url.lower())
    netloc = parsed.netloc or parsed.path
    netloc = netloc.replace("www.", "")
    
    ignored_domains = [
        'bindex.info', 'easy.co.il', 'duns100.co.il', 'facebook.com', 'linkedin.com',
        'instagram.com', 'yellowpages.co.il', 'd.co.il', 'youtube.com', 'checkid.co.il',
        'gov.il', 'wikipedia.org', 'waze.com', 'mapa.co.il', 'infobiz.co.il',
        'guidestar.org.il', 'zoomap.co.il', 'behance.net', 'github.com', 'twitter.com',
        'bsr.co.il', 'bsr-group.co.il', 'bsr-group.com', 'bsr.org.il'
    ]
    
    for domain in ignored_domains:
        if domain in netloc:
            return None
            
    return url

def scrape_ddg(query):
    """Query DuckDuckGo for organic results."""
    encoded_query = urllib.parse.quote_plus(query)
    search_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
    try:
        response = requests.get(search_url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            for result_div in soup.find_all('div', class_='result'):
                a_title = result_div.find('a', class_='result__title')
                if not a_title:
                    continue
                href = a_title.get('href')
                if not href:
                    continue
                title_text = a_title.get_text(strip=True)
                
                parsed_href = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                resolved_url = parsed_href['uddg'][0] if 'uddg' in parsed_href else href
                
                cleaned_url = clean_domain(resolved_url)
                if not cleaned_url:
                    continue
                
                div_snippet = result_div.find('a', class_='result__snippet')
                snippet_text = div_snippet.get_text(strip=True) if div_snippet else ""
                
                results.append({
                    'url': cleaned_url,
                    'title': title_text,
                    'snippet': snippet_text
                })
            return results
    except Exception as e:
        print(f"[SEARCH RESOLVER] DDG parser error: {e}")
    return []

def scrape_yahoo(query):
    """Query Yahoo Search as a reliable fallback."""
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://search.yahoo.com/search?q={encoded_query}"
    print(f"[SEARCH RESOLVER] Querying Yahoo fallback: '{query}'...")
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            for div in soup.find_all('div', class_='algo'):
                a = div.find('a')
                if not a:
                    continue
                href = a.get('href')
                if not href or href.startswith(('javascript:', '#')):
                    continue
                
                # Extract clean URL from Yahoo redirect
                if 'RU=' in href:
                    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                    if 'RU' in parsed:
                        href = parsed['RU'][0]
                        
                cleaned = clean_domain(href)
                if not cleaned:
                    continue
                
                title = a.get_text(strip=True)
                
                snippet_div = div.find(class_='compText') or div.find('p') or div.find('span')
                snippet = snippet_div.get_text(strip=True) if snippet_div else ""
                
                results.append({
                    'url': cleaned,
                    'title': title,
                    'snippet': snippet
                })
            return results
    except Exception as e:
        print(f"[SEARCH RESOLVER] Yahoo parser error: {e}")
    return []

def scrape_bing(query):
    """Query Bing Search as a reliable fallback."""
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://www.bing.com/search?q={encoded_query}"
    print(f"[SEARCH RESOLVER] Querying Bing fallback: '{query}'...")
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            for li in soup.find_all('li', class_='b_algo'):
                h2 = li.find('h2')
                a = h2.find('a') if h2 else li.find('a')
                if not a:
                    continue
                href = a.get('href')
                if not href or href.startswith(('javascript:', '#')):
                    continue
                    
                cleaned = clean_domain(href)
                if not cleaned:
                    continue
                    
                title = a.get_text(strip=True)
                snippet_div = li.find('p') or li.find('span')
                snippet = snippet_div.get_text(strip=True) if snippet_div else ""
                
                results.append({
                    'url': cleaned,
                    'title': title,
                    'snippet': snippet
                })
            return results
    except Exception as e:
        print(f"[SEARCH RESOLVER] Bing parser error: {e}")
    return []

def search_website_for_business(business_name):
    """
    Resolves a business name to their official website using multi-engine fallbacks (DDG -> Yahoo -> Bing).
    Completely immune to DDG rate-limiting. Employs Gemini or strict local heuristics.
    """
    # Clean up the search query itself by replacing slashes/dashes/commas with spaces
    # Otherwise slashes in search queries confuse search engine request parsers!
    clean_business_name = business_name.replace("/", " ").replace("-", " ").replace(",", " ")
    query = f"{clean_business_name} בסר פתח תקווה"
    
    # 1. Query DuckDuckGo
    print(f"[SEARCH RESOLVER] Querying DuckDuckGo: '{query}'...")
    results = scrape_ddg(query)
    
    # 2. Query Yahoo Fallback if blocked
    if not results:
        results = scrape_yahoo(query)
        
    # 3. Query Bing Fallback if Yahoo also fails
    if not results:
        results = scrape_bing(query)
        
    # 4. Process results if any engine succeeded
    if results:
        print(f"[SEARCH RESOLVER] Found {len(results)} potential search results for '{business_name}':")
        for idx, r in enumerate(results[:3]):
            print(f"  Result #{idx+1}: URL='{r['url']}' | Title='{r['title']}'")
        # --- Mode A: Gemini AI Verification ---
        if HAS_GEMINI and gemini_model:
            try:
                print(f"[SEARCH RESOLVER] Querying Gemini to select official site from search results...")
                results_summary = "\n".join([f"- Title: '{r['title']}'\n  URL: '{r['url']}'\n  Desc: '{r['snippet']}'" for r in results[:4]])
                prompt = (
                    f"You are a web crawling assistant. A company named '{business_name}' is located in B.S.R. Towers in Petah Tikva, Israel.\n"
                    f"Here are the top search results for this company:\n\n"
                    f"{results_summary}\n\n"
                    f"Determine which URL is the actual official homepage of the company '{business_name}'.\n"
                    f"- Respond ONLY with the exact URL.\n"
                    f"- Exclude third-party directories, general tower portals (like bsr.co.il), unrelated blogs, or other companies.\n"
                    f"- If there is NO official website for the company among these results, respond with the string 'NULL'."
                )
                llm_res = gemini_model.generate_content(prompt)
                selected_url = llm_res.text.strip().replace('`', '')
                
                if selected_url and selected_url != "NULL" and selected_url.startswith("http"):
                    print(f"[SEARCH RESOLVER] Gemini verified website: {selected_url}")
                    return selected_url
                else:
                    print(f"[SEARCH RESOLVER] Gemini determined that company '{business_name}' has no official website in search results.")
                    return None
            except Exception as e:
                print(f"[SEARCH RESOLVER] Gemini verification exception: {e}. Falling back to strict local heuristic.")
        
        # --- Mode B: Strict Local Heuristic Match ---
        stop_words = {'בע"מ', 'בעמ', 'ישראל', 'קבוצת', 'שירותי', 'שרותי', 'מערכות', 'פתרונות', 'כספים', 'אחזקות', 'ltd', 'group', 'israel', 'systems', 'solutions', 'holdings', 'services', 'inc', 'corp', 'co'}
        normalized_name = business_name.replace("/", " ").replace("-", " ").replace(",", " ")
        name_words = [re.sub(r'[^\w\s]', '', w).lower() for w in normalized_name.split()]
        keywords = [w for w in name_words if len(w) > 1 and w not in stop_words]
        
        if not keywords:
            keywords = [re.sub(r'[^\w\s]', '', business_name).lower()]
        
        print(f"[SEARCH RESOLVER] Running strict local keywords search: {keywords}")
        
        for r in results[:4]:
            title_lower = r['title'].lower()
            snippet_lower = r['snippet'].lower()
            url_lower = r['url'].lower()
            
            matched = False
            for kw in keywords:
                if kw in title_lower or kw in url_lower or kw in snippet_lower:
                    matched = True
                    break
                    
            if matched:
                print(f"[SEARCH RESOLVER] Strictly resolved website: {r['url']}")
                return r['url']
                
        print(f"[SEARCH RESOLVER] Strictly rejected all results for '{business_name}' due to keyword mismatch.")
        
    else:
        print(f"[SEARCH RESOLVER] All search engines (DDG, Yahoo, Bing) returned 0 results. Rate-limited or offline.")
        
    return None

# -----------------
# 3. Menu Navigation & Careers Page Crawling
# -----------------
def find_menu_and_career_links(homepage_url):
    """
    Crawls the homepage, extracts all unique local links, and inspects
    menus/headers for potential career paths.
    """
    try:
        response = requests.get(homepage_url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            return [], ""
            
        soup = BeautifulSoup(response.text, 'html.parser')
        raw_html = response.text
        
        # Parse absolute homepage URL domain
        parsed_home = urllib.parse.urlparse(homepage_url)
        base_domain = f"{parsed_home.scheme}://{parsed_home.netloc}"
        
        # 1. Inspect navigation structures and standard link blocks
        links_data = []
        seen_urls = set()
        
        # Scrape all anchor elements
        for a in soup.find_all('a'):
            href = a.get('href')
            if not href or href.startswith(('#', 'javascript:', 'tel:', 'mailto:')):
                continue
                
            # Make URL absolute
            abs_url = urllib.parse.urljoin(homepage_url, href)
            
            # Ensure it is a local link within the same domain
            parsed_abs = urllib.parse.urlparse(abs_url)
            if parsed_abs.netloc != parsed_home.netloc:
                continue
                
            # Deduplicate
            if abs_url in seen_urls:
                continue
            seen_urls.add(abs_url)
            
            # Grab containing section (e.g. is it inside <nav>, <header>, or menu list?)
            in_menu = False
            parent = a.parent
            depth = 0
            while parent and depth < 6:
                parent_tag = parent.name
                parent_class = " ".join(parent.get('class', [])) if parent.get('class') else ""
                parent_id = parent.get('id', "")
                
                if parent_tag in ('nav', 'header') or 'menu' in parent_class.lower() or 'nav' in parent_class.lower() or 'menu' in parent_id.lower() or 'nav' in parent_id.lower():
                    in_menu = True
                    break
                parent = parent.parent
                depth += 1
                
            text = a.get_text(strip=True)
            title = a.get('title', "")
            
            links_data.append({
                'url': abs_url,
                'text': text,
                'title': title,
                'in_menu': in_menu
            })
            
        return links_data, raw_html
    except Exception as e:
        print(f"Error crawling homepage {homepage_url}: {e}")
        return [], ""

def resolve_careers_link_via_llm(homepage_url, links):
    """
    Resolves the careers URL. Uses Google Gemini API if GEMINI_API_KEY is active,
    otherwise gracefully falls back to a robust keyword heuristic engine.
    """
    if HAS_GEMINI and gemini_model:
        try:
            print(f"[LLM LINK RESOLVER] Querying Gemini for careers path on {homepage_url}...")
            links_summary = "\n".join([f"- Text: '{l['text']}', URL: '{l['url']}', InMenu: {l['in_menu']}" for l in links])
            prompt = (
                f"You are a web crawling assistant. Analyze this list of local navigation links found on the homepage: {homepage_url}.\n\n"
                f"Available Links:\n{links_summary}\n\n"
                f"Identify which URL is the Careers/Jobs/דרושים/קריירה page. "
                f"Respond ONLY with the exact absolute URL of the careers page. If there is no clear careers page, respond with the string 'NULL'."
            )
            response = gemini_model.generate_content(prompt)
            result_url = response.text.strip().replace('`', '')
            
            if result_url and result_url != "NULL" and result_url.startswith("http"):
                print(f"[LLM LINK RESOLVER] Gemini resolved careers URL: {result_url}")
                return result_url
            else:
                print(f"[LLM LINK RESOLVER] Gemini could not identify careers URL. Falling back to local heuristic.")
        except Exception as e:
            print(f"[LLM LINK RESOLVER] Gemini API exception: {e}. Falling back to local heuristic.")
            
    # HEURISTIC LINK MATCHING (LOCAL BACKUP CRAWLER)
    # Target keywords in English and Hebrew
    career_keywords = [
        r'career', r'job', r'join', r'work-with-us', r'workwithus', r'hiring', r'vacancy', r'opportunity',
        r'דרושים', r'קריירה', r'עבודה', r'הצטרפו', r'משרות', r'גיוס'
    ]
    
    best_link = None
    best_score = 0
    
    for item in links:
        score = 0
        url_lower = item['url'].lower()
        text_lower = item['text'].lower()
        title_lower = item['title'].lower()
        
        # Match keywords
        for keyword in career_keywords:
            if re.search(keyword, url_lower):
                score += 3
            if re.search(keyword, text_lower):
                score += 5
            if re.search(keyword, title_lower):
                score += 4
                
        # Give a boost if the link is located in a navigation menu
        if score > 0 and item['in_menu']:
            score += 2
            
        # Prioritize exact path matches e.g. /careers or /דרושים
        if re.search(r'/(careers|jobs|join|דרושים|קריירה)/?$', url_lower):
            score += 4
            
        if score > best_score:
            best_score = score
            best_link = item['url']
            
    if best_link:
        print(f"Heuristically resolved careers page (score {best_score}): {best_link}")
        return best_link
        
    return None

# -----------------
# 4. Job Extraction & LLM Filtering
# -----------------
def extract_jobs_from_page(url):
    """
    Fetches the career page and extracts raw text/structured lists of jobs.
    """
    print(f"Fetching careers page content: {url}...")
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            return "", []
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove script and style elements to clean raw text
        for s in soup(["script", "style", "meta", "noscript", "iframe"]):
            s.decompose()
            
        # Get raw text
        raw_text = soup.get_text(separator=' \n ', strip=True)
        
        # Local heuristic structured extraction
        # Look for headers containing job-like titles or block elements
        detected_positions = []
        
        # 1. Parse headers first as they often contain Job Titles
        # Typically jobs are in <h3>, <h4> or <h2> tags on careers pages
        job_title_blacklist = ['דרושים', 'קריירה', 'עבודה אצלנו', 'משרות פתוחות', 'open positions', 'careers', 'jobs', 'הצטרפו אלינו']
        
        for heading in soup.find_all(['h2', 'h3', 'h4', 'h5']):
            title = heading.get_text(strip=True)
            # Ensure it's not a generic page header, has reasonable length (3-60 chars)
            if len(title) > 3 and len(title) < 60:
                # Avoid blacklist
                if not any(black in title.lower() for black in job_title_blacklist):
                    # Check for indicators of a job title
                    # e.g., contains specific letters, or Hebrew/English job markers
                    # (in a careers page, headers are usually job titles!)
                    detected_positions.append(title)
                    
        # 2. Parse job container divs
        # E.g. divs with class names containing job, position, role etc.
        for div in soup.find_all('div'):
            classes = div.get('class', [])
            class_str = " ".join(classes).lower() if isinstance(classes, list) else str(classes).lower()
            if 'job-title' in class_str or 'position-title' in class_str or 'mishra' in class_str:
                title = div.get_text(strip=True)
                if len(title) > 3 and len(title) < 60 and title not in detected_positions:
                    detected_positions.append(title)
                    
        # Clean up positions list
        cleaned_positions = []
        for pos in detected_positions:
            pos_clean = re.sub(r'\s+', ' ', pos).strip()
            # Basic validation
            if len(pos_clean) > 4 and not pos_clean.isdigit():
                cleaned_positions.append(pos_clean)
                
        # Remove duplicates while preserving order
        unique_positions = []
        for pos in cleaned_positions:
            if pos not in unique_positions:
                unique_positions.append(pos)
                
        return raw_text, unique_positions
    except Exception as e:
        print(f"Error scraping careers page {url}: {e}")
        return "", []

def llm_filter_positions(raw_text, local_positions):
    """
    Filters and formats extracted position candidates. Uses Google Gemini API if
    GEMINI_API_KEY is active to extract high-fidelity structured positions,
    otherwise falls back to a clean local heuristic keyword processor.
    """
    if HAS_GEMINI and gemini_model:
        try:
            print("[LLM JOB FILTER] Querying Gemini to extract high-fidelity positions...")
            prompt = (
                f"You are a recruitment coordinator assistant. Analyze the raw text scraped from a company's careers page, "
                f"and extract a clean list of active open job positions.\n\n"
                f"Candidate Titles Found:\n{local_positions}\n\n"
                f"Raw Page Text Snippet:\n{raw_text[:8000]}\n\n"
                f"Instructions:\n"
                f"1. Filter out boilerplate headers, footers, and non-job titles from the candidates list.\n"
                f"2. Return the result strictly as a valid JSON array of objects. Each object MUST have these exact fields:\n"
                f"   - 'title': The job title (preserve Hebrew or English as written)\n"
                f"   - 'department': The department (e.g. R&D, Sales, Finance, Operations, or 'General')\n"
                f"   - 'status': Set to 'Gemini Verified'\n"
                f"Respond ONLY with the raw JSON array string. Do not include markdown code block syntax (```json) or extra text."
            )
            response = gemini_model.generate_content(prompt)
            clean_res = response.text.strip().replace('```json', '').replace('```', '').strip()
            
            # Attempt to parse json
            parsed_jobs = json.loads(clean_res)
            if isinstance(parsed_jobs, list):
                print(f"[LLM JOB FILTER] Gemini successfully verified {len(parsed_jobs)} jobs.")
                return parsed_jobs
        except Exception as e:
            print(f"[LLM JOB FILTER] Gemini API exception: {e}. Falling back to local heuristic.")
            
    # HEURISTIC FILTER BACKUP (LOCAL & ZERO COST)
    # Filter the positions list we got from the headers
    # Ensure they actually look like job titles (e.g. Manager, Engineer, Analyst, מפתח, מנהל, נציג etc.)
    role_indicators = [
        r'developer', r'engineer', r'manager', r'specialist', r'analyst', r'lead', r'intern', r'expert', r'designer',
        r'מפתח', r'מהנדס', r'מנהל', r'ראש צוות', r'נציג', r'איש/ת', r'מתכנת', r'ארכיטקט', r'מיישם', r'אנליסט', r'יועץ',
        r'מזכיר', r'אחראי/ת', r'רכז/ת', r'רואה חשבון', r'עורך דין', r'אופרטור', r'טכנאי', r'מדען'
    ]
    
    filtered_jobs = []
    for pos in local_positions:
        has_indicator = False
        pos_lower = pos.lower()
        for ind in role_indicators:
            if re.search(ind, pos_lower):
                has_indicator = True
                break
                
        # If the page was small or list is small, keep all detected positions
        if has_indicator or len(local_positions) < 6:
            filtered_jobs.append({
                "title": pos,
                "status": "Local heuristic (LLM pending)",
                "department": "Unknown"
            })
            
    return filtered_jobs

# -----------------
# 5. Master Scraping Controller Loop
# -----------------
class ScrapingProgress:
    total = 0
    current_index = 0
    current_company = ""
    is_running = False
    logs = []

    @classmethod
    def reset(cls):
        cls.total = 0
        cls.current_index = 0
        cls.current_company = ""
        cls.is_running = False
        cls.logs = []

    @classmethod
    def log(cls, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        print(log_entry)
        cls.logs.append(log_entry)
        # Limit logs to last 200 lines
        if len(cls.logs) > 200:
            cls.logs.pop(0)

from datetime import datetime

def run_scraper_process():
    """
    Main loop. Running this will load new companies from the Bindex API,
    then crawl each company to resolve website and extract open jobs.
    Perfect checkpoint-resumability: ignores already completed entries.
    """
    if ScrapingProgress.is_running:
        ScrapingProgress.log("Scraper is already running.")
        return
        
    ScrapingProgress.reset()
    ScrapingProgress.is_running = True
    ScrapingProgress.log("Initializing Scraper engine...")
    
    try:
        # Step 1: Pull details from Bindex API first
        ScrapingProgress.log("Synchronizing business directory with Bindex sheets...")
        populate_database_from_bindex()
        
        # Step 2: Get all companies that are pending scraping
        pending = database.get_pending_companies()
        ScrapingProgress.total = len(pending)
        ScrapingProgress.log(f"Found {ScrapingProgress.total} companies pending/failed in the queue.")
        
        if ScrapingProgress.total == 0:
            ScrapingProgress.log("All companies are already scraped! Nothing to do.")
            ScrapingProgress.is_running = False
            return
            
        for i, company in enumerate(pending):
            if not ScrapingProgress.is_running:
                ScrapingProgress.log("Scraping paused by user command.")
                break
                
            ScrapingProgress.current_index = i + 1
            ScrapingProgress.current_company = company['business_name']
            company_id = company['id']
            name = company['business_name']
            
            ScrapingProgress.log(f"({i+1}/{ScrapingProgress.total}) Processing: {name} (Tower {company['tower']})")
            
            # Substep A: Resolve Website URL if empty
            site_url = company['site_url']
            if not site_url:
                database.update_company_status(company_id, 'RESOLVING_SITE')
                ScrapingProgress.log(f"Resolving website URL for '{name}'...")
                site_url = search_website_for_business(name)
                
                if not site_url:
                    # Failed to find website, mark as completed but without URL (avoids repeated searches)
                    database.save_scraped_data(company_id, None, None, "", [], [], 'COMPLETED')
                    ScrapingProgress.log(f"No website resolved for '{name}'. Skipping crawler.")
                    time.sleep(1.5)
                    continue
                else:
                    database.update_company_url(company_id, site_url)
            
            # Substep B: Crawl Website & search Careers page
            database.update_company_status(company_id, 'SEARCHING_JOBS')
            ScrapingProgress.log(f"Crawling homepage: {site_url}")
            links, homepage_raw = find_menu_and_career_links(site_url)
            
            careers_url = None
            raw_jobs_text = ""
            positions_list = []
            filtered_jobs = []
            
            if links:
                ScrapingProgress.log(f"Extracted {len(links)} navigation links. Resolving careers path...")
                careers_url = resolve_careers_link_via_llm(site_url, links)
                
            # Substep C: Scrape careers/jobs content
            if careers_url:
                ScrapingProgress.log(f"Careers URL identified: {careers_url}")
                raw_jobs_text, positions_list = extract_jobs_from_page(careers_url)
            else:
                # Fallback: scrape homepage directly for job patterns
                ScrapingProgress.log("No distinct careers page found. Fallback: extracting from homepage directly.")
                raw_jobs_text, positions_list = extract_jobs_from_page(site_url)
                careers_url = site_url
                
            # Substep D: Filter positions using local / LLM filter
            if positions_list:
                ScrapingProgress.log(f"Heuristically extracted {len(positions_list)} raw positions. Running filter...")
                filtered_jobs = llm_filter_positions(raw_jobs_text, positions_list)
                ScrapingProgress.log(f"Filtered down to {len(filtered_jobs)} structured positions.")
            else:
                ScrapingProgress.log("No job listings detected on careers page.")
                
            # Substep E: Save to DB
            database.save_scraped_data(
                company_id=company_id,
                site_url=site_url,
                careers_url=careers_url,
                raw_text=raw_jobs_text,
                open_positions=positions_list,
                llm_filtered=filtered_jobs,
                status='COMPLETED'
            )
            ScrapingProgress.log(f"Successfully processed {name}.")
            
            # Be polite and rate limit requests
            time.sleep(2)
            
    except Exception as e:
        ScrapingProgress.log(f"CRITICAL ERROR in scraper process: {e}")
    finally:
        ScrapingProgress.is_running = False
        ScrapingProgress.log("Scraper loop completed.")

def stop_scraper_process():
    if ScrapingProgress.is_running:
        ScrapingProgress.is_running = False
        ScrapingProgress.log("Initiating stop sequence...")
    else:
        print("Scraper is already idle.")
