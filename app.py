"""
AKS Price Checker — уеб версия
FastAPI бакенд с паралелни async заявки към партньорските сайтове.

Стартиране (локално):
    pip install -r requirements.txt
    uvicorn app:app --host 0.0.0.0 --port 8090

Или с Docker:
    docker build -t aks-price-checker .
    docker run -d -p 8090:8090 --name price-checker aks-price-checker
"""

import asyncio
import time
from urllib.parse import urljoin, quote_plus

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# ---------------------------------------------------------------------------
# Конфигурация на сайтовете (пренесена 1:1 от Tkinter версията)
# ---------------------------------------------------------------------------

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
RETRIES = 2          # брой повторни опита след първия неуспешен
RETRY_DELAY = 1.5    # секунди между опитите
CACHE_TTL = 600      # 10 минути кеш — колеги, търсещи същото, получават мигновен отговор

# ---------------------------------------------------------------------------
# Прост in-memory кеш { (category, query): (timestamp, data) }
# ---------------------------------------------------------------------------

_cache: dict[tuple[str, str], tuple[float, dict]] = {}


def cache_get(key: tuple[str, str]):
    entry = _cache.get(key)
    if entry and time.time() - entry[0] < CACHE_TTL:
        return entry[1]
    _cache.pop(key, None)
    return None


def cache_set(key: tuple[str, str], data: dict):
    _cache[key] = (time.time(), data)
    # лека защита срещу неограничен растеж
    if len(_cache) > 200:
        oldest = min(_cache, key=lambda k: _cache[k][0])
        _cache.pop(oldest, None)


# ---------------------------------------------------------------------------
# Скрейпинг
# ---------------------------------------------------------------------------

def parse_site(html: str, site: dict, search_terms: list[str]) -> list[dict]:
    """Твоята логика от Tkinter версията: селектор + проверка, че всички
    думи от заявката присъстват в title/текста на линка."""
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen = set()
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
        items.append({"title": link_text or title, "url": full_url})
    return items


async def fetch_with_retry(client: httpx.AsyncClient, url: str) -> httpx.Response | None:
    for attempt in range(RETRIES + 1):
        try:
            resp = await client.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp
        except httpx.HTTPError:
            if attempt < RETRIES:
                await asyncio.sleep(RETRY_DELAY)
    return None


async def search_site(client: httpx.AsyncClient, site: dict, query: str,
                      search_terms: list[str]) -> dict:
    started = time.perf_counter()
    search_url = site["url"] + quote_plus(query)
    if "extra" in site:
        search_url += site["extra"]

    resp = await fetch_with_retry(client, search_url)
    elapsed = round(time.perf_counter() - started, 2)

    if resp is None:
        return {"site": site["name"], "ok": False, "items": [],
                "error": "Няма отговор от сайта", "seconds": elapsed}

    try:
        # BeautifulSoup е синхронен → в thread pool, за да не блокира event loop-а
        items = await asyncio.to_thread(parse_site, resp.text, site, search_terms)
    except Exception as e:  # повреден HTML не бива да събаря цялото търсене
        return {"site": site["name"], "ok": False, "items": [],
                "error": f"Грешка при парсване: {e}", "seconds": elapsed}

    elapsed = round(time.perf_counter() - started, 2)
    return {"site": site["name"], "ok": True, "items": items,
            "error": None, "seconds": elapsed}


async def search_all(category: str, query: str) -> dict:
    sites = CATEGORIES[category]
    search_terms = query.lower().split()
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        tasks = [search_site(client, s, query, search_terms) for s in sites]
        results = await asyncio.gather(*tasks)
    return {"query": query, "category": category, "results": results}


# ---------------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------------

app = FastAPI(title="AKS Price Checker")


@app.get("/api/search")
async def api_search(
    q: str = Query(..., min_length=2, description="Модел / продукт за търсене"),
    category: str = Query("phone", pattern="^(phone|pc)$"),
):
    q = q.strip()
    key = (category, q.lower())

    cached = cache_get(key)
    if cached:
        return {**cached, "cached": True}

    started = time.perf_counter()
    data = await search_all(category, q)
    data["total_seconds"] = round(time.perf_counter() - started, 2)
    data["cached"] = False

    cache_set(key, data)
    return data


@app.get("/")
async def index():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")
