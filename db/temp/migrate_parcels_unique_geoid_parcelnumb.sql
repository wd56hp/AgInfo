-- Parcel numbers are unique per county (geoid), not statewide. Replace global parcelnumb uniqueness.
-- Run once on existing DBs: docker exec -i aginfo-postgis psql -U agadmin -d aginfo -f /tmp/aginfo-import/migrate_parcels_unique_geoid_parcelnumb.sql
DROP INDEX IF EXISTS parcels_parcelnumb_uidx;
CREATE UNIQUE INDEX IF NOT EXISTS parcels_geoid_parcelnumb_uidx ON parcels (geoid, parcelnumb);
