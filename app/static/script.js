const YAHOO_APPID = "dj00aiZpPWoyQVc5RXVkQWhXQyZzPWNvbnN1bWVyc2VjcmV0";

let map, adminMap, userLocation, markers = [], adminMarkers = [], alertPolygons = [];

async function geocodeWithYahoo(address) {
  const url = new URL("https://map.yahooapis.jp/geocode/V1/geoCoder");
  url.searchParams.set("appid", YAHOO_APPID);
  url.searchParams.set("query", address);
  url.searchParams.set("output", "json");

  const res = await fetch(url);
  if (!res.ok) throw new Error("Yahoo Geocode API error");
  const json = await res.json();
  if (!json.Feature?.length) throw new Error("住所が見つかりません");
  const [lon, lat] = json.Feature[0].Geometry.Coordinates
    .split(",")
    .map(parseFloat);
  return [lat, lon];
}

async function fetchShelters() {
    const search = document.getElementById('search')?.value;
    const form = document.getElementById('filter-form');
    const distSelect = document.getElementById('filter-distance');
    const maxDistance = distSelect ? parseFloat(distSelect.value) || 0 : 0;
    const params = new URLSearchParams();
    if (search) params.append('search', search);
    if (form) {
        if (form.pets_allowed.checked) params.append('pets_allowed', 'true');
        if (form.barrier_free.checked) params.append('barrier_free', 'true');
        if (form.toilet_available.checked) params.append('toilet_available', 'true');
        if (form.food_available.checked) params.append('food_available', 'true');
        if (form.medical_available.checked) params.append('medical_available', 'true');
        if (form.wifi_available.checked) params.append('wifi_available', 'true');
        if (form.charging_available.checked) params.append('charging_available', 'true');
    }
    try {
        const response = await fetch(`/api/shelters?${params}`);
        if (!response.ok) throw new Error('APIエラー');
       const allShelters = await response.json();
       // 現在地取得済みかつ距離指定があれば絞り込む
       const shelters = (userLocation && maxDistance > 0)
         ? allShelters.filter(s => {
             const d = calculateDistanceKm(userLocation, [s.latitude, s.longitude]);
             return d <= maxDistance;
           })
         : allShelters;
       if (document.getElementById('shelter-list')) {
           updateShelterList(shelters);
           updateMap(shelters);
        }
        if (document.getElementById('admin-shelter-list')) {
            updateAdminShelterList(shelters);
            updateAdminMap(shelters);
        }
    } catch (e) {
        console.error('fetchSheltersエラー:', e);
    }
}

