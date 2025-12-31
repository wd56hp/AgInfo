-- Kansas Grain and Feed Association (KGFA) Member Directory schema
-- Stores member directory data from KGFA website
-- Data sourced from KGFA member directory scraping

CREATE TABLE IF NOT EXISTS ksgfa_detail (
    ksgfa_detail_id    SERIAL PRIMARY KEY,
    
    -- Company information
    company            VARCHAR(200) NOT NULL,
    contact            VARCHAR(200),  -- Contact person name (may be empty)
    
    -- Contact information
    phone              VARCHAR(50),   -- Phone number (may be empty)
    website            VARCHAR(300),  -- Website URL (may be empty)
    
    -- Address information
    street             VARCHAR(200),  -- Street address (may be empty or contain placeholder)
    city               VARCHAR(100),  -- City (may be empty)
    state              CHAR(2) DEFAULT 'KS',  -- State code (may be empty, defaults to KS)
    zip                VARCHAR(20),   -- ZIP/postal code (may be empty)
    
    -- Additional data
    notes              TEXT,          -- Notes field (may contain HTML content)
    detail_url         VARCHAR(500) NOT NULL UNIQUE,  -- URL to detail page on KGFA website
    
    -- Metadata
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index on company name for faster lookups
CREATE INDEX IF NOT EXISTS idx_ksgfa_detail_company ON ksgfa_detail(company);

-- Create index on city and state for location-based queries
CREATE INDEX IF NOT EXISTS idx_ksgfa_detail_location ON ksgfa_detail(city, state);

-- Create index on detail_url for uniqueness enforcement and lookups
CREATE INDEX IF NOT EXISTS idx_ksgfa_detail_detail_url ON ksgfa_detail(detail_url);

-- Create index on zip for location-based queries
CREATE INDEX IF NOT EXISTS idx_ksgfa_detail_zip ON ksgfa_detail(zip);

-- Comment on table
COMMENT ON TABLE ksgfa_detail IS 'Kansas Grain and Feed Association (KGFA) member directory data';
COMMENT ON COLUMN ksgfa_detail.company IS 'Company/organization name';
COMMENT ON COLUMN ksgfa_detail.contact IS 'Contact person name (may be empty)';
COMMENT ON COLUMN ksgfa_detail.phone IS 'Phone number (may be empty)';
COMMENT ON COLUMN ksgfa_detail.street IS 'Street address (may be empty or contain placeholder value)';
COMMENT ON COLUMN ksgfa_detail.detail_url IS 'URL to the detail page on KGFA website (unique)';
COMMENT ON COLUMN ksgfa_detail.notes IS 'Additional notes, may contain HTML content from source';
