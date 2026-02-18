import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re

STEAM_URL = "https://store.steampowered.com/search/?filter=topsellers&os=win&cc=us" 

async def test_steam_parsing():
    print(f"Fetching {STEAM_URL}...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Cookie": "birthtime=568022401; lastagecheckage=1-January-1988"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(STEAM_URL, headers=headers) as response:
            print(f"Status: {response.status}")
            html = await response.text()
    
    soup = BeautifulSoup(html, "html.parser")
    items = soup.find_all("a", class_="search_result_row", limit=5)
    
    print(f"Found {len(items)} items.\n")

    for i, item in enumerate(items):
        title = item.find("span", class_="title").get_text(strip=True)
        print(f"[{i+1}] {title}")
        
        # DUMP HTML FOR DEBUGGING
        if i == 0:
            print("--- HTML DUMP OF FIRST ITEM ---")
            print(item.prettify())
            print("--- END HTML DUMP ---")

        # Try multiple selectors
        selectors = [".search_price", ".discount_final_price", ".search_price_discount_combined"]
        
        found_price = False
        for sel in selectors:
            price_div = item.select_one(sel)
            if price_div:
                print(f"    Found with selector '{sel}': '{price_div.get_text(strip=True)}'")
                found_price = True
        
        if not found_price:
            print("    NO PRICE FOUND with any selector")
        
        print("-" * 20)

if __name__ == "__main__":
    if asyncio.get_event_loop_policy().__class__.__name__ == 'WindowsProactorEventLoopPolicy':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_steam_parsing())