function updateShelterList(shelters) {
    const shelterList = document.getElementById('shelter-list');
    if (!shelterList) return;
    const alerts = JSON.parse(localStorage.getItem('alerts') || '[]');

    shelterList.innerHTML = shelters.map(shelter => {
       // デバッグ用ログ：現在地と避難所の座標
       console.log(
         `DEBUG shelter ${shelter.id} coords:`,
         'userLocation=', userLocation,
         ' shelterLatLon=', shelter.latitude, shelter.longitude
       );
        const occupancyPercent = (shelter.current_occupancy / shelter.capacity) * 100;
        const isWarning = occupancyPercent >= 80;
        const favorites = JSON.parse(localStorage.getItem('favorites') || '[]');
        const isFavorited = favorites.includes(shelter.id);

        // ここから距離計算ロジック
        let distanceText = '不明';
        if (userLocation) {
           // デバッグ用ログ：calculateDistanceKm の生データ
           const rawKm = calculateDistanceKm(userLocation, [shelter.latitude, shelter.longitude]);
           console.log(`DEBUG raw distance (km):`, rawKm);
            // calculateDistanceKm は数値（km）を返す関数です
            const km = calculateDistanceKm(
                userLocation,
                [shelter.latitude, shelter.longitude]
            );
            console.log(`shelter ${shelter.id} 距離 raw km=`, km);
            distanceText = `${km.toFixed(1)}km`;
        }

        const tags = [];
        if (shelter.attributes.pets_allowed)    tags.push('ペット可');
        if (shelter.attributes.barrier_free)     tags.push('バリアフリー');
        if (shelter.attributes.toilet_available) tags.push('トイレ');
        if (shelter.attributes.food_available)   tags.push('食料');
        if (shelter.attributes.medical_available)tags.push('医療');
        if (shelter.attributes.wifi_available)   tags.push('Wi-Fi');
        if (shelter.attributes.charging_available) tags.push('充電');
        const areaAlerts = alerts
            .filter(a => shelter.address.includes(a.area))
            .map(a => a.warning_type);
        if (areaAlerts.length) tags.push(...areaAlerts.map(a => `警報: ${a}`));

        return `
            <div class="shelter" data-id="${shelter.id}">
                <h4>${shelter.name}</h4>
                <p>住所: ${shelter.address}</p>
                <p>定員: ${shelter.capacity}人</p>
                <p>現在人数: ${shelter.current_occupancy}人 (${occupancyPercent.toFixed(1)}%)</p>
                <p>距離: ${distanceText}</p>
                <div class="occupancy-bar">
                    <div class="occupancy-fill ${isWarning ? 'warning' : ''}"
                         style="width: ${occupancyPercent}%"></div>
                </div>
                <canvas id="chart-${shelter.id}" height="50"></canvas>
                <div class="tags">
                    ${tags.map(tag => `<span class="tag">${tag}</span>`).join('')}
                </div>
                <p>状態: ${shelter.status === 'open' ? '開設中' : '閉鎖'}</p>
                ${shelter.photos.length
                    ? `<div>${shelter.photos.map(p => `<img src="${p}" class="photo-preview">`).join('')}</div>`
                    : ''
                }
                <button class="favorite-btn ${isFavorited ? 'favorited' : ''}"
                        onclick="toggleFavorite(${shelter.id})">
                    ${isFavorited ? '★ お気に入り解除' : '☆ お気に入り登録'}
                </button>
                <button onclick="showDetails(${shelter.id})">詳細</button>
                <a href="https://www.google.com/maps/dir/?api=1&destination=${shelter.latitude},${shelter.longitude}"
                   target="_blank">ルート案内</a>
            </div>
        `;
    }).join('');

    // 既存のチャート描画ロジックもそのまま動きます
    shelters.forEach(shelter => {
        const ctx = document.getElementById(`chart-${shelter.id}`);
        if (ctx) {
            new Chart(ctx.getContext('2d'), {
                type: 'bar',
                data: {
                    labels: ['空き状況'],
                    datasets: [{
                        label: '利用人数',
                        data: [shelter.current_occupancy],
                        backgroundColor:
                            shelter.current_occupancy / shelter.capacity >= 0.8
                                ? '#dc3545'
                                : '#28a745'
                    }, {
                        label: '定員',
                        data: [shelter.capacity],
                        backgroundColor: '#e0e0e0'
                    }]
                },
                options: {
                    indexAxis: 'y',
                    scales: { x: { max: shelter.capacity } }
                }
            });
        }
    });
}


