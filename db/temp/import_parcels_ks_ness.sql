-- Import KS Ness parcels. CSV layout matches ks_ness export (trailing mail_csz / county_provided_mailing_address
-- instead of mailing_address / boundary_desc). Staging as TEXT avoids empty-string integer errors.

BEGIN;

DELETE FROM parcels WHERE state2 = 'KS' AND lower(county) = 'ness';

CREATE TEMP TABLE ness_stg (
    geoid TEXT, parcelnumb TEXT, parcelnumb_no_formatting TEXT, state_parcelnumb TEXT,
    account_number TEXT, tax_id TEXT, alt_parcelnumb1 TEXT, alt_parcelnumb2 TEXT, alt_parcelnumb3 TEXT,
    usecode TEXT, usedesc TEXT, zoning TEXT, zoning_description TEXT, struct TEXT, structno TEXT,
    yearbuilt TEXT, year_built_effective_date TEXT, numstories TEXT, numunits TEXT, numrooms TEXT,
    num_bath TEXT, num_bath_partial TEXT, num_bedrooms TEXT, structstyle TEXT, parvaltype TEXT,
    improvval TEXT, landval TEXT, parval TEXT, agval TEXT, saleprice TEXT, saledate TEXT,
    taxamt TEXT, taxyear TEXT, last_ownership_transfer_date TEXT, owntype TEXT, owner TEXT,
    unmodified_owner TEXT, ownfrst TEXT, ownlast TEXT, owner2 TEXT, owner3 TEXT, owner4 TEXT,
    previous_owner TEXT, mailadd TEXT, mail_address2 TEXT, careof TEXT, mail_addno TEXT,
    mail_addpref TEXT, mail_addstr TEXT, mail_addsttyp TEXT, mail_addstsuf TEXT, mail_unit TEXT,
    mail_city TEXT, mail_state2 TEXT, mail_zip TEXT, mail_country TEXT, mail_urbanization TEXT,
    original_mailing_address TEXT, address TEXT, address2 TEXT, saddno TEXT, saddpref TEXT, saddstr TEXT,
    saddsttyp TEXT, saddstsuf TEXT, sunit TEXT, scity TEXT, original_address TEXT, city TEXT,
    county TEXT, state2 TEXT, szip TEXT, szip5 TEXT, urbanization TEXT, location_name TEXT,
    address_source TEXT, legaldesc TEXT, plat TEXT, book TEXT, page TEXT, block TEXT, lot TEXT,
    neighborhood TEXT, neighborhood_code TEXT, subdivision TEXT, lat TEXT, lon TEXT, qoz TEXT,
    qoz_tract TEXT, census_tract TEXT, census_block TEXT, census_blockgroup TEXT, census_zcta TEXT,
    ll_last_refresh TEXT, sourceurl TEXT, recrdareatx TEXT, recrdareano TEXT, area_building TEXT,
    area_building_definition TEXT, deeded_acres TEXT, gisacre TEXT, sqft TEXT, ll_gisacre TEXT,
    ll_gissqft TEXT, plss_township TEXT, plss_section TEXT, plss_range TEXT, reviseddate TEXT,
    path TEXT, ll_stable_id TEXT, ll_uuid TEXT, ll_stack_uuid TEXT, ll_updated_at TEXT,
    kspid TEXT, co_abbr TEXT, dateparcels TEXT, property_status TEXT, taxing_unit TEXT,
    mail_csz TEXT, county_provided_mailing_address TEXT
);

COPY ness_stg FROM '/tmp/aginfo-import/ks_ness.csv'
WITH (FORMAT csv, HEADER true, DELIMITER ',', QUOTE '"', ESCAPE '"', NULL '');

-- Source extract may repeat the same (geoid, parcelnumb); keep one row per key.
DELETE FROM ness_stg s
WHERE EXISTS (
    SELECT 1 FROM ness_stg s2
    WHERE s2.ctid < s.ctid
      AND NULLIF(TRIM(s2.geoid), '') IS NOT DISTINCT FROM NULLIF(TRIM(s.geoid), '')
      AND NULLIF(TRIM(s2.parcelnumb), '') IS NOT DISTINCT FROM NULLIF(TRIM(s.parcelnumb), '')
);

