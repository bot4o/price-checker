import asyncio
import re
import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "bg,en-US;q=0.7,en;q=0.3",
}

# Увеличаваме таймаута за свързване на 10.0s и общия на 15.0s
TIMEOUT_CONFIG = httpx.Timeout(15.0, connect=10.0)

async def debug_masterclub(query="iphone"):
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=TIMEOUT_CONFIG) as client:
        print("=" * 60)
        print("STEP 1: FETCHING HOMEPAGE")
        print("=" * 60)
        
        try:
            home_resp = await client.get("https://masterclub.info/")
            print(f"[*] Homepage Status: {home_resp.status_code}")
            print(f"[*] Session Cookies Received: {dict(client.cookies)}")
        except httpx.ConnectTimeout:
            print("[!] ConnectTimeout: Сървърът masterclub.info не отговори навреме при опит за връзка.")
            return
        except httpx.RequestError as e:
            print(f"[!] Network Error: {type(e).__name__} -> {e}")
            return
        
        # 1. Търсене на скрити security_hash полета в HTML
        soup_home = BeautifulSoup(home_resp.text, "html.parser")
        inputs = soup_home.find_all("input", {"type": "hidden"})
        print("\n[*] Hidden Input Fields found on Homepage:")
        for inp in inputs:
            name = inp.get("name")
            val = inp.get("value")
            if name and any(k in str(name).lower() for k in ["security", "hash", "dispatch"]):
                print(f"    -> {name} = {val}")
                
        # 2. Проверка за JavaScript променливи
        js_hashes = re.findall(r'security_hash[^\w]*([a-f0-9]{32})', home_resp.text, re.I)
        print(f"[*] JS Security Hashes found: {js_hashes}")
        
        sec_hash = js_hashes[0] if js_hashes else ""

        print("\n" + "=" * 60)
        print(f"STEP 2: EXECUTING SEARCH FOR '{query}'")
        print("=" * 60)
        
        search_url = (
            f"https://masterclub.info/?match=all&subcats=Y&pcode_from_q=Y"
            f"&pshort=Y&pfull=Y&pname=Y&pkeywords=Y&search_performed=Y"
            f"&q={query}&dispatch=products.search"
        )
        if sec_hash:
            search_url += f"&security_hash={sec_hash}"

        print(f"[*] Target Search URL:\n    {search_url}\n")
        
        try:
            search_resp = await client.get(search_url)
            print(f"[*] Search Response Status: {search_resp.status_code}")
            print(f"[*] Final URL (after redirects): {search_resp.url}")
        except httpx.RequestError as e:
            print(f"[!] Search Request Error: {e}")
            return
        
        soup_search = BeautifulSoup(search_resp.text, "html.parser")
        page_title = soup_search.title.string.strip() if soup_search.title else "No Title"
        print(f"[*] Response Page Title: '{page_title}'")
        
        # 3. Тест на CSS селектори
        print("\n[*] Testing Candidate CSS Selectors for Product Links:")
        candidate_selectors = [
            "a.product-title",
            ".ty-grid-list__item-name a",
            ".ty-compact-list__title a",
            ".ty-column4 a",
            "a[href*='dispatch=products.view']",
            "a[href*='.html']"
        ]
        
        for sel in candidate_selectors:
            matches = soup_search.select(sel)
            valid_links = [m.get_text(strip=True) for m in matches if query.lower() in m.get_text().lower()]
            print(f"    -> Selector '{sel}': {len(matches)} total matches | {len(valid_links)} matching '{query}'")
            if valid_links:
                print(f"       Sample match: \"{valid_links[0]}\"")

if __name__ == "__main__":
    asyncio.run(debug_masterclub("iphone"))