function updateAdminShelterList(shelters) {
    const shelterList = document.getElementById('admin-shelter-list');
    if (!shelterList) return;
    shelterList.innerHTML = shelters.map(shelter => `
        <div class="shelter" data-id="${shelter.id}">
            <input type="checkbox" class="shelter-checkbox" value="${shelter.id}">
            <h4>${shelter.name}</h4>
            <form class="edit-shelter-form">
                <input type="hidden" name="id" value="${shelter.id}">
                <div class="card">
                    <div class="card-header">基本情報</div>
                    <div class="card-body">
                        <label>名前: <input type="text" name="name" value="${shelter.name}"></label><br>
                        <label>住所: <input type="text" name="address" value="${shelter.address}" onblur="updateAdminMapPin(${shelter.id}, this.value)"></label><br>
                        <input type="hidden" name="latitude" value="${shelter.latitude}">
                        <input type="hidden" name="longitude" value="${shelter.longitude}">
                        <label>定員: <input type="number" name="capacity" value="${shelter.capacity}"></label><br>
                        <label>現在利用人数: <input type="number" name="current_occupancy" value="${shelter.current_occupancy}"></label><br>
                    </div>
                </div>
                <div class="card">
                    <div class="card-header">施設属性</div>
                    <div class="card-body">
                        <label><input type="checkbox" name="pets_allowed" ${shelter.pets_allowed ? 'checked' : ''}> ペット可</label><br>
                        <label><input type="checkbox" name="barrier_free" ${shelter.barrier_free ? 'checked' : ''}> バリアフリー</label><br>
                        <label><input type="checkbox" name="toilet_available" ${shelter.toilet_available ? 'checked' : ''}> トイレ</label><br>
                        <label><input type="checkbox" name="food_available" ${shelter.food_available ? 'checked' : ''}> 食料提供</label><br>
                        <label><input type="checkbox" name="medical_available" ${shelter.medical_available ? 'checked' : ''}> 医療対応</label><br>
                        <label><input type="checkbox" name="wifi_available" ${shelter.wifi_available ? 'checked' : ''}> Wi-Fi</label><br>
                        <label><input type="checkbox" name="charging_available" ${shelter.charging_available ? 'checked' : ''}> 充電設備</label><br>
                    </div>
                </div>
                <div class="card">
                    <div class="card-header">運営情報</div>
                    <div class="card-body">
                        <label>連絡先: <input type="text" name="contact" value="${shelter.contact}"></label><br>
                        <label>運営団体: <input type="text" name="operator" value="${shelter.operator}"></label><br>
                        <label>開設日時: <input type="datetime-local" name="opened_at" value="${new Date(shelter.opened_at).toISOString().slice(0,16)}"></label><br>
                        <label>状態: 
                            <select name="status">
                                <option value="open" ${shelter.status === 'open' ? 'selected' : ''}>開設中</option>
                                <option value="closed" ${shelter.status === 'closed' ? 'selected' : ''}>閉鎖</option>
                            </select>
                        </label><br>
                    </div>
                </div>
                <div class="card">
                    <div class="card-header">写真</div>
                    <div class="card-body">
                        <input type="file" name="photo" accept="image/*">
                        ${shelter.photos.length ? `<div>${shelter.photos.map(p => `<img src="${p}" class="photo-preview">`).join('')}</div>` : ''}
                    </div>
                </div>
                <button type="submit">更新</button>
                <button type="button" class="delete-shelter">削除</button>
            </form>
<div class="mb-3">
  <label for="filter-distance" class="form-label">表示範囲:</label>
  <select id="filter-distance"
          class="form-select form-select-sm d-inline-block w-auto ms-2"
          onchange="fetchShelters()">
    <option value="0">全て表示</option>
    <option value="5">5km以内</option>
    <option value="10">10km以内</option>
    <option value="20">20km以内</option>
  </select>
</div>
        </div>
    `).join('');
}

async function fetchAlerts() {
    try {
        const response = await fetch('/api/disaster-alerts');
        const alerts = await response.json();
        localStorage.setItem('alerts', JSON.stringify(alerts));
        updateAlertSection(alerts);
        updateMapAlerts(alerts);
    } catch (e) {
        console.error('fetchAlertsエラー:', e);
        updateAlertSection([]);
    }
}

function updateAlertSection(alerts) {
    const alertSection = document.getElementById('alert-section');
    if (!alertSection) return;
    alertSection.innerHTML = alerts.length ? alerts.map(alert => `
        <div class="alert-item ${alert.level.toLowerCase()}">
            ${alert.area}: ${alert.warning_type} - ${alert.description} (発行: ${new Date(alert.issued_at).toLocaleString()})
        </div>
    `).join('') : '<p>警報はありません</p>';
}