INSERT INTO parcels (
    geoid, parcelnumb, parcelnumb_no_formatting, state_parcelnumb, account_number, tax_id,
    alt_parcelnumb1, alt_parcelnumb2, alt_parcelnumb3, usecode, usedesc, zoning, zoning_description,
    struct, structno, yearbuilt, year_built_effective_date, numstories, numunits, numrooms,
    num_bath, num_bath_partial, num_bedrooms, structstyle, parvaltype, improvval, landval, parval, agval,
    saleprice, saledate, taxamt, taxyear, last_ownership_transfer_date, owntype, owner, unmodified_owner,
    ownfrst, ownlast, owner2, owner3, owner4, previous_owner, mailadd, mail_address2, careof,
    mail_addno, mail_addpref, mail_addstr, mail_addsttyp, mail_addstsuf, mail_unit, mail_city, mail_state2,
    mail_zip, mail_country, mail_urbanization, original_mailing_address, address, address2, saddno,
    saddpref, saddstr, saddsttyp, saddstsuf, sunit, scity, original_address, city, county, state2,
    szip, szip5, urbanization, location_name, address_source, legaldesc, plat, book, page, block, lot,
    neighborhood, neighborhood_code, subdivision, lat, lon, qoz, qoz_tract, census_tract, census_block,
    census_blockgroup, census_zcta, ll_last_refresh, sourceurl, recrdareatx, recrdareano, area_building,
    area_building_definition, deeded_acres, gisacre, sqft, ll_gisacre, ll_gissqft, plss_township,
    plss_section, plss_range, reviseddate, path, ll_stable_id, ll_uuid, ll_stack_uuid, ll_updated_at,
    kspid, co_abbr, dateparcels, mailing_address, boundary_desc, property_status, taxing_unit
)
SELECT
    NULLIF(TRIM(geoid), ''),
    NULLIF(TRIM(parcelnumb), ''),
    NULLIF(TRIM(parcelnumb_no_formatting), ''),
    NULLIF(TRIM(state_parcelnumb), ''),
    NULLIF(TRIM(account_number), ''),
    NULLIF(TRIM(tax_id), ''),
    NULLIF(TRIM(alt_parcelnumb1), ''),
    NULLIF(TRIM(alt_parcelnumb2), ''),
    NULLIF(TRIM(alt_parcelnumb3), ''),
    NULLIF(TRIM(usecode), ''),
    NULLIF(TRIM(usedesc), ''),
    NULLIF(TRIM(zoning), ''),
    NULLIF(TRIM(zoning_description), ''),
    NULLIF(TRIM(struct), ''),
    NULLIF(TRIM(structno), ''),
    NULLIF(TRIM(yearbuilt), '')::INTEGER,
    NULLIF(TRIM(year_built_effective_date), ''),
    NULLIF(TRIM(numstories), '')::NUMERIC,
    NULLIF(TRIM(numunits), '')::INTEGER,
    NULLIF(TRIM(numrooms), '')::INTEGER,
    NULLIF(TRIM(num_bath), '')::NUMERIC,
    NULLIF(TRIM(num_bath_partial), '')::NUMERIC,
    NULLIF(TRIM(num_bedrooms), '')::INTEGER,
    NULLIF(TRIM(structstyle), ''),
    NULLIF(TRIM(parvaltype), ''),
    NULLIF(TRIM(improvval), '')::NUMERIC,
    NULLIF(TRIM(landval), '')::NUMERIC,
    NULLIF(TRIM(parval), '')::NUMERIC,
    NULLIF(TRIM(agval), '')::NUMERIC,
    NULLIF(TRIM(saleprice), '')::NUMERIC,
    NULLIF(TRIM(saledate), ''),
    NULLIF(TRIM(taxamt), '')::NUMERIC,
    NULLIF(TRIM(taxyear), '')::INTEGER,
    NULLIF(TRIM(last_ownership_transfer_date), ''),
    NULLIF(TRIM(owntype), ''),
    NULLIF(TRIM(owner), ''),
    NULLIF(TRIM(unmodified_owner), ''),
    NULLIF(TRIM(ownfrst), ''),
    NULLIF(TRIM(ownlast), ''),
    NULLIF(TRIM(owner2), ''),
    NULLIF(TRIM(owner3), ''),
    NULLIF(TRIM(owner4), ''),
    NULLIF(TRIM(previous_owner), ''),
    NULLIF(TRIM(mailadd), ''),
    NULLIF(TRIM(mail_address2), ''),
    NULLIF(TRIM(careof), ''),
    NULLIF(TRIM(mail_addno), ''),
    NULLIF(TRIM(mail_addpref), ''),
    NULLIF(TRIM(mail_addstr), ''),
    NULLIF(TRIM(mail_addsttyp), ''),
    NULLIF(TRIM(mail_addstsuf), ''),
    NULLIF(TRIM(mail_unit), ''),
    NULLIF(TRIM(mail_city), ''),
    NULLIF(TRIM(mail_state2), ''),
    NULLIF(TRIM(mail_zip), ''),
    NULLIF(TRIM(mail_country), ''),
    NULLIF(TRIM(mail_urbanization), ''),
    NULLIF(TRIM(original_mailing_address), ''),
    NULLIF(TRIM(address), ''),
    NULLIF(TRIM(address2), ''),
    NULLIF(TRIM(saddno), ''),
    NULLIF(TRIM(saddpref), ''),
    NULLIF(TRIM(saddstr), ''),
    NULLIF(TRIM(saddsttyp), ''),
    NULLIF(TRIM(saddstsuf), ''),
    NULLIF(TRIM(sunit), ''),
    NULLIF(TRIM(scity), ''),
    NULLIF(TRIM(original_address), ''),
    NULLIF(TRIM(city), ''),
    NULLIF(TRIM(county), ''),
    NULLIF(TRIM(state2), ''),
    NULLIF(TRIM(szip), ''),
    NULLIF(TRIM(szip5), ''),
    NULLIF(TRIM(urbanization), ''),
    NULLIF(TRIM(location_name), ''),
    NULLIF(TRIM(address_source), ''),
    NULLIF(TRIM(legaldesc), ''),
    NULLIF(TRIM(plat), ''),
    NULLIF(TRIM(book), ''),
    NULLIF(TRIM(page), ''),
    NULLIF(TRIM(block), ''),
    NULLIF(TRIM(lot), ''),
    NULLIF(TRIM(neighborhood), ''),
    NULLIF(TRIM(neighborhood_code), ''),
    NULLIF(TRIM(subdivision), ''),
    NULLIF(TRIM(lat), '')::DOUBLE PRECISION,
    NULLIF(TRIM(lon), '')::DOUBLE PRECISION,
    CASE
        WHEN TRIM(LOWER(qoz)) IN ('t', 'true', 'y', 'yes', '1') THEN TRUE
        WHEN TRIM(LOWER(qoz)) IN ('f', 'false', 'n', 'no', '0') THEN FALSE
        ELSE NULL
    END,
    NULLIF(TRIM(qoz_tract), ''),
    NULLIF(TRIM(census_tract), ''),
    NULLIF(TRIM(census_block), ''),
    NULLIF(TRIM(census_blockgroup), ''),
    NULLIF(TRIM(census_zcta), ''),
    NULLIF(TRIM(ll_last_refresh), ''),
    NULLIF(TRIM(sourceurl), ''),
    NULLIF(TRIM(recrdareatx), ''),
    NULLIF(TRIM(recrdareano), '')::NUMERIC,
    NULLIF(TRIM(area_building), '')::NUMERIC,
    NULLIF(TRIM(area_building_definition), ''),
    NULLIF(TRIM(deeded_acres), '')::NUMERIC,
    NULLIF(TRIM(gisacre), '')::NUMERIC,
    NULLIF(TRIM(sqft), '')::NUMERIC,
    NULLIF(TRIM(ll_gisacre), '')::NUMERIC,
    NULLIF(TRIM(ll_gissqft), '')::NUMERIC,
    NULLIF(TRIM(plss_township), ''),
    NULLIF(TRIM(plss_section), ''),
    NULLIF(TRIM(plss_range), ''),
    NULLIF(TRIM(reviseddate), ''),
    NULLIF(TRIM(path), ''),
    NULLIF(TRIM(ll_stable_id), ''),
    NULLIF(TRIM(ll_uuid), '')::UUID,
    NULLIF(TRIM(ll_stack_uuid), '')::UUID,
    NULLIF(TRIM(ll_updated_at), '')::TIMESTAMPTZ,
    NULLIF(TRIM(kspid), ''),
    NULLIF(TRIM(co_abbr), ''),
    NULLIF(TRIM(dateparcels), ''),
    COALESCE(NULLIF(TRIM(mail_csz), ''), NULLIF(TRIM(county_provided_mailing_address), '')),
    NULL::TEXT,
    NULLIF(TRIM(property_status), ''),
    NULLIF(TRIM(taxing_unit), '')
FROM ness_stg;

UPDATE parcels
SET geom = ST_SetSRID(ST_MakePoint(lon, lat), 4326)
WHERE state2 = 'KS'
  AND lower(county) = 'ness'
  AND lat IS NOT NULL
  AND lon IS NOT NULL;

COMMIT;
