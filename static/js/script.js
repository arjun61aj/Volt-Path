const radius=document.querySelector('#radius'), radiusValue=document.querySelector('#radius-value');
if(radius){radius.addEventListener('input',()=>radiusValue.value=`${radius.value} km`)}
const geo=document.querySelector('#geolocate');
if(geo) geo.addEventListener('click',()=>{if(!navigator.geolocation){alert('Geolocation is not available in this browser.');return}geo.textContent='Locating…';navigator.geolocation.getCurrentPosition(p=>{document.querySelector('#latitude').value=p.coords.latitude;document.querySelector('#longitude').value=p.coords.longitude;document.querySelector('#location').value='Current location';geo.textContent='✓ Location captured'},()=>{geo.textContent='◎ Use my current location';alert('Location permission was not granted. You can enter an area or coordinates instead.')},{enableHighAccuracy:true,timeout:8000})});
if(window.mapData && window.L){
 const u=mapData.user, map=L.map('map',{scrollWheelZoom:false}).setView([u.lat,u.lon],11);
 L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap',maxZoom:19}).addTo(map);
 const icon=t=>L.divIcon({className:`map-marker ${t}`,iconSize:[26,26],iconAnchor:[13,25]});
 L.marker([u.lat,u.lon],{icon:icon('user')}).addTo(map).bindPopup('<b>Your starting point</b>');
 const bounds=[[u.lat,u.lon]];
 mapData.stations.forEach((s,i)=>{bounds.push([s.latitude,s.longitude]);L.marker([s.latitude,s.longitude],{icon:icon(i===0&&s.eligible?'best':'alt')}).addTo(map).bindPopup(`<b>${s.name}</b><br>${s.distance_km} km · ${s.counts.available}/${s.counts.total} free<br><a href="/station/${s.station_id}">View details →</a>`) });
 if(bounds.length>1)map.fitBounds(bounds,{padding:[30,30],maxZoom:13});
}
// Version 2 station editor: multiple normalized charger records.
const chargerList=document.querySelector('#charger-list'), chargerTemplate=document.querySelector('#charger-template');
function renumberChargers(){if(!chargerList)return;[...chargerList.querySelectorAll('.charger-editor')].forEach((x,i)=>x.querySelector('.charger-index').textContent=i+1);chargerList.querySelectorAll('.remove-charger').forEach(b=>b.disabled=chargerList.children.length===1);const total=document.querySelector('#total-chargers');if(total)total.value=chargerList.children.length}
if(chargerList){document.querySelector('#add-charger').addEventListener('click',()=>{chargerList.append(chargerTemplate.content.cloneNode(true));renumberChargers()});chargerList.addEventListener('click',e=>{if(e.target.classList.contains('remove-charger')&&chargerList.children.length>1){e.target.closest('.charger-editor').remove();renumberChargers()}});renumberChargers()}
const is24=document.querySelector('#is-24');
function toggleHours(){if(!is24)return;document.querySelectorAll('.hours-fields input').forEach(x=>{x.disabled=is24.checked;x.required=!is24.checked})}
if(is24){is24.addEventListener('change',toggleHours);toggleHours()}
// Interactive station-location picker shared by Add, Edit and Register pages.
(function initStationLocationMap(){
 const container=document.querySelector('#admin-map');
 const lat=document.querySelector('#admin-lat');
 const lon=document.querySelector('#admin-lon');
 if(!container || !lat || !lon) return;

 const help=container.nextElementSibling;
 const normalHelp=help ? help.textContent : '';
 const valid=(a,b)=>Number.isFinite(a)&&Number.isFinite(b)&&a>=-90&&a<=90&&b>=-180&&b<=180;
 const fieldCoordinates=()=>[Number.parseFloat(lat.value),Number.parseFloat(lon.value)];
 const fallback=[
   Number(window.adminMapData?.lat) || 19.0760,
   Number(window.adminMapData?.lon) || 72.8777
 ];

 // Leaflet must be loaded before this file. Show a useful error instead of a silent blank box.
 if(!window.L){
   container.classList.add('map-load-error');
   container.textContent='Map library could not load. Check your internet connection and refresh the page.';
   return;
 }
 // Prevent “Map container is already initialized” if another script invokes this initializer.
 if(container._leaflet_id) return;

 const initial=fieldCoordinates();
 const hasInitial=valid(initial[0],initial[1]);
 const centre=hasInitial?initial:(valid(fallback[0],fallback[1])?fallback:[19.0760,72.8777]);
 const map=L.map(container,{scrollWheelZoom:true}).setView(centre,13);
 const tiles=L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
   maxZoom:19,
   attribution:'&copy; OpenStreetMap contributors'
 }).addTo(map);
 let marker=null;

 const stationName=()=>document.querySelector('input[name="name"]')?.value.trim()||'New Charging Station';
 const popupNode=(a,b)=>{
   const box=document.createElement('div');
   const title=document.createElement('strong');
   const details=document.createElement('div');
   title.textContent=stationName();
   details.textContent=`Selected location\nLatitude: ${a.toFixed(6)}\nLongitude: ${b.toFixed(6)}`;
   details.style.whiteSpace='pre-line';
   details.style.marginTop='4px';
   box.append(title,details);
   return box;
 };
 const updatePopup=(a,b)=>marker&&marker.bindPopup(popupNode(a,b));
 const ensureMarker=(a,b)=>{
   if(marker) marker.setLatLng([a,b]);
   else {
     marker=L.marker([a,b],{draggable:true,title:'Selected charging station location'}).addTo(map);
     marker.on('dragend',()=>select(marker.getLatLng().lat,marker.getLatLng().lng,false));
   }
   updatePopup(a,b);
 };
 const showValidity=(ok)=>{
   lat.setCustomValidity(ok?'':'Latitude must be between -90 and 90.');
   lon.setCustomValidity(ok?'':'Longitude must be between -180 and 180.');
   if(help){help.textContent=ok?normalHelp:'Invalid coordinates. Please enter valid values or select a location on the map.';help.classList.toggle('coordinate-error',!ok)}
 };
 function select(a,b,recentre=true){
   if(!valid(a,b)){showValidity(false);return}
   showValidity(true);
   lat.value=a.toFixed(6);lon.value=b.toFixed(6);
   ensureMarker(a,b);
   if(recentre) map.setView([a,b],Math.max(map.getZoom(),13));
 }
 function syncFields(){
   const [a,b]=fieldCoordinates();
   if(valid(a,b)) select(a,b,true); else showValidity(false);
 }

 if(hasInitial) ensureMarker(initial[0],initial[1]);
 map.on('click',e=>select(e.latlng.lat,e.latlng.lng,false));
 let fieldTimer;
 [lat,lon].forEach(input=>{
   input.addEventListener('input',()=>{clearTimeout(fieldTimer);fieldTimer=setTimeout(syncFields,250)});
   input.addEventListener('change',syncFields);
 });
 document.querySelector('input[name="name"]')?.addEventListener('input',()=>{if(marker){const p=marker.getLatLng();updatePopup(p.lat,p.lng)}});
 tiles.on('tileerror',()=>{if(help&&!help.classList.contains('coordinate-error')) help.textContent='Map tiles could not load. Check your connection; coordinates can still be entered manually.'});
 // Leaflet can otherwise remain partially blank when a responsive/sticky layout settles.
 setTimeout(()=>map.invalidateSize(),150);
 window.addEventListener('resize',()=>map.invalidateSize());
 window.stationLocationMap=map;
})();
// Named searches must not accidentally reuse coordinates captured by an earlier geolocation click.
const locationText=document.querySelector('#location');
if(locationText) locationText.addEventListener('input',()=>{
 const latitude=document.querySelector('#latitude'),longitude=document.querySelector('#longitude');
 if(latitude)latitude.value=''; if(longitude)longitude.value='';
});
