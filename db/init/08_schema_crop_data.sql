-- Federal Crop Data Layer (CDL) schema
-- Stores crop acreage data by region, year, and crop type
-- Data typically sourced from USDA NASS Cropland Data Layer

-- 1. crop_type ---------------------------------------------------------
-- Lookup table for crop types with CDL codes

CREATE TABLE IF NOT EXISTS crop_type (
    crop_type_id       SERIAL PRIMARY KEY,
    cdl_code           INTEGER NOT NULL UNIQUE,  -- CDL crop code (e.g., 1=Corn, 5=Soybeans)
    name               VARCHAR(200) NOT NULL UNIQUE,  -- Crop name (e.g., 'Corn', 'Soybeans')
    category           VARCHAR(50),  -- 'GRAIN', 'OILSEED', 'FORAGE', 'VEGETABLE', 'FRUIT', 'OTHER'
    description        TEXT,
    is_row_crop        BOOLEAN DEFAULT FALSE,  -- True for row crops (corn, soybeans, etc.)
    is_perennial       BOOLEAN DEFAULT FALSE,  -- True for perennial crops (alfalfa, etc.)
    notes              TEXT
);

-- Seed common crop types with CDL codes
-- Based on USDA NASS CDL classification
INSERT INTO crop_type (cdl_code, name, category, is_row_crop, description) VALUES
    (1, 'Corn', 'GRAIN', TRUE, 'Corn'),
    (5, 'Soybeans', 'OILSEED', TRUE, 'Soybeans'),
    (24, 'Winter Wheat', 'GRAIN', TRUE, 'Winter Wheat'),
    (23, 'Spring Wheat', 'GRAIN', TRUE, 'Spring Wheat'),
    (36, 'Alfalfa', 'FORAGE', FALSE, 'Alfalfa'),
    (37, 'Other Hay/Non Alfalfa', 'FORAGE', FALSE, 'Other Hay/Non Alfalfa'),
    (59, 'Sorghum', 'GRAIN', TRUE, 'Sorghum'),
    (27, 'Rye', 'GRAIN', TRUE, 'Rye'),
    (28, 'Oats', 'GRAIN', TRUE, 'Oats'),
    (29, 'Millet', 'GRAIN', TRUE, 'Millet'),
    (30, 'Speltz', 'GRAIN', TRUE, 'Speltz'),
    (39, 'Sugarbeets', 'OTHER', TRUE, 'Sugarbeets'),
    (41, 'Dry Beans', 'VEGETABLE', TRUE, 'Dry Beans'),
    (42, 'Potatoes', 'VEGETABLE', TRUE, 'Potatoes'),
    (43, 'Other Crops', 'OTHER', FALSE, 'Other Crops'),
    (44, 'Sugarcane', 'OTHER', FALSE, 'Sugarcane'),
    (46, 'Sweet Potatoes', 'VEGETABLE', TRUE, 'Sweet Potatoes'),
    (47, 'Misc Vegs & Fruits', 'VEGETABLE', FALSE, 'Miscellaneous Vegetables & Fruits'),
    (48, 'Watermelons', 'FRUIT', TRUE, 'Watermelons'),
    (49, 'Onions', 'VEGETABLE', TRUE, 'Onions'),
    (50, 'Cucumbers', 'VEGETABLE', TRUE, 'Cucumbers'),
    (51, 'Chick Peas', 'VEGETABLE', TRUE, 'Chick Peas'),
    (52, 'Lentils', 'VEGETABLE', TRUE, 'Lentils'),
    (53, 'Peas', 'VEGETABLE', TRUE, 'Peas'),
    (54, 'Tomatoes', 'VEGETABLE', TRUE, 'Tomatoes'),
    (55, 'Caneberries', 'FRUIT', FALSE, 'Caneberries'),
    (56, 'Hops', 'OTHER', FALSE, 'Hops'),
    (57, 'Herbs', 'OTHER', FALSE, 'Herbs'),
    (58, 'Clover/Wildflowers', 'FORAGE', FALSE, 'Clover/Wildflowers'),
    (60, 'Sunflowers', 'OILSEED', TRUE, 'Sunflowers'),
    (61, 'Canola', 'OILSEED', TRUE, 'Canola'),
    (66, 'Cherries', 'FRUIT', FALSE, 'Cherries'),
    (67, 'Peaches', 'FRUIT', FALSE, 'Peaches'),
    (68, 'Apples', 'FRUIT', FALSE, 'Apples'),
    (69, 'Grapes', 'FRUIT', FALSE, 'Grapes'),
    (70, 'Christmas Trees', 'OTHER', FALSE, 'Christmas Trees'),
    (71, 'Other Tree Crops', 'FRUIT', FALSE, 'Other Tree Crops'),
    (72, 'Citrus', 'FRUIT', FALSE, 'Citrus'),
    (74, 'Pecans', 'FRUIT', FALSE, 'Pecans'),
    (75, 'Almonds', 'FRUIT', FALSE, 'Almonds'),
    (76, 'Walnuts', 'FRUIT', FALSE, 'Walnuts'),
    (77, 'Pears', 'FRUIT', FALSE, 'Pears'),
    (111, 'Open Water', 'OTHER', FALSE, 'Open Water'),
    (121, 'Developed/Open Space', 'OTHER', FALSE, 'Developed/Open Space'),
    (122, 'Developed/Low Intensity', 'OTHER', FALSE, 'Developed/Low Intensity'),
    (123, 'Developed/Med Intensity', 'OTHER', FALSE, 'Developed/Medium Intensity'),
    (124, 'Developed/High Intensity', 'OTHER', FALSE, 'Developed/High Intensity'),
    (131, 'Barren', 'OTHER', FALSE, 'Barren'),
    (141, 'Deciduous Forest', 'OTHER', FALSE, 'Deciduous Forest'),
    (142, 'Evergreen Forest', 'OTHER', FALSE, 'Evergreen Forest'),
    (143, 'Mixed Forest', 'OTHER', FALSE, 'Mixed Forest'),
    (152, 'Shrubland', 'OTHER', FALSE, 'Shrubland'),
    (176, 'Grassland/Pasture', 'FORAGE', FALSE, 'Grassland/Pasture'),
    (190, 'Woody Wetlands', 'OTHER', FALSE, 'Woody Wetlands'),
    (195, 'Herbaceous Wetlands', 'OTHER', FALSE, 'Herbaceous Wetlands'),
    (204, 'Pistachios', 'FRUIT', FALSE, 'Pistachios'),
    (205, 'Triticale', 'GRAIN', TRUE, 'Triticale'),
    (206, 'Carrots', 'VEGETABLE', TRUE, 'Carrots'),
    (207, 'Asparagus', 'VEGETABLE', TRUE, 'Asparagus'),
    (208, 'Garlic', 'VEGETABLE', TRUE, 'Garlic'),
    (209, 'Cantaloupes', 'FRUIT', TRUE, 'Cantaloupes'),
    (210, 'Prunes', 'FRUIT', FALSE, 'Prunes'),
    (211, 'Olives', 'FRUIT', FALSE, 'Olives'),
    (212, 'Oranges', 'FRUIT', FALSE, 'Oranges'),
    (213, 'Honeydew Melons', 'FRUIT', TRUE, 'Honeydew Melons'),
    (214, 'Broccoli', 'VEGETABLE', TRUE, 'Broccoli'),
    (215, 'Peppers', 'VEGETABLE', TRUE, 'Peppers'),
    (216, 'Pomegranates', 'FRUIT', FALSE, 'Pomegranates'),
    (217, 'Nectarines', 'FRUIT', FALSE, 'Nectarines'),
    (218, 'Greens', 'VEGETABLE', TRUE, 'Greens'),
    (219, 'Plums', 'FRUIT', FALSE, 'Plums'),
    (220, 'Strawberries', 'FRUIT', FALSE, 'Strawberries'),
    (221, 'Squash', 'VEGETABLE', TRUE, 'Squash'),
    (222, 'Apricots', 'FRUIT', FALSE, 'Apricots'),
    (223, 'Vetch', 'FORAGE', FALSE, 'Vetch'),
    (224, 'Dbl Crop WinWht/Soybeans', 'GRAIN', TRUE, 'Double Crop Winter Wheat/Soybeans'),
    (225, 'Dbl Crop Oats/Corn', 'GRAIN', TRUE, 'Double Crop Oats/Corn'),
    (226, 'Lettuce', 'VEGETABLE', TRUE, 'Lettuce'),
    (227, 'Dbl Crop Triticale/Corn', 'GRAIN', TRUE, 'Double Crop Triticale/Corn'),
    (228, 'Pumpkins', 'VEGETABLE', TRUE, 'Pumpkins'),
    (229, 'Dbl Crop Lettuce/Durum Wht', 'GRAIN', TRUE, 'Double Crop Lettuce/Durum Wheat'),
    (230, 'Dbl Crop Lettuce/Barley', 'GRAIN', TRUE, 'Double Crop Lettuce/Barley'),
    (231, 'Dbl Crop Durum Wht/Sorghum', 'GRAIN', TRUE, 'Double Crop Durum Wheat/Sorghum'),
    (232, 'Dbl Crop Barley/Sorghum', 'GRAIN', TRUE, 'Double Crop Barley/Sorghum'),
    (233, 'Dbl Crop WinWht/Corn', 'GRAIN', TRUE, 'Double Crop Winter Wheat/Corn'),
    (234, 'Dbl Crop WinWht/Cotton', 'GRAIN', TRUE, 'Double Crop Winter Wheat/Cotton'),
    (235, 'Dbl Crop Soybeans/Cotton', 'OILSEED', TRUE, 'Double Crop Soybeans/Cotton'),
    (236, 'Dbl Crop Soybeans/Oats', 'OILSEED', TRUE, 'Double Crop Soybeans/Oats'),
    (237, 'Dbl Crop Corn/Soybeans', 'GRAIN', TRUE, 'Double Crop Corn/Soybeans'),
    (238, 'Blueberries', 'FRUIT', FALSE, 'Blueberries'),
    (239, 'Cabbage', 'VEGETABLE', TRUE, 'Cabbage'),
    (240, 'Cauliflower', 'VEGETABLE', TRUE, 'Cauliflower'),
    (241, 'Celery', 'VEGETABLE', TRUE, 'Celery'),
    (242, 'Radishes', 'VEGETABLE', TRUE, 'Radishes'),
    (243, 'Turnips', 'VEGETABLE', TRUE, 'Turnips'),
    (244, 'Eggplants', 'VEGETABLE', TRUE, 'Eggplants'),
    (245, 'Gourds', 'VEGETABLE', TRUE, 'Gourds'),
    (246, 'Cranberries', 'FRUIT', FALSE, 'Cranberries'),
    (247, 'Dbl Crop Barley/Corn', 'GRAIN', TRUE, 'Double Crop Barley/Corn')
