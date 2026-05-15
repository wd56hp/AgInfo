-- Import KS Trego parcels from Regrid-style CSV (same layout as ks_barton, ks_ellis, etc.)
-- CSV path is /tmp/aginfo-import in the PostGIS container (host: db/temp).

BEGIN;

DELETE FROM parcels WHERE state2 = 'KS' AND lower(county) = 'trego';

COPY parcels (
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
FROM '/tmp/aginfo-import/ks_trego.csv'
WITH (FORMAT csv, HEADER true, DELIMITER ',', QUOTE '"', ESCAPE '"', NULL '');

UPDATE parcels
SET geom = ST_SetSRID(ST_MakePoint(lon, lat), 4326)
WHERE state2 = 'KS'
  AND lower(county) = 'trego'
  AND lat IS NOT NULL
  AND lon IS NOT NULL;

COMMIT;
