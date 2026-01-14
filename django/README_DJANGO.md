# Django + GeoDjango Admin Interface for AgInfo

This Django application provides a web-based admin interface for managing AgInfo database records.

## Features

- **Full CRUD Operations**: Create, Read, Update, Delete for all AgInfo entities
- **GeoDjango Integration**: Map-based editing for facilities with geographic coordinates
- **Django Admin Interface**: Built-in admin panel with search, filters, and list views
- **PostGIS Support**: Seamless integration with existing PostGIS database

## Models

The Django application includes models for all major AgInfo entities:

- **Company**: Organizations/companies
- **FacilityType**: Types of facilities (Grain Elevator, Ethanol Plant, etc.)
- **Facility**: Facilities with geographic coordinates (GeoDjango PointField)
- **FacilityContact**: Contact persons for facilities
- **ServiceType**: Types of services offered
- **FacilityService**: Many-to-many relationship between facilities and services
- **Product**: Products handled
- **FacilityProduct**: Many-to-many relationship between facilities and products
- **TransportMode**: Transport modes (TRUCK, RAIL, etc.)
- **FacilityTransportMode**: Many-to-many relationship between facilities and transport modes

## Setup

### Prerequisites

- Docker and Docker Compose installed
- PostGIS database running (via docker-compose)

### Installation

1. **Build and start the Django container**:
   ```bash
   docker-compose up -d django
   ```

2. **Create a superuser** (for admin access):
   ```bash
   docker exec -it aginfo-django python manage.py createsuperuser
   ```

3. **Access the admin interface**:
   - URL: `http://your-server:8000/admin`
   - Login with the superuser credentials created above

### Using Existing Database

The Django models are configured to use the existing AgInfo database. The models match the existing schema exactly, so no database migrations are needed for the core schema. However, you may want to run:

```bash
docker exec -it aginfo-django python manage.py migrate --run-syncdb
```

This will create Django's internal tables (for admin, sessions, etc.) without modifying your existing AgInfo tables.

## Configuration

### Environment Variables

Environment variables can be set in a `.env` file (copy from `.env.example`). The Django service uses:

**Database Connection:**
- `POSTGRES_DB`: Database name (default: `aginfo`)
- `POSTGRES_USER`: Database user (default: `agadmin`)
- `POSTGRES_PASSWORD`: Database password (default: `changeme`)
- `POSTGRES_HOST`: Database host (default: `172.28.0.10` - postgis container IP)
- `POSTGRES_PORT`: Database port (default: `5432`)

**Django Configuration:**
- `DJANGO_SECRET_KEY`: Django secret key (**change in production!**)
  - Generate a new key: `python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'`
- `DJANGO_DEBUG`: Debug mode (`True` for development, `False` for production)

**Port Configuration:**
- `DJANGO_HOST_PORT`: External port for Django admin (default: `8000`)
- `DJANGO_CONTAINER_PORT`: Internal container port (default: `8000`)

See `.env.example` for all available configuration options.

## Usage

### Admin Interface

1. Navigate to `http://your-server:8000/admin`
2. Log in with your superuser credentials
3. Use the admin interface to:
   - Add new companies, facilities, contacts, etc.
   - Edit existing records
   - Delete records
   - Search and filter records
   - View facilities on an interactive map (GeoDjango)

### Adding a New Facility

1. Go to **Facilities** → **Add Facility**
2. Fill in the facility details:
   - Name, description, company, facility type
   - Address information
   - **Latitude and Longitude** (coordinates)
   - Or use the **map widget** to click and set the location
3. The geometry field will be automatically generated from lat/lon
4. Save the facility

### Editing Facilities

Facilities can be edited directly in the admin interface. The map widget allows you to:
- View the facility location on an OpenStreetMap-based map
- Click on the map to update the location
- See the coordinates update automatically

## Integration with Existing System

The Django admin interface works seamlessly with:
- **GeoServer**: Any changes made in Django are immediately available in GeoServer layers
- **Web Maps**: The static HTML maps will reflect changes after GeoServer refreshes its cache
- **Database Views**: The `facility_with_names` view automatically includes new/updated records

## Development

### Running Management Commands

```bash
# Access Django shell
docker exec -it aginfo-django python manage.py shell

# Run migrations
docker exec -it aginfo-django python manage.py migrate

# Collect static files
docker exec -it aginfo-django python manage.py collectstatic

# Create superuser
docker exec -it aginfo-django python manage.py createsuperuser
```

### Project Structure

```
aginfo_django/
├── aginfo/           # Django app with models and admin
│   ├── models.py     # GeoDjango models
│   ├── admin.py      # Admin configuration
│   └── apps.py       # App configuration
├── settings.py       # Django settings
├── urls.py           # URL configuration
└── wsgi.py           # WSGI application
```

## Security Notes

- **Change the secret key** in production (`DJANGO_SECRET_KEY`)
- **Disable debug mode** in production (`DJANGO_DEBUG=False`)
- **Configure ALLOWED_HOSTS** appropriately in `settings.py`
- **Use HTTPS** in production
- **Implement authentication** beyond Django admin if needed
- **Set strong passwords** for superuser accounts

## Troubleshooting

### GDAL/GEOS Library Issues

If you encounter GDAL or GEOS library errors, ensure:
- The Dockerfile installs the required system libraries
- Environment variables `GDAL_LIBRARY_PATH` and `GEOS_LIBRARY_PATH` are set correctly
- The libraries exist at the specified paths in the container

### Database Connection Issues

- Verify the PostGIS container is running: `docker ps`
- Check that the database credentials match those in `docker-compose.yml`
- Ensure the network configuration allows communication between containers

### Map Widget Not Displaying

- Verify GDAL libraries are installed in the container
- Check browser console for JavaScript errors
- Ensure OpenStreetMap tiles can be loaded (internet connection required)

## Additional Resources

- [Django Documentation](https://docs.djangoproject.com/)
- [GeoDjango Documentation](https://docs.djangoproject.com/en/stable/ref/contrib/gis/)
- [PostGIS Documentation](https://postgis.net/documentation/)

