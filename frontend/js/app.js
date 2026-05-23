// State Management
let companies = [];
let filteredCompaniesList = [];
let currentTowerFilter = 'ALL';
let searchQuery = '';
let selectedCompanyForUrl = null;
let scraperPollInterval = null;
let knownLogsCount = 0;

// On Initialization
document.addEventListener("DOMContentLoaded", () => {
    loadCompanies();
    // Start polling scraper status in case it is already running
    pollScraperStatus();
    scraperPollInterval = setInterval(pollScraperStatus, 1500);
});

// -----------------
// 1. Loading Data from Backend
// -----------------
async function loadCompanies() {
    try {
        const response = await fetch('/api/companies');
        if (!response.ok) throw new Error("Failed to fetch companies database");
        companies = await response.json();
        
        // Calculate Metrics
        updateMetrics();
        // Render
        filterCompanies();
    } catch (error) {
        console.error("Error loading directory:", error);
        document.getElementById("companiesGrid").innerHTML = `
            <div class="error-state">
                <span style="font-size: 32px; display: block; margin-bottom: 10px;">⚠️</span>
                Failed to load database. Is the FastAPI backend running?
            </div>
        `;
    }
}

function updateMetrics() {
    const total = companies.length;
    const resolved = companies.filter(c => c.site_url).length;
    
    // Calculate companies with open jobs
    const withJobs = companies.filter(c => {
        try {
            const jobs = JSON.parse(c.llm_filtered_positions || '[]');
            return jobs.length > 0;
        } catch {
            return false;
        }
    }).length;
    
    document.getElementById("metricTotal").innerText = total;
    document.getElementById("metricResolved").innerText = resolved;
    document.getElementById("metricJobs").innerText = withJobs;
}

// -----------------
// 2. Rendering Directory Cards
// -----------------
function setTowerFilter(tower) {
    currentTowerFilter = tower;
    
    // Update active pill UI
    const pills = document.querySelectorAll("#towerPills .pill");
    pills.forEach(pill => {
        if (pill.getAttribute("data-tower") === tower) {
            pill.classList.add("active");
        } else {
            pill.classList.remove("active");
        }
    });
    
    filterCompanies();
}

function filterCompanies() {
    searchQuery = document.getElementById("searchInput").value.toLowerCase().trim();
    const statusFilter = document.getElementById("statusFilter").value;
    
    filteredCompaniesList = companies.filter(c => {
        // Tower filter
        if (currentTowerFilter !== 'ALL' && c.tower !== currentTowerFilter) {
            return false;
        }
        
        // Search query (matches name, category, or jobs)
        const nameMatch = c.business_name.toLowerCase().includes(searchQuery);
        const categoryMatch = (c.category || '').toLowerCase().includes(searchQuery);
        const keywordMatch = (c.keywords || '').toLowerCase().includes(searchQuery);
        
        let jobMatch = false;
        try {
            const rawJobs = JSON.parse(c.open_positions || '[]');
            jobMatch = rawJobs.some(job => job.toLowerCase().includes(searchQuery));
        } catch {}
        
        const matchesQuery = nameMatch || categoryMatch || keywordMatch || jobMatch;
        if (!matchesQuery) return false;
        
        // Careers Status Filter
        let jobsList = [];
        try { jobsList = JSON.parse(c.llm_filtered_positions || '[]'); } catch {}
        
        if (statusFilter === 'HAS_JOBS') {
            return jobsList.length > 0;
        } else if (statusFilter === 'HAS_URL') {
            return !!c.site_url;
        } else if (statusFilter === 'NO_URL') {
            return !c.site_url;
        } else if (statusFilter === 'PENDING') {
            return c.search_status === 'PENDING';
        } else if (statusFilter === 'COMPLETED') {
            return c.search_status === 'COMPLETED';
        }
        
        return true;
    });
    
    renderGrid();
}

