import asyncio
import sys
import time
from urllib.parse import urljoin, quote_plus

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

# Logging
logger.remove() 
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss.SS}</green> | <level>{level: <7}</level> | <cyan>{extra[component]: <8}</cyan>  | <level>{message}</level>",
    colorize=True
)

# File output logs/scraper.log
logger.add(
    "logs/scraper.log",
    rotation="10MB",
    retention="7 days",
    format="{time:YYYY-MM-DD HH:mm:ss.SS} | {level: <7} | {extra[component]: <8} | {message}", 
    level="INFO",
    enqueue=True
)

logger = logger.bind(components="SYSTEM")

# Sites confiuration (1:1 from thinker version)
PC_SITES = [
    {
        "name": "LaptopRemont",
        "url": "https://www.laptopremont.com/advanced_search_result.php?keywords=",
        "selector": "a[href^='https://www.laptopremont.com/']",
    },
    {
        "name": "OLX",
        "url": "https://www.olx.bg/ads/q-",
        "selector": "a.css-z3gu2d",
    },
    {
        "name": "Bazar",
        "url": "https://bazar.bg/obiavi?q=",
        "selector": "a[data-id]",
    },
]

PHONE_SITES = [
    {
        "name": "Cellphone BG",
        "url": "https://cellphone-bg.com/search?search=",
        "selector": "a.prod-info",
    },
    {
        "name": "Alpha Mobile",
        "url": "https://www.alphamobile.eu/index.php?route=product/search&search=",
        "selector": "a.prod-info",
    },
    {
        "name": "GagoGSM",
        "url": "https://gagogsm.com/index.php?route=product/search&search=",
        "selector": "a.prod-info",
    },
    {
        "name": "Smenime",
        "url": "https://smenime.com/%D1%82%D1%8A%D1%80%D1%81%D0%B5%D0%BD%D0%B5?searchword=",
        "selector": "a[title]",
    },
    {
        "name": "PhoneZona",
        "url": "https://phonezona.com/index.php?route=product/search&search=",
        "selector": "a.prod-info",
    },
    {
        "name": "MasterClub",
        "url": (
            "https://masterclub.info/?match=all&subcats=Y&pcode_from_q=Y"
            "&pshort=Y&pfull=Y&pname=Y&pkeywords=Y&search_performed=Y&q="
        ),
        "selector": "a.product-title",
        "extra": "&dispatch=products.search&security_hash=f1a874bef7fdd99c17064010466ec1ad",
    },
    {
        "name": "Siaifon",
        "url": "https://siaifon.com/search.html?phrase=",
        "selector": "a.c-product-grid__product-title-link",
    },
]

CATEGORIES = {"phone": PHONE_SITES, "pc": PC_SITES}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "bg,en;q=0.8",
}

REQUEST_TIMEOUT = 12.0
RETRIES = 2          # num repated tries after the first unsucessfull one 
RETRY_DELAY = 1.5    # seconds between tries 
CACHE_TTL = 600      # 10 minutes cache — collegues, searcing for the same, get the imidiate result 

# Simple in-memory cache { (category, query): (timestamp, data) }
_cache: dict[tuple[str, str], tuple[float, dict]] = {}

def cache_get(key: tuple[str, str]):
    entry = _cache.get(key)
    if entry and time.time() - entry[0] < CACHE_TTL:
        return entry[1]
    _cache.pop(key, None)
    return None

def cache_set(key: tuple[str, str], data: dict):
    _cache[key] = (time.time(), data)
    # little security from unbounded growth 
    if len(_cache) > 200:
        oldest = min(_cache, key=lambda k: _cache[k][0])
        _cache.pop(oldest, None)

# Scraping logic
def parse_site(html: str, site: dict, search_terms: list[str]) -> list[dict]:
    start_time = time.perf_counter()
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen = set()
    
    # specific filters for prices in different sites 
    site_price_tags = {
        "Siaifon": [".c-product-grid__product-price", ".price"],
        "Cellphone BG": [".price-new", ".price"],
        "Alpha Mobile": [".price-new", ".price"],
        "GagoGSM": [".price-new", ".price"],
        "PhoneZona": [".price-new", ".price"],
        "MasterClub": [".ty-price-num", ".price"],
        "OLX": ["[data-testid='ad-price']", ".css-19346ff", ".price"],
        "Bazar": ["span.price", ".price"]
    }
    
    for link in soup.select(site["selector"]):
        href = link.get("href")
        if not href:
            continue
            
        title = (link.get("title") or "").lower()
        link_text = link.get_text(strip=True)
        haystack = title + " " + link_text.lower()
        
        if not all(term in haystack for term in search_terms):
            continue
            
        full_url = urljoin(site["url"], href)
        if full_url in seen:
            continue
        seen.add(full_url)
        
        clean_title = " ".join(link_text.split()) or title
        detected_price = ""
        
        # Getting targetet selectors for prices for the approporiate site
        price_tags = site_price_tags.get(site["name"], [".price", ".price-new"])
        
        # Dynamic climbing upon the parents for finding A PRICE
        current_parent = link
        
        # Climbs up 4 levels upon the DOM tree
        for _ in range(4):
            current_parent = current_parent.parent
            if not current_parent or current_parent.name == "[document]":
                break
                
            found_price_text = ""
            for tag in price_tags:
                price_elem = current_parent.select_one(tag)
                if price_elem:
                    # Removing spaces and new rows 
                    raw_text = price_elem.get_text(strip=True)
                    found_price_text = " ".join(raw_text.split())
                    if found_price_text:
                        break
            
            # If valid price is found in this parent, we save it and stops searching 
            if found_price_text:
                detected_price = found_price_text
                break

        # Building title with price
        if detected_price:
            display_title = f"{clean_title} — {detected_price}"
        else:
            display_title = clean_title
            
        items.append({"title": display_title, "url": full_url})
    elapsed_ms = round((time.perf_counter() - start_time) * 1000)

    # Parsing speed and anomaly warnings
    parser_log = logger.bind(component="PARSER")
    if not items:
        parser_log.warning(f"[{site['name']}] 0 items found in {elapsed_ms}ms! (CSS selector '{site['selector']}' broken or empty query)")
    else:
        parser_log.warning(f"[{site['name']}] Exracter {len(items)} items in {elapsed_ms}ms")
        
    return items

