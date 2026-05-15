# Bid Page Discovery Script

This script discovers pages on company/facility websites that contain cash and new crop bid information for corn, milo (sorghum), and wheat.

## Overview

The `discover_bid_pages.py` script:
1. Reads URLs from the `scrape_url` table
2. Visits each website and explores pages
3. Searches for bid-related keywords (cash bid, new crop, prices, etc.)
4. Scores pages based on relevance to grain bids
5. Stores discovered page paths back to the `scrape_url` table

## Usage

### Basic Usage (Dry Run)

Preview what will be discovered without making changes:

```bash
./db/tools/run_discover_bid_pages.sh
```

### Apply Changes

Actually update the database with discovered pages:

```bash
./db/tools/run_discover_bid_pages.sh --apply
```

### Options

- `--apply`: Actually update database (default is dry run)
- `--limit N`: Process only first N URLs (useful for testing)
- `--company-id ID`: Only process URLs for specific company
- `--facility-id ID`: Only process URLs for specific facility
- `--max-pages N`: Maximum pages to explore per website (default: 50)

### Examples

```bash
# Test with first 5 URLs
./db/tools/run_discover_bid_pages.sh --limit 5

# Process all URLs and update database
./db/tools/run_discover_bid_pages.sh --apply

# Process only URLs for a specific company
./db/tools/run_discover_bid_pages.sh --apply --company-id 123

# Explore more pages per site
./db/tools/run_discover_bid_pages.sh --apply --max-pages 100
```

## How It Works

### Keyword Detection

The script searches for:
- **Bid keywords**: cash bid, cash price, grain bid, new crop, bid sheet, daily bid, etc.
- **Crop keywords**: corn, milo, sorghum, wheat, grain
- **Price patterns**: $5.50, 5.50/bu, per bushel, etc.

### Scoring System

Pages are scored based on:
- Bid keywords found (10 points each)
- Crop keywords found (5 points each)
- Presence of price patterns (10 points)
- Presence of tables (5 points - bids often in tables)
- Specific high-value keywords (cash bid, new crop, etc.)

Pages with score >= 15 are considered relevant and stored.

### Page Discovery

For each website:
1. Starts with the homepage
2. Follows links on the same domain
3. Checks each page for bid-related content
4. Respects robots.txt
5. Limits exploration to avoid excessive crawling

## Output

The script will:
- Display progress for each URL being processed
- Show discovered pages with their scores
- List bid and crop keywords found
- Update `scrape_url.bid_page_path` with the best matching page
- Add notes about what was discovered

## Database Updates

When `--apply` is used, the script updates:
- `bid_page_path`: The path to the discovered bid page
- `notes`: Information about the discovery (score, keywords found)
- `updated_at`: Timestamp of the update

## Notes

- The script respects robots.txt and includes rate limiting (1 second between requests)
- It only explores pages on the same domain as the master_website
- Skips common non-content file types (PDFs, images, etc.)
- If a URL already has a `bid_page_path`, it will be skipped

## Next Steps

After discovering bid pages, you can:
1. Review the discovered pages in the database
2. Manually adjust `bid_page_path` values if needed
3. Create a scraping script to extract actual bid data from these pages
