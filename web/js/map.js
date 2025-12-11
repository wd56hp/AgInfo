// Initialize the map
const map = L.map('map').setView([38.5, -99.5], 6); // Center on Kansas

// Add OpenStreetMap tile layer
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19
}).addTo(map);

// GeoServer WMS layer (uncomment and configure when ready)
// const geoserverWMS = L.tileLayer.wms('http://172.28.0.20:8080/geoserver/aginfo/wms', {
//     layers: 'aginfo:facilities',
//     format: 'image/png',
//     transparent: true,
//     version: '1.1.0'
// }).addTo(map);

// Example marker (replace with GeoServer layer or API call)
const exampleMarker = L.marker([38.471820, -99.551400])
    .addTo(map)
    .bindPopup('<b>United Ag Services</b><br>Alexander, KS<br>200 W K-96');

// Function to load facilities from GeoServer or API
async function loadFacilities() {
    // TODO: Fetch facilities from GeoServer WMS/WFS or REST API
    // Example:
    // const response = await fetch('http://172.28.0.20:8080/geoserver/aginfo/ows?service=WFS&version=1.0.0&request=GetFeature&typeName=aginfo:facilities&outputFormat=application/json');
    // const data = await response.json();
    // Add markers or layers from the data
}

// Load facilities on map ready
map.whenReady(() => {
    console.log('Map ready');
    // loadFacilities();
});