ON CONFLICT (cdl_code) DO NOTHING;

-- 2. region ------------------------------------------------------------
-- Defines geographical regions for crop data analysis
-- Can represent counties, watersheds, custom polygons, etc.

CREATE TABLE IF NOT EXISTS region (
    region_id          SERIAL PRIMARY KEY,
    region_type        VARCHAR(50) NOT NULL,  -- 'COUNTY', 'WATERSHED', 'CUSTOM', 'STATE', 'MULTI_STATE'
    name               VARCHAR(200) NOT NULL,  -- Region name (e.g., 'Rush County', 'Watershed 123')
    state              CHAR(2),  -- State code (if applicable)
    county             VARCHAR(100),  -- County name (if region_type = 'COUNTY')
    description        TEXT,
    geom               geometry(Polygon, 4326),  -- Region boundary polygon
    created_date       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    notes              TEXT,
    
    UNIQUE(region_type, name, state, county)
);

-- Create spatial index for region boundaries
CREATE INDEX IF NOT EXISTS region_geom_gix ON region USING gist (geom);
CREATE INDEX IF NOT EXISTS region_type_ix ON region USING btree (region_type);
CREATE INDEX IF NOT EXISTS region_state_county_ix ON region USING btree (state, county);

-- 3. crop_acres --------------------------------------------------------
-- Main fact table: Region | Year | Crop | Acres
-- Stores the actual crop acreage data from CDL analysis

