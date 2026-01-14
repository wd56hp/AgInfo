-- Views for crop data analysis
-- Provides convenient queries for common crop data analysis scenarios

-- View: crop_summary_by_region_year
-- Summary of all crops by region and year, sorted by acres
CREATE OR REPLACE VIEW crop_summary_by_region_year AS
SELECT 
    r.region_id,
    r.region_type,
    r.name AS region_name,
    r.state,
    r.county,
    ca.year,
    ct.cdl_code,
    ct.name AS crop_name,
    ct.category AS crop_category,
    ca.acres,
    ca.pixel_count,
    ca.data_source,
    ca.processing_date
FROM crop_acres ca
JOIN region r ON ca.region_id = r.region_id
JOIN crop_type ct ON ca.crop_type_id = ct.crop_type_id
ORDER BY r.name, ca.year DESC, ca.acres DESC;

-- Grant permissions
GRANT SELECT ON crop_summary_by_region_year TO agadmin;

-- Add comment
COMMENT ON VIEW crop_summary_by_region_year IS 'Complete crop data summary by region and year with crop details';

-- View: crop_totals_by_region
-- Total acres by crop for each region (aggregated across all years)
CREATE OR REPLACE VIEW crop_totals_by_region AS
SELECT 
    r.region_id,
    r.region_type,
    r.name AS region_name,
    r.state,
    r.county,
    ct.cdl_code,
    ct.name AS crop_name,
    ct.category AS crop_category,
    SUM(ca.acres) AS total_acres,
    COUNT(DISTINCT ca.year) AS years_count,
    MIN(ca.year) AS first_year,
    MAX(ca.year) AS last_year
FROM crop_acres ca
JOIN region r ON ca.region_id = r.region_id
JOIN crop_type ct ON ca.crop_type_id = ct.crop_type_id
GROUP BY r.region_id, r.region_type, r.name, r.state, r.county, ct.cdl_code, ct.name, ct.category
ORDER BY r.name, total_acres DESC;

-- Grant permissions
GRANT SELECT ON crop_totals_by_region TO agadmin;

-- Add comment
COMMENT ON VIEW crop_totals_by_region IS 'Total crop acres by region aggregated across all years';

-- View: crop_totals_by_year
-- Total acres by crop for each year (aggregated across all regions)
CREATE OR REPLACE VIEW crop_totals_by_year AS
SELECT 
    ca.year,
    ct.cdl_code,
    ct.name AS crop_name,
    ct.category AS crop_category,
    SUM(ca.acres) AS total_acres,
    COUNT(DISTINCT ca.region_id) AS regions_count
FROM crop_acres ca
JOIN crop_type ct ON ca.crop_type_id = ct.crop_type_id
GROUP BY ca.year, ct.cdl_code, ct.name, ct.category
ORDER BY ca.year DESC, total_acres DESC;

-- Grant permissions
GRANT SELECT ON crop_totals_by_year TO agadmin;

-- Add comment
COMMENT ON VIEW crop_totals_by_year IS 'Total crop acres by year aggregated across all regions';

-- View: top_crops_by_region
-- Top N crops by acres for each region (most recent year)
CREATE OR REPLACE VIEW top_crops_by_region AS
SELECT 
    r.region_id,
    r.name AS region_name,
    r.state,
    r.county,
    ca.year,
    ct.cdl_code,
    ct.name AS crop_name,
    ct.category AS crop_category,
    ca.acres,
    ROW_NUMBER() OVER (PARTITION BY r.region_id ORDER BY ca.year DESC, ca.acres DESC) AS rank
FROM crop_acres ca
JOIN region r ON ca.region_id = r.region_id
JOIN crop_type ct ON ca.crop_type_id = ct.crop_type_id
ORDER BY r.name, ca.year DESC, ca.acres DESC;

-- Grant permissions
GRANT SELECT ON top_crops_by_region TO agadmin;

-- Add comment
COMMENT ON VIEW top_crops_by_region IS 'Ranked crops by acres for each region, ordered by most recent year';

-- View: crop_trends_by_region
-- Year-over-year trends for crops by region
CREATE OR REPLACE VIEW crop_trends_by_region AS
SELECT 
    r.region_id,
    r.name AS region_name,
    r.state,
    r.county,
    ct.cdl_code,
    ct.name AS crop_name,
    ca.year,
    ca.acres,
    LAG(ca.acres) OVER (PARTITION BY r.region_id, ct.crop_type_id ORDER BY ca.year) AS previous_year_acres,
    ca.acres - LAG(ca.acres) OVER (PARTITION BY r.region_id, ct.crop_type_id ORDER BY ca.year) AS change_acres,
    CASE 
        WHEN LAG(ca.acres) OVER (PARTITION BY r.region_id, ct.crop_type_id ORDER BY ca.year) > 0 
        THEN ((ca.acres - LAG(ca.acres) OVER (PARTITION BY r.region_id, ct.crop_type_id ORDER BY ca.year)) / 
              LAG(ca.acres) OVER (PARTITION BY r.region_id, ct.crop_type_id ORDER BY ca.year)) * 100
        ELSE NULL
    END AS change_percent
FROM crop_acres ca
JOIN region r ON ca.region_id = r.region_id
JOIN crop_type ct ON ca.crop_type_id = ct.crop_type_id
ORDER BY r.name, ct.name, ca.year;

-- Grant permissions
GRANT SELECT ON crop_trends_by_region TO agadmin;

-- Add comment
COMMENT ON VIEW crop_trends_by_region IS 'Year-over-year crop acreage trends with change calculations';

-- View: row_crops_by_region_year
-- Filtered view showing only row crops (corn, soybeans, wheat, etc.)
CREATE OR REPLACE VIEW row_crops_by_region_year AS
SELECT 
    r.region_id,
    r.name AS region_name,
    r.state,
    r.county,
    ca.year,
    ct.cdl_code,
    ct.name AS crop_name,
    ca.acres
FROM crop_acres ca
JOIN region r ON ca.region_id = r.region_id
JOIN crop_type ct ON ca.crop_type_id = ct.crop_type_id
WHERE ct.is_row_crop = TRUE
ORDER BY r.name, ca.year DESC, ca.acres DESC;

-- Grant permissions
GRANT SELECT ON row_crops_by_region_year TO agadmin;

-- Add comment
COMMENT ON VIEW row_crops_by_region_year IS 'Row crops only (corn, soybeans, wheat, etc.) by region and year';

