-- Import KGFA detail CSV data without duplicates
-- Uses temporary table and INSERT ... ON CONFLICT to handle duplicates

-- Create temporary table with same structure
CREATE TEMP TABLE ksgfa_detail_temp (LIKE ksgfa_detail INCLUDING ALL);

-- Import CSV into temporary table
COPY ksgfa_detail_temp(company, contact, phone, street, city, state, zip, website, notes, detail_url) 
FROM '/tmp/aginfo-import/ksgfa_detail.csv' 
WITH (FORMAT csv, HEADER true, DELIMITER ',', QUOTE '"', ESCAPE '"');

-- Insert from temp table, updating existing records on conflict
INSERT INTO ksgfa_detail(company, contact, phone, website, street, city, state, zip, notes, detail_url)
SELECT company, contact, phone, website, street, city, state, zip, notes, detail_url
FROM ksgfa_detail_temp
ON CONFLICT (detail_url) 
DO UPDATE SET
    company = EXCLUDED.company,
    contact = EXCLUDED.contact,
    phone = EXCLUDED.phone,
    website = EXCLUDED.website,
    street = EXCLUDED.street,
    city = EXCLUDED.city,
    state = EXCLUDED.state,
    zip = EXCLUDED.zip,
    notes = EXCLUDED.notes,
    updated_at = CURRENT_TIMESTAMP;

-- Drop temp table
DROP TABLE ksgfa_detail_temp;