function renderGrid() {
    const grid = document.getElementById("companiesGrid");
    document.getElementById("resultsCount").innerText = `Showing ${filteredCompaniesList.length} companies`;
    
    if (filteredCompaniesList.length === 0) {
        grid.innerHTML = `
            <div class="loading-state">
                🔍 No companies match your search and filter criteria.
            </div>
        `;
        return;
    }
    
    grid.innerHTML = filteredCompaniesList.map(c => {
        let jobsCount = 0;
        try {
            const jobs = JSON.parse(c.llm_filtered_positions || '[]');
            jobsCount = jobs.length;
        } catch {}
        
        // Determine Job status badge classes
        let indicatorHtml = "";
        if (c.search_status === 'RESOLVING_SITE') {
            indicatorHtml = `<div class="jobs-indicator pending"><span class="spinner" style="margin-right: 8px;"></span>Resolving website URL...</div>`;
        } else if (c.search_status === 'SEARCHING_JOBS') {
            indicatorHtml = `<div class="jobs-indicator pending"><span class="spinner" style="margin-right: 8px;"></span>Searching careers page...</div>`;
        } else if (!c.site_url) {
            indicatorHtml = `<div class="jobs-indicator empty">No Website Resolved</div>`;
        } else if (c.search_status === 'FAILED') {
            indicatorHtml = `<div class="jobs-indicator failed">Scrape Failed</div>`;
        } else if (jobsCount > 0) {
            indicatorHtml = `<div class="jobs-indicator found">🔥 ${jobsCount} Open Positions</div>`;
        } else {
            indicatorHtml = `<div class="jobs-indicator empty">0 Positions Found</div>`;
        }
        
        const towerClass = c.tower.toLowerCase();
        const floorText = c.floor !== null ? `Floor ${c.floor}` : 'Floor Unknown';
        
        return `
            <div class="company-card glass-card" id="card-${c.id}">
                <div class="card-header">
                    <span class="tower-badge ${towerClass}">${c.tower}</span>
                    <span class="floor-badge">${floorText}</span>
                </div>
                
                <div class="card-body">
                    <h3 class="company-title" title="${c.business_name}">${c.business_name}</h3>
                    <div class="company-category">${c.category || 'General Business'}</div>
                    
                    <div class="meta-info">
                        ${c.representative ? `<div class="meta-row"><span>👤</span> ${c.representative}</div>` : ''}
                        ${c.phone ? `<div class="meta-row"><span>📞</span> ${c.phone}</div>` : ''}
                        ${c.entrance ? `<div class="meta-row"><span>🚪</span> ${c.entrance}</div>` : ''}
                    </div>
                    
                    ${indicatorHtml}
                    
                    <div class="card-actions">
                        <button class="btn btn-secondary" onclick="viewJobPositions(${c.id})" ${jobsCount === 0 ? 'disabled' : ''}>
                            View Positions
                        </button>
                        <button class="btn btn-action btn-secondary" title="Edit Website URL" onclick="openUrlModal(${c.id}, '${c.site_url || ''}')">
                            ✏️
                        </button>
                        <button class="btn btn-action btn-secondary" title="Force Scrape URL" onclick="forceSingleScrape(${c.id}, this)">
                            🔄
                        </button>
                    </div>
                </div>
            </div>
        `;
    }).join("");
}

// -----------------
// 3. Managing Scraper (Control Panel)
// -----------------
async function startScraper() {
    try {
        const response = await fetch('/api/scraper/start', { method: 'POST' });
        const data = await response.json();
        
        appendSystemLog(`[SYSTEM] Scraper started: ${data.message}`);
        // Visual switch
        document.getElementById("btnStart").classList.add("hidden");
        document.getElementById("btnStop").classList.remove("hidden");
    } catch (error) {
        appendSystemLog(`[ERROR] Failed to start scraper: ${error.message}`);
    }
}

async function stopScraper() {
    try {
        const response = await fetch('/api/scraper/stop', { method: 'POST' });
        const data = await response.json();
        
        appendSystemLog(`[SYSTEM] Stopping scraper: ${data.message}`);
    } catch (error) {
        appendSystemLog(`[ERROR] Failed to stop scraper: ${error.message}`);
    }
}