async def fetch_with_retry(client: httpx.AsyncClient, url: str, site_name: str) -> httpx.Response | None:
    net_log = logger.bind(components="NETWORK")

    for attempt in range(1, RETRIES + 2):
        try:
            start_time=time.perf_counter()
            resp = await client.get(url, timeout=REQUEST_TIMEOUT)
            elapsed_ms = round((time.perf_counter() - start_time) * 1000)

            resp.raise_for_status()

            # Network speed tracking
            net_log.info(f"[{site_name}] GET -> Status 200 OK ({elapsed_ms}ms)")
            return resp

        except httpx.HTTPError as e:
            status = e.response.status_code
            # Anti-scrapign or server error blocks
            net_log.warning(f"[{site_name}] HTTP {status} on attempt {attempt}/{RETRIES + 1}. Retrying in {RETRY_DELAY}s...")
            if attempt <= RETRIES:
                await asyncio.sleep(RETRY_DELAY)
        except (httpx.RequestError, httpx.TimeoutException) as e:
            net_log.warning(f"[{site_name}] Connection error ({type(e).__name__}] on attempt {attempt}/{RETRIES + 1}. Retrying...")
            if attempt <= RETRIES:
                await asyncio.sleep(RETRY_DELAY)

    net_log.error(f"[{site_name}] FAILED to fetch after {RETRIES + 1} attempts!")
    return None


async def search_site(client: httpx.AsyncClient, site: dict, query: str,
                      search_terms: list[str]) -> dict:
    started = time.perf_counter()
    search_url = site["url"] + quote_plus(query)
    if "extra" in site:
        search_url += site["extra"]

    resp = await fetch_with_retry(client, search_url, site["name"])
    elapsed = round(time.perf_counter() - started, 2)

    if resp is None:
        return {"site": site["name"], "ok": False, "items": [],
                "error": "Няма отговор от сайта", "seconds": elapsed}

    try:
        items = await asyncio.to_thread(parse_site, resp.text, site, search_terms)
    except Exception as e:  
        # Crash catching
        logger.bind(component="PARSER").error(f"[{site['name']}] HTML parsing crashed: {str(e)}")
        return {"site": site["name"], "ok": False, "items": [],
                "error": f"Error in parsing: {e}", "seconds": elapsed}

    elapsed = round(time.perf_counter() - started, 2)
    return {"site": site["name"], "ok": True, "items": items,
            "error": None, "seconds": elapsed}


async def search_all(category: str, query: str) -> dict:
    sites = CATEGORIES[category]
    search_terms = query.lower().split()

    logger.bind(components="SCRAPER").info(f"Launching concurent search across {len(sites)} '{category}' sites for: '{query}'")

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        tasks = [search_site(client, s, query, search_terms) for s in sites]
        results = await asyncio.gather(*tasks)

    return {"query": query, "category": category, "results": results}


# FastAPI 
app = FastAPI(title="AKS Price Checker")

@app.on_event("startup")
async def startup_event():
    logger.bind(component="SYSTEM").success("AKS Price Checker server booted up and ready for requests!")

@app.get("/api/search")
async def api_search(
    q: str = Query(..., min_length=2, description="Модел / продукт за търсене"),
    category: str = Query("phone", pattern="^(phone|pc)$"),
):
    api_log = logger.bind(component="API")
    q = q.strip()
    key = (category, q.lower())

    #Incomming API tracking & Cache hits
    cached = cache_get(key)
    if cached:
        api_log.success(f"CACHE HIT -> Return instant results for '{q}' ({category})")
        return {**cached, "cached": True}

    api_log.info(f"SEARCH REQUEST -> Category: '{category}', Query: '{q}'")
    started = time.perf_counter()

    data = await search_all(category, q)

    total_seconds = round(time.perf_counter() - started, 2)
    data["total_seconds"] = total_seconds
    data["cached"] = False

    total_items = sum(len(r["items"]) for r in data ["results"] if r["ok"])
    api_log.success(f"SEARCH COMPLETED -> Found {total_items} items across all sites in {total_seconds}s")

    cache_set(key, data)
    return data


@app.get("/")
async def index():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")
