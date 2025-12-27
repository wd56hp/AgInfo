# AgInfo
Ag Facility and Services Info

## Overview

AgInfo is a comprehensive agricultural facility and services information system with:
- **Interactive Web Maps**: Leaflet-based maps for visualizing facilities
- **GeoServer Integration**: WMS/WFS services for spatial data
- **PostGIS Database**: PostgreSQL with PostGIS extension for geospatial data
- **Django Admin Interface**: Web-based CRUD interface for managing data (see [README_DJANGO.md](README_DJANGO.md))

## Quick Start

1. **Configure environment** (optional):
   ```bash
   cp .env.example .env
   # Edit .env with your preferred settings (ports, passwords, etc.)
   ```

2. **Start all services**:
   ```bash
   docker-compose up -d
   ```

2. **Access web maps**: `http://your-server:8091`
   - Standard Map: `/aginfo-map.html`
   - Network Map: `/aginfo-network-map.html`
   - Starburst Chart: `/aginfo-starburst.html`

3. **Access GeoServer**: `http://your-server:8090/geoserver`

4. **Access Django Admin** (after setup): `http://your-server:8000/admin`
   - See [README_DJANGO.md](README_DJANGO.md) for setup instructions

## Services

- **PostGIS** (port 15433): PostgreSQL database with PostGIS extension
- **GeoServer** (port 8090): WMS/WFS map services
- **Web** (port 8091): Static HTML maps served by nginx
- **Django** (port 8000): Admin interface for data management