async function pollScraperStatus() {
    try {
        const response = await fetch('/api/scraper/status');
        const data = await response.json();
        
        const dot = document.getElementById("statusDot");
        const text = document.getElementById("statusText");
        const progressContainer = document.getElementById("progressContainer");
        const progressBar = document.getElementById("progressBar");
        const progressCompany = document.getElementById("progressCompany");
        const progressRatio = document.getElementById("progressRatio");
        
        if (data.is_running) {
            dot.className = "status-dot active";
            text.innerText = "Crawling Towers...";
            
            // Buttons
            document.getElementById("btnStart").classList.add("hidden");
            document.getElementById("btnStop").classList.remove("hidden");
            
            // Progress Bar
            progressContainer.classList.remove("hidden");
            progressCompany.innerText = data.current_company || "Initializing...";
            progressRatio.innerText = `${data.current_index}/${data.total}`;
            progressBar.style.width = `${data.progress_percent}%`;
        } else {
            const isStopping = data.logs.length > 0 && data.logs[data.logs.length - 1].includes("stop");
            dot.className = isStopping ? "status-dot stopping" : "status-dot";
            text.innerText = isStopping ? "Stopping..." : "Idle";
            
            // Buttons
            document.getElementById("btnStart").classList.remove("hidden");
            document.getElementById("btnStop").classList.add("hidden");
            
            progressContainer.classList.add("hidden");
        }
        
        // Append new logs to Console Log Panel
        if (data.logs && data.logs.length > knownLogsCount) {
            const consoleLogs = document.getElementById("consoleLogs");
            const newLogs = data.logs.slice(knownLogsCount);
            
            newLogs.forEach(log => {
                const div = document.createElement("div");
                div.className = "log-entry";
                
                if (log.includes("[ERROR]") || log.includes("CRITICAL")) div.classList.add("error");
                else if (log.includes("Successfully") || log.includes("completed")) div.classList.add("success");
                else if (log.includes("[SYSTEM]")) div.classList.add("system");
                
                div.innerText = log;
                consoleLogs.appendChild(div);
            });
            
            knownLogsCount = data.logs.length;
            // Scroll to bottom
            consoleLogs.scrollTop = consoleLogs.scrollHeight;
            
            // Auto reload database when scraper state finishes crawling
            loadCompanies();
        }
    } catch (error) {
        console.error("Error polling scraper:", error);
    }
}

// -----------------
// 4. Force Single-Company Scrape
// -----------------
async function forceSingleScrape(companyId, btnElement) {
    // Show spinner inside card actions
    const originalContent = btnElement.innerText;
    btnElement.innerHTML = `<span class="spinner"></span>`;
    btnElement.disabled = true;
    
    appendSystemLog(`[SYSTEM] Starting target scrape for Company #${companyId}...`);
    
    try {
        const response = await fetch(`/api/companies/${companyId}/re-scrape`, { method: 'POST' });
        const data = await response.json();
        
        if (response.ok && data.status === "completed") {
            appendSystemLog(`[SUCCESS] Re-scraped successfully: ${data.message}`);
            // Reload database
            await loadCompanies();
        } else {
            appendSystemLog(`[ERROR] Re-scrape failed: ${data.message || 'Scrape resolution error'}`);
            await loadCompanies();
        }
    } catch (error) {
        appendSystemLog(`[ERROR] Network error scraping Company #${companyId}: ${error.message}`);
    } finally {
        btnElement.innerHTML = originalContent;
        btnElement.disabled = false;
    }
}

// -----------------
// 5. Update Company Website URL Modal
// -----------------
function openUrlModal(companyId, currentUrl) {
    selectedCompanyForUrl = companyId;
    document.getElementById("editUrlInput").value = currentUrl;
    document.getElementById("urlModal").classList.remove("hidden");
}

function closeUrlModal() {
    selectedCompanyForUrl = null;
    document.getElementById("urlModal").classList.add("hidden");
}

async function saveCompanyUrl() {
    if (!selectedCompanyForUrl) return;
    
    const inputUrl = document.getElementById("editUrlInput").value.trim();
    const btn = document.getElementById("btnSaveUrl");
    
    btn.disabled = true;
    btn.innerText = "Saving...";
    
    try {
        const response = await fetch(`/api/companies/${selectedCompanyForUrl}/url`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: inputUrl })
        });
        
        if (response.ok) {
            appendSystemLog(`[SYSTEM] Updated website URL for Company #${selectedCompanyForUrl}`);
            closeUrlModal();
            loadCompanies();
        } else {
            alert("Failed to update website URL");
        }
    } catch (error) {
        console.error("Error saving URL:", error);
    } finally {
        btn.disabled = false;
        btn.innerText = "Save Website";
    }
}

