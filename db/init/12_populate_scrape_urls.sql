-- Populate scrape_url table with existing URLs from company and facility tables
-- This script extracts unique website URLs and creates scrape_url entries

-- First, clear any existing scrape_url entries (optional - comment out if you want to keep existing)
-- TRUNCATE TABLE scrape_url;

-- Insert URLs from company table
INSERT INTO scrape_url (company_id, master_website, bid_page_path, status, notes, created_at, updated_at)
SELECT 
    company_id,
    website_url AS master_website,
    NULL AS bid_page_path,  -- Bid page path will be filled in later for scraping
    'ACTIVE' AS status,
    'Imported from company.website_url' AS notes,
    CURRENT_TIMESTAMP AS created_at,
    CURRENT_TIMESTAMP AS updated_at
FROM company
WHERE website_url IS NOT NULL 
  AND website_url != ''
  AND website_url NOT LIKE 'http://%'  -- Only process if it's a full URL
  AND website_url NOT LIKE 'https://%'
  AND website_url NOT LIKE 'www.%'
  AND TRIM(website_url) != ''
ON CONFLICT DO NOTHING;

-- Also handle URLs that already have http:// or https://
INSERT INTO scrape_url (company_id, master_website, bid_page_path, status, notes, created_at, updated_at)
SELECT 
    company_id,
    CASE 
        WHEN website_url LIKE 'http://%' OR website_url LIKE 'https://%' THEN
            -- Extract base URL (remove path if present)
            regexp_replace(website_url, '^https?://([^/]+).*$', 'https://\1', 'i')
        WHEN website_url LIKE 'www.%' THEN
            'https://' || website_url
        ELSE
            'https://' || website_url
    END AS master_website,
    CASE 
        WHEN website_url LIKE '%/%' AND (website_url LIKE 'http://%' OR website_url LIKE 'https://%') THEN
            -- Extract path portion
            regexp_replace(website_url, '^https?://[^/]+(.*)$', '\1', 'i')
        ELSE
            NULL
    END AS bid_page_path,
    'ACTIVE' AS status,
    'Imported from company.website_url' AS notes,
    CURRENT_TIMESTAMP AS created_at,
    CURRENT_TIMESTAMP AS updated_at
FROM company
WHERE website_url IS NOT NULL 
  AND website_url != ''
  AND TRIM(website_url) != ''
  AND NOT EXISTS (
      -- Avoid duplicates - check if this company_id + website_url combo already exists
      SELECT 1 FROM scrape_url 
      WHERE scrape_url.company_id = company.company_id 
        AND scrape_url.master_website = CASE 
            WHEN company.website_url LIKE 'http://%' OR company.website_url LIKE 'https://%' THEN
                regexp_replace(company.website_url, '^https?://([^/]+).*$', 'https://\1', 'i')
            WHEN company.website_url LIKE 'www.%' THEN
                'https://' || company.website_url
            ELSE
                'https://' || company.website_url
        END
  );

-- Insert URLs from facility table
INSERT INTO scrape_url (facility_id, master_website, bid_page_path, status, notes, created_at, updated_at)
SELECT 
    facility_id,
    CASE 
        WHEN website_url LIKE 'http://%' OR website_url LIKE 'https://%' THEN
            -- Extract base URL (remove path if present)
            regexp_replace(website_url, '^https?://([^/]+).*$', 'https://\1', 'i')
        WHEN website_url LIKE 'www.%' THEN
            'https://' || website_url
        ELSE
            'https://' || website_url
    END AS master_website,
    CASE 
        WHEN website_url LIKE '%/%' AND (website_url LIKE 'http://%' OR website_url LIKE 'https://%') THEN
            -- Extract path portion
            regexp_replace(website_url, '^https?://[^/]+(.*)$', '\1', 'i')
        ELSE
            NULL
    END AS bid_page_path,
    'ACTIVE' AS status,
    'Imported from facility.website_url' AS notes,
    CURRENT_TIMESTAMP AS created_at,
    CURRENT_TIMESTAMP AS updated_at
FROM facility
WHERE website_url IS NOT NULL 
  AND website_url != ''
  AND TRIM(website_url) != ''
  AND NOT EXISTS (
      -- Avoid duplicates - check if this facility_id + website_url combo already exists
      SELECT 1 FROM scrape_url 
      WHERE scrape_url.facility_id = facility.facility_id 
        AND scrape_url.master_website = CASE 
            WHEN facility.website_url LIKE 'http://%' OR facility.website_url LIKE 'https://%' THEN
                regexp_replace(facility.website_url, '^https?://([^/]+).*$', 'https://\1', 'i')
            WHEN facility.website_url LIKE 'www.%' THEN
                'https://' || facility.website_url
            ELSE
                'https://' || facility.website_url
        END
  );

-- Summary query to show what was inserted
SELECT 
    'Company URLs' AS source,
    COUNT(*) AS count
FROM scrape_url
WHERE company_id IS NOT NULL
UNION ALL
SELECT 
    'Facility URLs' AS source,
    COUNT(*) AS count
FROM scrape_url
WHERE facility_id IS NOT NULL
UNION ALL
SELECT 
    'Total URLs' AS source,
    COUNT(*) AS count
FROM scrape_url;
