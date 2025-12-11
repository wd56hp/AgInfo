// Initialize the map
const map = L.map('map').setView([38.5, -99.5], 6); // Center on Kansas

// Add OpenStreetMap tile layer
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19
}).addTo(map);

// GeoServer configuration - dynamically use current hostname
const currentHost = window.location.hostname;
const GEOSERVER_URL = `http://${currentHost}:8090/geoserver`;
const WFS_LAYER = 'aginfo:facility';

// Store markers for potential cleanup
let facilityMarkers = [];

// Function to load facilities dynamically from GeoServer WFS
async function loadFacilities() {
    try {
        // Build WFS GetFeature request URL
        const wfsUrl = `${GEOSERVER_URL}/wfs?` +
            `service=WFS&` +
            `version=1.1.0&` +
            `request=GetFeature&` +
            `typeName=${WFS_LAYER}&` +
            `outputFormat=application/json&` +
            `srsName=EPSG:4326`;

        console.log('Fetching facilities from:', wfsUrl);
        
        const response = await fetch(wfsUrl);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const geojson = await response.json();
        
        // Clear existing markers
        facilityMarkers.forEach(marker => map.removeLayer(marker));
        facilityMarkers = [];
        
        // Process GeoJSON features
        if (geojson.features && geojson.features.length > 0) {
            geojson.features.forEach(feature => {
                const props = feature.properties;
                const coords = feature.geometry.coordinates; // [lng, lat] in GeoJSON
                
                // Build popup content
                const popupContent = `
                    <b>${props.name || 'Unknown'}</b><br>
                    ${props.city || ''}, ${props.state || ''}<br>
                    ${props.address_line1 || ''}
                    ${props.description ? '<br><small>' + props.description + '</small>' : ''}
                `;
                
                // Create marker (note: GeoJSON uses [lng, lat], Leaflet uses [lat, lng])
                const marker = L.marker([coords[1], coords[0]])
                    .addTo(map)
                    .bindPopup(popupContent);
                
                facilityMarkers.push(marker);
            });
            
            console.log(`Loaded ${facilityMarkers.length} facilities from database`);
            
            // Fit map to show all facilities
            if (facilityMarkers.length > 0) {
                const group = new L.featureGroup(facilityMarkers);
                map.fitBounds(group.getBounds().pad(0.1));
            }
        } else {
            console.warn('No facilities found in database');
        }
    } catch (error) {
        console.error('Error loading facilities:', error);
        // Show error message to user
        L.popup()
            .setLatLng([38.5, -99.5])
            .setContent(`<b>Error loading facilities</b><br>${error.message}<br><small>Check console for details</small>`)
            .openOn(map);
    }
}

// Load facilities when map is ready
map.whenReady(() => {
    console.log('Map ready - loading facilities from GeoServer...');
    loadFacilities();
});