// -----------------
// 6. View Positions Modal
// -----------------
function viewJobPositions(companyId) {
    const c = companies.find(item => item.id === companyId);
    if (!c) return;
    
    document.getElementById("modalTower").innerText = c.tower;
    document.getElementById("modalTower").className = `tower-badge ${c.tower.toLowerCase()}`;
    document.getElementById("modalName").innerText = c.business_name;
    document.getElementById("modalCategory").innerText = c.category || 'General Business';
    
    // Floor info
    const floorText = c.floor !== null ? `Floor ${c.floor}` : 'Floor Unknown';
    const entranceText = c.entrance ? `, ${c.entrance}` : '';
    document.getElementById("modalFloor").innerText = `${floorText}${entranceText}`;
    
    // Representative
    document.getElementById("modalRepresentative").innerText = c.representative || 'Reception Desk';
    
    // Website link
    const webLink = document.getElementById("modalWebsiteLink");
    if (c.site_url) {
        webLink.href = c.site_url;
        webLink.innerText = `${c.site_url.replace("https://", "").replace("http://", "")} 🔗`;
        webLink.style.display = "inline-block";
    } else {
        webLink.style.display = "none";
    }
    
    // Careers link
    const careersLink = document.getElementById("modalCareersLink");
    const careersGroup = document.getElementById("modalCareersGroup");
    if (c.careers_url) {
        careersLink.href = c.careers_url;
        careersGroup.style.display = "block";
    } else {
        careersGroup.style.display = "none";
    }
    
    // Contact actions
    const phoneBtn = document.getElementById("modalCall");
    if (c.phone) {
        phoneBtn.href = `tel:${c.phone}`;
        phoneBtn.style.display = "block";
    } else {
        phoneBtn.style.display = "none";
    }
    
    const waBtn = document.getElementById("modalWhatsapp");
    if (c.whatsapp) {
        waBtn.href = `https://wa.me/${c.whatsapp}`;
        waBtn.style.display = "block";
    } else {
        waBtn.style.display = "none";
    }
    
    // Open positions parsing
    let jobsList = [];
    try {
        jobsList = JSON.parse(c.llm_filtered_positions || '[]');
    } catch {}
    
    const listContainer = document.getElementById("modalJobsList");
    if (jobsList.length === 0) {
        listContainer.innerHTML = `
            <div style="text-align: center; color: var(--text-muted); padding: 40px 0;">
                No structured open positions found.
            </div>
        `;
    } else {
        listContainer.innerHTML = jobsList.map(job => {
            const title = job.title || 'Unknown Position';
            const dept = job.department || 'General';
            
            // Check if title contains Hebrew characters to change direction
            const hasHebrew = /[\u0590-\u05FF]/.test(title);
            const dirClass = hasHebrew ? "" : "ltr";
            
            return `
                <div class="job-item ${dirClass}">
                    <h4>${title}</h4>
                    <div class="job-meta">
                        <span>🏷️ Department: ${dept}</span>
                        <span>📍 Location: Petah Tikva (BSR)</span>
                    </div>
                </div>
            `;
        }).join("");
    }
    
    document.getElementById("jobModal").classList.remove("hidden");
}

function closeJobModal() {
    document.getElementById("jobModal").classList.add("hidden");
}

// -----------------
// 7. System Helpers
// -----------------
function appendSystemLog(message) {
    const consoleLogs = document.getElementById("consoleLogs");
    const timestamp = new Date().toLocaleTimeString();
    
    const div = document.createElement("div");
    div.className = "log-entry system";
    if (message.includes("[SUCCESS]")) div.className = "log-entry success";
    if (message.includes("[ERROR]")) div.className = "log-entry error";
    
    div.innerText = `[${timestamp}] ${message}`;
    consoleLogs.appendChild(div);
    consoleLogs.scrollTop = consoleLogs.scrollHeight;
}

function clearLocalLogs() {
    document.getElementById("consoleLogs").innerHTML = `
        <div class="log-entry system">[SYSTEM] Terminal logs cleared. Active connection polling remains active.</div>
    `;
    knownLogsCount = 0;
}
