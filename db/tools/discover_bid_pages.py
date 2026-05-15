#!/usr/bin/env python3
"""
Discover bid pages on company/facility websites.

This script visits websites from the scrape_url table and searches for pages
containing cash and new crop bids for corn, milo (sorghum), and wheat.

It will:
1. Read URLs from scrape_url table
2. Visit each master_website
3. Search for bid-related pages (cash bids, new crop, prices)
4. Store discovered bid_page_path values back to scrape_url table

Usage:
    python discover_bid_pages.py [--apply] [--limit N] [--company-id ID] [--facility-id ID]
"""

import os
import sys
import re
import time
import argparse
from typing import Dict, Any, Optional, List, Set
from urllib.parse import urljoin, urlparse, urlunparse
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
from urllib.robotparser import RobotFileParser

# Load .env
env_loaded = load_dotenv()
if not env_loaded and os.path.exists("/project/.env"):
    load_dotenv("/project/.env")


def db_connect():
    """Connect to database using .env variables."""
    host = os.environ.get("PGHOST", "localhost")
    port = os.environ.get("POSTGIS_HOST_PORT")
    if not port:
        raise SystemExit("ERROR: POSTGIS_HOST_PORT is not set in .env")

    for k in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"):
        if not os.environ.get(k):
            raise SystemExit(f"ERROR: {k} is not set in .env")

    return psycopg2.connect(
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=host,
        port=port,
    )


# Keywords to search for bid-related content
BID_KEYWORDS = [
    'cash bid', 'cash price', 'cash grain', 'grain bid', 'grain price',
    'new crop', 'new crop bid', 'new crop price',
    'corn bid', 'corn price', 'corn cash',
    'milo bid', 'milo price', 'milo cash', 'sorghum bid', 'sorghum price',
    'wheat bid', 'wheat price', 'wheat cash',
    'grain prices', 'commodity prices', 'bid sheet', 'price sheet',
    'daily bid', 'daily price', 'market price'
]

CROP_KEYWORDS = ['corn', 'milo', 'sorghum', 'wheat', 'grain']


def normalize_url(url: str) -> str:
    """Normalize URL - ensure it has a protocol."""
    url = url.strip()
    if not url:
        return url
    
    # Fix common malformed URLs
    # Fix "http:/" or "https:/" (missing slash)
    url = re.sub(r'^https?:/(?!/)', r'https://', url)
    
    # If it already has a protocol, return as-is
    if url.startswith('http://') or url.startswith('https://'):
        return url
    
    # Add https:// if missing
    if url.startswith('www.'):
        return 'https://' + url
    
    return 'https://' + url


