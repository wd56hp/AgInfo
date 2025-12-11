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

// Facility data
const facilities = [
    {
        name: 'Alexander',
        city: 'Alexander',
        state: 'KS',
        address: '200 W K-96',
        lat: 38.469440,
        lng: -99.553060
    },
    {
        name: 'Bison',
        city: 'Bison',
        state: 'KS',
        address: '100 North Main',
        lat: 38.528900,
        lng: -99.195400
    }
];

// Add markers for all facilities
facilities.forEach(facility => {
    const marker = L.marker([facility.lat, facility.lng])
        .addTo(map)
        .bindPopup(`<b>${facility.name}</b><br>${facility.city}, ${facility.state}<br>${facility.address}`);
});

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
    console.log('Map ready - showing', facilities.length, 'facilities');
    // loadFacilities();
});