function initMap() {
  // 1) map コンテナを Leaflet に紐づけて初期表示
  map = L.map('map').setView([35.6762, 139.6503], 10);

  // 2) ← ここが必須！OpenStreetMap のタイルレイヤーを追加
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors',
    maxZoom: 18
  }).addTo(map);

  // 既存の Geolocation → 避難所フェッチ処理
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      position => {
        userLocation = [position.coords.latitude, position.coords.longitude];
        L.marker(userLocation, { icon: L.divIcon({ className: 'user-icon' }) })
          .addTo(map)
          .bindPopup('現在地').openPopup();
        map.setView(userLocation, 12);
        console.log('現在地設定:', userLocation);
        fetchShelters();
        fetchAlerts();
      },
      error => {
        console.warn('位置情報取得失敗:', error.message);
        fetchShelters();
        fetchAlerts();
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 0
      }
    );
  } else {
    console.warn('Geolocation非対応');
    fetchShelters();
    fetchAlerts();
  }
}


function initAdminMap() {
    try {
        console.log('initAdminMap開始');
        adminMap = L.map('admin-map').setView([35.6762, 139.6503], 10);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap'
        }).addTo(adminMap);
        console.log('管理者タイルレイヤー追加');
        fetchShelters();
    } catch (e) {
        console.error('initAdminMapエラー:', e);
    }
}

function updateMap(shelters) {
    try {
        console.log('updateMap開始', shelters.length);
        markers.forEach(marker => map.removeLayer(marker));
        markers = [];
        const alerts = JSON.parse(localStorage.getItem('alerts') || '[]');
        shelters.forEach(shelter => {
        let distText = '不明';
        if (userLocation) {
          const d = calculateDistanceKm(userLocation, [shelter.latitude, shelter.longitude]);
          distText = d.toFixed(1) + 'km';
        }
            const areaAlerts = alerts.filter(a => shelter.address.includes(a.area)).map(a => a.warning_type).join(', ');
            const popup = `<b>${shelter.name}</b><br>住所: ${shelter.address}<br>距離: ${distText}<br>警報: ${areaAlerts || 'なし'}`;
            const marker = L.marker([shelter.latitude, shelter.longitude], {
                icon: L.divIcon({ className: 'shelter-icon' })
            }).addTo(map);
            marker.on('click', () => showDetails(shelter.id));
            marker.bindPopup(popup);
            markers.push(marker);
        });
        if (shelters.length && userLocation) {
            const bounds = L.latLngBounds(shelters.map(s => [s.latitude, s.longitude]).concat([userLocation]));
            map.fitBounds(bounds, { padding: [50, 50] });
        }
        console.log('マーカー更新完了');
    } catch (e) {
        console.error('updateMapエラー:', e);
    }
}

function updateAdminMap(shelters) {
    try {
        console.log('updateAdminMap開始', shelters.length);
        adminMarkers.forEach(marker => adminMap.removeLayer(marker));
        adminMarkers = [];
        shelters.forEach(shelter => {
            const marker = L.marker([shelter.latitude, shelter.longitude], {
                icon: L.divIcon({ className: 'shelter-icon' })
            }).addTo(adminMap);
            marker.bindPopup(`<b>${shelter.name}</b><br>住所: ${shelter.address}`);
            adminMarkers.push(marker);
        });
        if (shelters.length) {
            const bounds = L.latLngBounds(shelters.map(s => [s.latitude, s.longitude]));
            adminMap.fitBounds(bounds, { padding: [50, 50] });
        }
        console.log('管理者マーカー更新完了');
    } catch (e) {
        console.error('updateAdminMapエラー:', e);
    }
}

async function updateAdminMapPin(shelterId, address) {
    try {
        const response = await fetch(`https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(address)}&format=json`);
        const data = await response.json();
        if (data.length) {
            const lat = parseFloat(data[0].lat);
            const lon = parseFloat(data[0].lon);
            const form = document.querySelector(`.shelter[data-id="${shelterId}"] .edit-shelter-form`);
            form.latitude.value = lat;
            form.longitude.value = lon;
            adminMarkers.forEach(marker => adminMap.removeLayer(marker));
            adminMarkers = [];
            const marker = L.marker([lat, lon], {
                icon: L.divIcon({ className: 'shelter-icon' })
            }).addTo(adminMap);
            marker.bindPopup(`住所: ${address}`);
            adminMarkers.push(marker);
            adminMap.setView([lat, lon], 12);
        }
    } catch (e) {
        console.error('updateAdminMapPinエラー:', e);
    }
}