def check_robots_txt(base_url: str, path: str = '/') -> bool:
    """Check if we're allowed to crawl this path according to robots.txt."""
    try:
        parsed = urlparse(base_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        
        return rp.can_fetch('*', urljoin(base_url, path))
    except Exception:
        # If robots.txt check fails, assume we can crawl (be respectful though)
        return True


def get_page_content(url: str, timeout: int = 10) -> Optional[BeautifulSoup]:
    """Fetch and parse a webpage."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        
        # Check content type
        content_type = response.headers.get('content-type', '').lower()
        if 'text/html' not in content_type:
            return None
        
        return BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"    ⚠ Error fetching {url}: {e}", flush=True)
        return None


def find_bid_keywords_in_text(text: str) -> Set[str]:
    """Find bid-related keywords in text."""
    text_lower = text.lower()
    found = set()
    
    for keyword in BID_KEYWORDS:
        if keyword.lower() in text_lower:
            found.add(keyword)
    
    return found


def find_crop_keywords_in_text(text: str) -> Set[str]:
    """Find crop-related keywords in text."""
    text_lower = text.lower()
    found = set()
    
    for keyword in CROP_KEYWORDS:
        if keyword.lower() in text_lower:
            found.add(keyword)
    
    return found


def score_page_for_bids(soup: BeautifulSoup, url: str) -> tuple[int, Set[str], Set[str]]:
    """Score a page for likelihood of containing bid information.
    
    Returns: (score, bid_keywords_found, crop_keywords_found)
    """
    if not soup:
        return (0, set(), set())
    
    # Get all text content
    text = soup.get_text(separator=' ', strip=True)
    
    # Find keywords
    bid_keywords = find_bid_keywords_in_text(text)
    crop_keywords = find_crop_keywords_in_text(text)
    
    # Calculate score
    score = 0
    score += len(bid_keywords) * 10  # Each bid keyword is worth 10 points
    score += len(crop_keywords) * 5   # Each crop keyword is worth 5 points
    
    # Bonus for specific high-value keywords
    text_lower = text.lower()
    if 'cash bid' in text_lower or 'cash price' in text_lower:
        score += 20
    if 'new crop' in text_lower:
        score += 15
    if any(crop in text_lower for crop in ['corn', 'milo', 'sorghum', 'wheat']):
        score += 10
    
    # Look for tables (bids are often in tables)
    tables = soup.find_all('table')
    if tables:
        score += 5
    
    # Look for price-like patterns (numbers with $ or /bu, /cwt, etc.)
    price_patterns = [
        r'\$\d+\.?\d*',  # $5.50
        r'\d+\.?\d*\s*/\s*(bu|bushel|cwt|ton)',  # 5.50/bu
        r'\d+\.?\d*\s*per\s*(bushel|bu|cwt|ton)',
    ]
    for pattern in price_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            score += 10
            break
    
    return (score, bid_keywords, crop_keywords)


def discover_pages_on_site(base_url: str, max_pages: int = 50) -> List[Dict[str, Any]]:
    """Discover pages on a website that might contain bid information.
    
    Returns list of dicts with: {url, path, score, bid_keywords, crop_keywords}
    """
    base_url = normalize_url(base_url)
    parsed = urlparse(base_url)
    base_domain = f"{parsed.scheme}://{parsed.netloc}"
    
    discovered = []
    visited = set()
    to_visit = [base_url]  # Start with homepage
    
    print(f"    Exploring {base_domain}...", flush=True)
    
    # Check robots.txt
    if not check_robots_txt(base_url):
        print(f"    ⚠ robots.txt disallows crawling {base_url}", flush=True)
        return discovered
    
    page_count = 0
    
    while to_visit and page_count < max_pages:
        current_url = to_visit.pop(0)
        
        if current_url in visited:
            continue
        
        visited.add(current_url)
        page_count += 1
        
        # Rate limiting
        time.sleep(1)
        
        print(f"    [{page_count}/{max_pages}] Checking: {current_url}", flush=True)
        
        soup = get_page_content(current_url)
        if not soup:
            continue
        
        # Score this page
        score, bid_keywords, crop_keywords = score_page_for_bids(soup, current_url)
        
        # If score is high enough, record it
        if score >= 15:  # Threshold for considering a page relevant
            path = urlparse(current_url).path
            if not path:
                path = '/'
            
            discovered.append({
                'url': current_url,
                'path': path,
                'score': score,
                'bid_keywords': bid_keywords,
                'crop_keywords': crop_keywords
            })
            
            print(f"      ✓ Found bid page (score: {score}): {path}", flush=True)
            print(f"        Bid keywords: {', '.join(bid_keywords) if bid_keywords else 'none'}", flush=True)
            print(f"        Crop keywords: {', '.join(crop_keywords) if crop_keywords else 'none'}", flush=True)
        
        # Find links to explore (only if we haven't found many pages yet)
        if len(discovered) < 10:
            links = soup.find_all('a', href=True)
            for link in links[:20]:  # Limit links per page
                href = link.get('href', '')
                if not href:
                    continue
                
                # Convert relative URLs to absolute
                absolute_url = urljoin(current_url, href)
                parsed_link = urlparse(absolute_url)
                
                # Only follow links on the same domain
                if parsed_link.netloc == parsed.netloc:
                    # Skip common non-content URLs
                    skip_patterns = [
                        r'\.(pdf|doc|docx|xls|xlsx|zip|jpg|jpeg|png|gif|css|js)$',
                        r'#',  # Anchors
                        r'mailto:', r'tel:', r'javascript:',
                    ]
                    
                    should_skip = False
                    for pattern in skip_patterns:
                        if re.search(pattern, absolute_url, re.IGNORECASE):
                            should_skip = True
                            break
                    
                    if not should_skip and absolute_url not in visited:
                        to_visit.append(absolute_url)
    
    return discovered


def update_scrape_url(conn, scrape_url_id: int, bid_page_path: str, notes: str, apply: bool):
    """Update scrape_url with discovered bid page path."""
    if not apply:
        print(f"    [DRY RUN] Would update scrape_url_id={scrape_url_id} with bid_page_path={bid_page_path}", flush=True)
        return
    
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE scrape_url
            SET bid_page_path = %s,
                notes = COALESCE(notes || '; ', '') || %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE scrape_url_id = %s
            """,
            (bid_page_path, notes, scrape_url_id)
        )
        conn.commit()
        print(f"    ✓ Updated scrape_url_id={scrape_url_id} with bid_page_path={bid_page_path}", flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="Discover bid pages on company/facility websites"
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Actually update database (default is dry run)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=0,
        help='Limit number of URLs to process (0 = all)'
    )
    parser.add_argument(
        '--company-id',
        type=int,
        help='Only process URLs for specific company_id'
    )
    parser.add_argument(
        '--facility-id',
        type=int,
        help='Only process URLs for specific facility_id'
    )
    parser.add_argument(
        '--max-pages',
        type=int,
        default=50,
        help='Maximum pages to explore per website (default: 50)'
    )
    
    args = parser.parse_args()
    
    if not args.apply:
        print("=" * 60)
        print("DRY RUN MODE - No changes will be made to database")
        print("=" * 60)
        print()
    
    # Connect to database
    print("Connecting to database...", flush=True)
    conn = db_connect()
    print("✓ Connected", flush=True)
    
    try:
        # Get URLs to process
        with conn.cursor() as cur:
            query = """
                SELECT scrape_url_id, company_id, facility_id, master_website, bid_page_path, status
                FROM scrape_url
                WHERE status = 'ACTIVE'
            """
            params = []
            
            if args.company_id:
                query += " AND company_id = %s"
                params.append(args.company_id)
            
            if args.facility_id:
                query += " AND facility_id = %s"
                params.append(args.facility_id)
            
            query += " ORDER BY scrape_url_id"
            
            if args.limit > 0:
                query += f" LIMIT {args.limit}"
            
            cur.execute(query, params)
            urls = cur.fetchall()
        
        print(f"\nFound {len(urls)} URLs to process", flush=True)
        
        if len(urls) == 0:
            print("No URLs to process")
            return
        
        # Process each URL
        processed = 0
        discovered_count = 0
        
        for row in urls:
            scrape_url_id, company_id, facility_id, master_website, existing_path, status = row
            
            processed += 1
            print(f"\n[{processed}/{len(urls)}] Processing scrape_url_id={scrape_url_id}", flush=True)
            print(f"  Website: {master_website}", flush=True)
            
            if existing_path:
                print(f"  ⚠ Already has bid_page_path: {existing_path} (skipping)", flush=True)
                continue
            
            # Discover pages
            discovered = discover_pages_on_site(master_website, max_pages=args.max_pages)
            
            if discovered:
                # Sort by score (highest first)
                discovered.sort(key=lambda x: x['score'], reverse=True)
                
                # Use the highest scoring page
                best = discovered[0]
                bid_page_path = best['path']
                
                # Build notes
                notes_parts = [
                    f"Discovered bid page (score: {best['score']})",
                    f"Bid keywords: {', '.join(best['bid_keywords']) if best['bid_keywords'] else 'none'}",
                    f"Crop keywords: {', '.join(best['crop_keywords']) if best['crop_keywords'] else 'none'}"
                ]
                notes = '; '.join(notes_parts)
                
                # Update database
                update_scrape_url(conn, scrape_url_id, bid_page_path, notes, args.apply)
                discovered_count += 1
                
                # If multiple good pages found, mention them
                if len(discovered) > 1:
                    print(f"  ℹ️  Found {len(discovered)} potential bid pages (using highest score)", flush=True)
            else:
                print(f"  ⊙ No bid pages discovered", flush=True)
        
        # Summary
        print("\n" + "=" * 60)
        print("DISCOVERY SUMMARY")
        print("=" * 60)
        print(f"URLs processed: {processed}")
        print(f"Bid pages discovered: {discovered_count}")
        
        if not args.apply:
            print("\nThis was a DRY RUN. Use --apply to actually update the database.")
        
    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