CREATE TABLE IF NOT EXISTS crop_acres (
    crop_acres_id      SERIAL PRIMARY KEY,
    region_id           INT NOT NULL REFERENCES region(region_id),
    crop_type_id        INT NOT NULL REFERENCES crop_type(crop_type_id),
    year                SMALLINT NOT NULL,  -- Year of CDL data (e.g., 2015, 2024)
    acres               NUMERIC(12, 4) NOT NULL,  -- Acres of this crop in this region/year
    pixel_count         BIGINT,  -- Original pixel count from CDL (if available)
    data_source         VARCHAR(100) DEFAULT 'USDA NASS CDL',  -- Source of data
    processing_date     TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,  -- When data was processed
    notes               TEXT,
    
    UNIQUE(region_id, crop_type_id, year)  -- One record per region/crop/year combination
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS crop_acres_region_year_ix ON crop_acres USING btree (region_id, year);
CREATE INDEX IF NOT EXISTS crop_acres_crop_year_ix ON crop_acres USING btree (crop_type_id, year);
CREATE INDEX IF NOT EXISTS crop_acres_year_ix ON crop_acres USING btree (year);

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON crop_type TO agadmin;
GRANT SELECT, INSERT, UPDATE, DELETE ON region TO agadmin;
GRANT SELECT, INSERT, UPDATE, DELETE ON crop_acres TO agadmin;
GRANT USAGE, SELECT ON SEQUENCE crop_type_crop_type_id_seq TO agadmin;
GRANT USAGE, SELECT ON SEQUENCE region_region_id_seq TO agadmin;
GRANT USAGE, SELECT ON SEQUENCE crop_acres_crop_acres_id_seq TO agadmin;

-- Add comments
COMMENT ON TABLE crop_type IS 'Lookup table for crop types with USDA NASS CDL codes';
COMMENT ON TABLE region IS 'Geographical regions for crop data analysis (counties, watersheds, custom polygons)';
COMMENT ON TABLE crop_acres IS 'Crop acreage data by region, year, and crop type from CDL analysis';
COMMENT ON COLUMN crop_acres.acres IS 'Acres calculated from CDL pixel counts (pixels × 0.222394 for Albers projection)';
COMMENT ON COLUMN crop_acres.pixel_count IS 'Original pixel count from CDL raster analysis';