function updateMapAlerts(alerts) {
    alertPolygons.forEach(polygon => map.removeLayer(polygon));
    alertPolygons = [];
    alerts.forEach(alert => {
        if (alert.bounds && alert.bounds[0][0] !== alert.bounds[1][0]) {
            const color = alert.level === '特別警報' ? '#9b1d64' : alert.level === '警報' ? '#dc3545' : '#ffc107';
            const polygon = L.rectangle(alert.bounds, {
                color: color,
                fillOpacity: 0.2,
                weight: 2
            }).addTo(map);
            polygon.bindPopup(`${alert.area}: ${alert.warning_type}`);
            alertPolygons.push(polygon);
        }
    });
}

function calculateDistanceKm(coord1, coord2) {
    const [lat1, lon1] = coord1;
    const [lat2, lon2] = coord2;
    const R = 6371;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat/2) * Math.sin(dLat/2)
            + Math.cos(lat1 * Math.PI/180) * Math.cos(lat2 * Math.PI/180)
            * Math.sin(dLon/2) * Math.sin(dLon/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
}

function calculateDistance(coord1, coord2) {
    const [lat1, lon1] = coord1;
    const [lat2, lon2] = coord2;
    const R = 6371;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
              Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
              Math.sin(dLon/2) * Math.sin(dLon/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    return (R * c).toFixed(1) + 'km';
}

async function showDetails(shelterId) {
    try {
        const response = await fetch(`/api/shelters`);
        const shelters = await response.json();
        const shelter = shelters.find(s => s.id === shelterId);
        if (!shelter) return;
        const alerts = JSON.parse(localStorage.getItem('alerts') || '[]');
        const areaAlerts = alerts.filter(a => shelter.address.includes(a.area)).map(a => a.warning_type).join(', ');
        document.getElementById('modal-content').innerHTML = `
            <h4>${shelter.name}</h4>
            <p>住所: ${shelter.address}</p>
            <p>連絡先: ${shelter.contact || 'なし'}</p>
            <p>運営団体: ${shelter.operator || 'なし'}</p>
            <p>開設日時: ${new Date(shelter.opened_at).toLocaleString()}</p>
            <p>空き状況: ${shelter.current_occupancy}/${shelter.capacity}</p>
            <p>警報: ${areaAlerts || 'なし'}</p>
            <p>状態: ${shelter.status === 'open' ? '開設中' : '閉鎖'}</p>
            ${shelter.photos.length ? `<div>${shelter.photos.map(p => `<img src="${p}" class="photo-preview">`).join('')}</div>` : ''}
        `;
        const modal = new bootstrap.Modal(document.getElementById('details-modal'));
        modal.show();
    } catch (e) {
        console.error('showDetailsエラー:', e);
    }
}

function toggleFavorite(shelterId) {
    let favorites = JSON.parse(localStorage.getItem('favorites') || '[]');
    if (favorites.includes(shelterId)) {
        favorites = favorites.filter(id => id !== shelterId);
        document.querySelector(`.shelter[data-id="${shelterId}"] .favorite-btn`).classList.remove('favorited');
        document.querySelector(`.shelter[data-id="${shelterId}"] .favorite-btn`).textContent = '☆ お気に入り登録';
    } else {
        favorites.push(shelterId);
        document.querySelector(`.shelter[data-id="${shelterId}"] .favorite-btn`).classList.add('favorited');
        document.querySelector(`.shelter[data-id="${shelterId}"] .favorite-btn`).textContent = '★ お気に入り解除';
    }
    localStorage.setItem('favorites', JSON.stringify(favorites));
}