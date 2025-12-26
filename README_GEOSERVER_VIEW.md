# GeoServer SQL View Setup

To avoid storing data in public repository files, we use a SQL view in the database that joins facility with company and facility_type tables to include readable names.

## Database View

The view `facility_with_names` is created automatically by `db/init/04_facility_view_with_names.sql`. This view includes:
- All facility columns
- `company_name` - joined from company table
- `facility_type_name` - joined from facility_type table

## GeoServer Configuration

You need to update your GeoServer layer to use this view instead of the base `facility` table:

1. Log into GeoServer (http://172.16.101.20:8090/geoserver)
2. Go to **Data > Workspaces > aginfo > facility**
3. Click **Edit** (pencil icon)
4. Under **Data**, change the **Feature Type** from `facility` to `facility_with_names`
5. Or create a new layer:
   - Go to **Data > Stores > aginfo (PostGIS)**
   - Click **New Layer**
   - Select `facility_with_names` from the list
   - Configure as needed
   - Publish the layer

## Benefits

- **No data files in repository** - All data stays in the database
- **Always up-to-date** - Names are joined at query time
- **Single source of truth** - Database is the only source
- **No maintenance** - No need to regenerate lookup files

## Web Code

The web code (`web/aginfo-map.html`) will automatically use:
- `props.company_name` - if available from the view
- `props.facility_type_name` - if available from the view
- Falls back to lookups if names aren't available (for backward compatibility)

## Verification

After updating GeoServer, check that the WFS response includes `company_name` and `facility_type_name`:

```bash
curl "http://172.16.101.20:8090/geoserver/wfs?service=WFS&version=1.1.0&request=GetFeature&typeName=aginfo:facility_with_names&outputFormat=application/json&maxFeatures=1"
```

You should see `company_name` and `facility_type_name` in the properties.





