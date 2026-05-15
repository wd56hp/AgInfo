-- Parcel numbers are unique per county (geoid), not statewide.
DROP INDEX IF EXISTS parcels_parcelnumb_uidx;
CREATE UNIQUE INDEX IF NOT EXISTS parcels_geoid_parcelnumb_uidx ON parcels (geoid, parcelnumb);
