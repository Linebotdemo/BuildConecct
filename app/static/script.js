const YAHOO_APPID = "dj00aiZpPWoyQVc5RXVkQWhXQyZzPWNvbnN1bWVyc2VjcmV0Jng9YTE-";

let map, userLocation, markers = [], alertPolygons = [], adminMap, adminMarkers = [];

/**
 * Yahoo ジオコーディング API で住所を緯度経度に変換
 */
async function geocodeWithYahoo(address) {
  try {
    if (!address) throw new Error("住所が空です");
    const url = new URL("https://map.yahooapis.jp/geocode/V1/geoCoder");
    url.searchParams.set("appid", YAHOO_APPID);
    url.searchParams.set("query", address);
    url.searchParams.set("output", "json");

    const res = await fetch(url);
    if (!res.ok) throw new Error(`Yahoo Geocode API error: ${res.status}`);
    const j = await res.json();
    if (!j.Feature?.length) throw new Error("住所が見つかりません");
    const [lon, lat] = j.Feature[0].Geometry.Coordinates.split(",").map(parseFloat);
    if (isNaN(lat) || isNaN(lon)) throw new Error("無効な座標");
    console.log("[geocodeWithYahoo] Success:", { address, lat, lon });
    return [lat, lon];
  } catch (e) {
    console.error("[geocodeWithYahoo] Error:", e.message);
    throw e;
  }
}

/**
 * 避難所を取得
 */
async function fetchShelters() {
  try {
    const search = document.getElementById("search")?.value || "";
    const status = document.getElementById("filter-status")?.value || "";
    const maxDist = parseFloat(document.getElementById("filter-distance")?.value || "0");
    const form = document.getElementById("filter-form");
    const params = new URLSearchParams();

    if (search) params.append("search", search);
    if (status) params.append("status", status);
    if (maxDist > 0 && userLocation) {
      params.append("distance", maxDist);
      params.append("latitude", userLocation[0]);
      params.append("longitude", userLocation[1]);
    }

    const attributes = [
      "pets_allowed",
      "barrier_free",
      "toilet_available",
      "food_available",
      "medical_available",
      "wifi_available",
      "charging_available",
    ];
    attributes.forEach((name) => {
      if (form?.elements[name]?.checked) params.append(name, "true");
    });

    console.log("[fetchShelters] Query:", params.toString());
    const token = localStorage.getItem("auth_token") || "";
    const res = await fetch(`/api/shelters?${params}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      if (res.status === 401) {
        console.warn("[fetchShelters] Unauthorized, redirecting to login");
        window.location.href = "/login";
      }
      throw new Error(`API error: ${res.status}`);
    }
    const shelters = await res.json() || [];
    console.log("[fetchShelters] Shelters:", shelters.length, shelters[0]);
    updateShelterList(shelters);
    updateMap(shelters);
    updateAdminShelterList(shelters); // 管理者リストも更新
    updateAdminMap(shelters); // 管理者マップも更新
  } catch (e) {
    console.error("[fetchShelters] Error:", e.message);
    updateShelterList([]);
    updateMap([]);
    updateAdminShelterList([]);
    updateAdminMap([]);
  }
}

/**
 * 避難所リストを描画
 */
function updateShelterList(shelters) {
  const container = document.getElementById("shelter-list");
  if (!container) {
    console.error("[updateShelterList] #shelter-list not found");
    return;
  }

  const attributeLabels = {
    pets_allowed: { label: "ペット可", icon: "🐾" },
    barrier_free: { label: "バリアフリー", icon: "♿" },
    toilet_available: { label: "トイレ", icon: "🚻" },
    food_available: { label: "食料", icon: "🍽️" },
    medical_available: { label: "医療", icon: "🏥" },
    wifi_available: { label: "Wi-Fi", icon: "📶" },
    charging_available: { label: "充電", icon: "🔌" },
  };

  container.innerHTML = shelters
    .map((shelter) => {
      const pct = shelter.capacity ? (shelter.current_occupancy / shelter.capacity) * 100 : 0;
      const isWarn = pct >= 80;
      const favs = JSON.parse(localStorage.getItem("favorites") || "[]");
      const isFavorited = favs.includes(shelter.id);

      let distanceText = "";
      if (userLocation && shelter.latitude && shelter.longitude) {
        const km = calculateDistanceKm(userLocation, [shelter.latitude, shelter.longitude]);
        distanceText = `${km.toFixed(1)}km`;
        console.log("[updateShelterList] Distance for", shelter.id, distanceText);
      }

const tags = Object.keys(attributeLabels)
  // shelter.attributes[key] が truthy（true, 1, "true" など）なら絞り込む
  .filter((key) => shelter.attributes && shelter.attributes[key])
  .map(
    (key) =>
      `<span class="badge bg-info me-1">${attributeLabels[key].icon} ${attributeLabels[key].label}</span>`
  );

// 属性が一つもなければ「属性なし」タグを追加
if (tags.length === 0) {
  tags.push(`<span class="badge bg-secondary">属性なし</span>`);
}

console.log(
  "shelter.id:", shelter.id,
  "attributes:", shelter.attributes,
  "tags:", tags
);


if (tags.length === 0) {
  tags.push(`<span class="badge bg-secondary">属性なし</span>`);
}
      console.log("[updateShelterList] Tags for", shelter.id, tags);

      return `
        <div class="shelter card mb-3 p-3" data-id="${shelter.id}">
          <h4>${shelter.name || "名称不明"}</h4>
          <p>住所: ${shelter.address || "―"}</p>
          <p>連絡先: ${shelter.contact || "―"}</p>
          <p>運営団体: ${shelter.operator || "―"}</p>
          <p>状態: ${shelter.status === "open" ? "開設中" : "閉鎖"}</p>
          <p>定員: ${shelter.capacity || 0}人</p>
          <p>現在: ${shelter.current_occupancy || 0}人 (${pct.toFixed(1)}%)</p>
          ${distanceText ? `<p>距離: ${distanceText}</p>` : ""}
          <div class="tags mb-2">${tags.join("")}</div>
          <div class="occupancy-bar mb-2">
            <div class="occupancy-fill ${isWarn ? "warning" : ""}" style="width:${pct}%;"></div>
          </div>
          <canvas id="chart-${shelter.id}" height="50"></canvas>
          ${
            shelter.photos?.length
              ? `<div class="photo-gallery mb-2">${shelter.photos
                  .map(
                    (p) =>
                      `<img src="${p}" class="photo-preview me-1 rounded" style="width:100px;cursor:pointer;" alt="サムネイル" onerror="this.src='/static/placeholder.jpg'">`
                  )
                  .join("")}</div>`
              : ""
          }
          <button class="favorite-btn btn btn-outline-secondary me-1 ${
            isFavorited ? "favorited" : ""
          }" onclick="toggleFavorite(${shelter.id})">
            ${isFavorited ? "★ お気に入り解除" : "☆ お気に入り登録"}
          </button>
          <a href="https://www.google.com/maps/dir/?api=1&destination=${shelter.latitude || 0},${
            shelter.longitude || 0
          }" target="_blank" class="btn btn-outline-success">
            ルート案内
          </a>
        </div>
      `;
    })
    .join("");

  shelters.forEach((shelter) => {
    const ctx = document.getElementById(`chart-${shelter.id}`);
    if (ctx) {
      try {
        new Chart(ctx.getContext("2d"), {
          type: "bar",
          data: {
            labels: ["空き状況"],
            datasets: [
              {
                label: "利用人数",
                data: [shelter.current_occupancy || 0],
                backgroundColor: (shelter.current_occupancy || 0) / (shelter.capacity || 1) >= 0.8 ? "#dc3545" : "#28a745",
              },
              {
                label: "定員",
                data: [shelter.capacity || 0],
                backgroundColor: "#e0e0e0",
              },
            ],
          },
          options: {
            indexAxis: "y",
            scales: { x: { max: shelter.capacity || 100 } },
            plugins: { legend: { display: false } },
          },
        });
      } catch (e) {
        console.error("[updateShelterList] Chart error:", e.message);
      }
    }
  });
}

/**
 * マップにピンを表示
 */
function updateMap(shelters) {
  try {
    if (!map) {
      console.error("[updateMap] Map not initialized");
      return;
    }
    markers.forEach((m) => map.removeLayer(m));
    markers = [];

    shelters.forEach((shelter) => {
      if (!shelter.latitude || !shelter.longitude) {
        console.warn(`[updateMap] Invalid coords for shelter ${shelter.id}`);
        return;
      }
      const marker = L.marker([shelter.latitude, shelter.longitude], {
        icon: L.divIcon({
          className: `shelter-icon ${shelter.status === "open" ? "open" : "closed"}`,
          html: shelter.current_occupancy / shelter.capacity >= 0.8 ? "🔴" : "🟢",
        }),
      })
        .addTo(map)
        .bindPopup(`
          <b>${shelter.name || "不明"}</b><br>
          住所: ${shelter.address || "―"}<br>
          状態: ${shelter.status === "open" ? "開設中" : "閉鎖"}<br>
          現在人数: ${shelter.current_occupancy || 0}/${shelter.capacity || 0}人
        `);
      marker.on("click", () => showDetails(shelter.id));
      markers.push(marker);
    });

    if (shelters.length && userLocation) {
      const bounds = L.latLngBounds(
        shelters
          .filter((s) => s.latitude && s.longitude)
          .map((s) => [s.latitude, s.longitude])
          .concat([userLocation])
      );
      map.fitBounds(bounds, { padding: [40, 40] });
    }
    console.log("[updateMap] Markers:", markers.length);
  } catch (e) {
    console.error("[updateMap] Error:", e.message);
  }
}

/**
 * 管理者用マップ初期化
 */
function initAdminMap() {
  try {
    console.log("[initAdminMap] Starting");
    const adminMapContainer = document.getElementById("admin-map");
    if (!adminMapContainer) {
      console.warn("[initAdminMap] #admin-map not found");
      return;
    }
    adminMap = L.map("admin-map").setView([35.6762, 139.6503], 10);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap",
      maxZoom: 18,
    }).addTo(adminMap);
    console.log("[initAdminMap] Tile layer added");
    fetchShelters();
  } catch (e) {
    console.error("[initAdminMap] Error:", e.message);
  }
}

/**
 * 管理者用ピン表示
 */
function updateAdminMap(shelters) {
  try {
    console.log("[updateAdminMap] Starting:", shelters.length);
    if (!adminMap) {
      console.warn("[updateAdminMap] Admin map not initialized");
      return;
    }
    adminMarkers.forEach((m) => adminMap.removeLayer(m));
    adminMarkers = [];

    shelters.forEach((shelter) => {
      if (!shelter.latitude || !shelter.longitude) {
        console.warn(`[updateAdminMap] Invalid coords for shelter ${shelter.id}`);
        return;
      }
      const marker = L.marker([shelter.latitude, shelter.longitude], {
        icon: L.divIcon({
          className: `shelter-icon ${shelter.status === "open" ? "open" : "closed"}`,
          html: shelter.current_occupancy / shelter.capacity >= 0.8 ? "🔴" : "🟢",
        }),
      })
        .addTo(adminMap)
        .bindPopup(`
          <b>${shelter.name || "不明"}</b><br>
          住所: ${shelter.address || "―"}<br>
          状態: ${shelter.status === "open" ? "開設中" : "閉鎖"}<br>
          現在人数: ${shelter.current_occupancy || 0}/${shelter.capacity || 0}人
        `);
      adminMarkers.push(marker);
    });

    if (shelters.length) {
      const bounds = L.latLngBounds(
        shelters
          .filter((s) => s.latitude && s.longitude)
          .map((s) => [s.latitude, s.longitude])
      );
      adminMap.fitBounds(bounds, { padding: [50, 50] });
    }
    console.log("[updateAdminMap] Markers:", adminMarkers.length);
  } catch (e) {
    console.error("[updateAdminMap] Error:", e.message);
  }
}

/**
 * 管理者用ピン更新
 */
async function updateAdminMapPin(shelterId, address) {
  try {
    const [lat, lon] = await geocodeWithYahoo(address);
    const form = document.querySelector(`.shelter[data-id="${shelterId}"] .edit-shelter-form`);
    if (form) {
      form.latitude.value = lat;
      form.longitude.value = lon;
    }
    if (!adminMap) {
      console.warn("[updateAdminMapPin] Admin map not initialized");
      return;
    }
    adminMarkers.forEach((m) => adminMap.removeLayer(m));
    adminMarkers = [];
    const marker = L.marker([lat, lon], {
      icon: L.divIcon({ className: "shelter-icon" }),
    })
      .addTo(adminMap)
      .bindPopup(`住所: ${address}`);
    adminMarkers.push(marker);
    adminMap.setView([lat, lon], 12);
    console.log("[updateAdminMapPin] Updated:", { shelterId, lat, lon });
  } catch (e) {
    console.error("[updateAdminMapPin] Error:", e.message);
  }
}

/**
 * 警報を取得
 */
async function fetchAlerts() {
  let hadError = false;
  let alerts = [];

  if (!userLocation) {
    hadError = true;
    updateAlertSection([], true);
    updateMapAlerts([]);
    console.log("[fetchAlerts] No userLocation");
    return;
  }

  const urlJMA = "https://www.jma.go.jp/bosai/hazard/data/warning/00.json";
  const proxyUrl = `/api/proxy?url=${encodeURIComponent(urlJMA)}`;
  console.log("[fetchAlerts] Proxy URL:", proxyUrl);

  try {
    const res = await fetch(proxyUrl);
    if (!res.ok) throw new Error(`JMA API error: ${res.status}`);
    const jsonData = await res.json();
    console.log("[fetchAlerts] JSON keys:", Object.keys(jsonData));

    const areas = (jsonData.areaTypes || []).flatMap((t) => t.areas || []);
    console.log("[fetchAlerts] Areas:", areas.length);

    areas.forEach((area) => {
      if (!area.polygon || !area.warnings) return;
      const bounds = L.latLngBounds(area.polygon);
      if (!bounds.contains(L.latLng(userLocation))) return;
      area.warnings
        .filter((w) => w.status !== "解除")
        .forEach((w) => {
          alerts.push({
            area: area.name,
            warning_type: w.kind.name,
            description: w.kind.name,
            issued_at: w.issued,
            level: w.kind.name.includes("特別") ? "特別警報" : w.kind.name.includes("警報") ? "警報" : "注意報",
            polygon: area.polygon,
          });
        });
    });

    console.log("[fetchAlerts] Alerts:", alerts.length);
    localStorage.setItem("alerts", JSON.stringify(alerts));
  } catch (e) {
    hadError = true;
    console.error("[fetchAlerts] Error:", e.message);
    updateAlertSection([], true);
    updateMapAlerts([]);
  }

  updateAlertSection(alerts, hadError);
  updateMapAlerts(hadError ? [] : alerts);
}

/**
 * 警報セクション更新
 */
function updateAlertSection(alerts, hadError = false) {
  const elem = document.getElementById("alert-section");
  if (!elem) {
    console.error("[updateAlertSection] #alert-section not found");
    return;
  }

  if (hadError) {
    elem.innerHTML = '<p class="alert-error">⚠️ 警報情報の取得に失敗しました。</p>';
    return;
  }

  if (!alerts.length) {
    elem.innerHTML = '<p class="alert-none">📭 現在、警報はありません。</p>';
    return;
  }

  elem.innerHTML = alerts
    .map((a) => {
      const issued = new Date(a.issued_at).toLocaleString("ja-JP", {
        year: "numeric",
        month: "long",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
      return `
      <div class="alert-item ${a.level.toLowerCase()}">
        <strong>${a.area}: ${a.warning_type}</strong><br>
        ${a.description}<br>
        <small>発行: ${issued}</small>
      </div>
    `;
    })
    .join("");
}

/**
 * マップに警報ポリゴン表示
 */
function updateMapAlerts(alerts) {
  try {
    alertPolygons.forEach((p) => map.removeLayer(p));
    alertPolygons = [];

    alerts.forEach((a) => {
      if (!a.polygon) return;
      const color = a.level === "特別警報" ? "#9b1d64" : a.level === "警報" ? "#dc3545" : "#ffc107";
      const poly = L.polygon(a.polygon, {
        color,
        fillOpacity: 0.2,
        weight: 2,
      }).addTo(map);
      const issued = new Date(a.issued_at).toLocaleString("ja-JP", {
        year: "numeric",
        month: "long",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
      poly.bindPopup(`<strong>${a.area}: ${a.warning_type}</strong><br>発行: ${issued}`);
      alertPolygons.push(poly);
    });
    console.log("[updateMapAlerts] Polygons:", alertPolygons.length);
  } catch (e) {
    console.error("[updateMapAlerts] Error:", e.message);
  }
}

/**
 * 管理者用リスト更新
 */
function updateAdminShelterList(shelters) {
  const shelterList = document.getElementById("admin-shelter-list");
  if (!shelterList) {
    console.log("[updateAdminShelterList] #admin-shelter-list not found");
    return;
  }

  shelterList.innerHTML = shelters
    .map((shelter) => `
        <div class="shelter" data-id="${shelter.id}">
            <input type="checkbox" class="shelter-checkbox" value="${shelter.id}">
            <h4>${shelter.name || "不明"}</h4>
            <form class="edit-shelter-form" onsubmit="updateShelter(event, ${shelter.id})">
                <input type="hidden" name="id" value="${shelter.id}">
                <div class="card">
                    <div class="card-header">基本情報</div>
                    <div class="card-body">
                        <label>名前: <input type="text" name="name" value="${shelter.name || ''}" required></label><br>
                        <label>住所: <input type="text" name="address" value="${
                          shelter.address || ''
                        }" onblur="updateAdminMapPin(${shelter.id}, this.value)" required></label><br>
                        <input type="hidden" name="latitude" value="${shelter.latitude || 0}">
                        <input type="hidden" name="longitude" value="${shelter.longitude || 0}">
                        <label>定員: <input type="number" name="capacity" value="${
                          shelter.capacity || 0
                        }" min="0" required></label><br>
                        <label>現在利用人数: <input type="number" name="current_occupancy" value="${
                          shelter.current_occupancy || 0
                        }" min="0"></label><br>
                    </div>
                </div>
                <div class="card">
                    <div class="card-header">施設属性</div>
                    <div class="card-body">
                        <label><input type="checkbox" name="pets_allowed" ${
                          shelter.attributes?.pets_allowed ? "checked" : ""
                        }> ペット可</label><br>
                        <label><input type="checkbox" name="barrier_free" ${
                          shelter.attributes?.barrier_free ? "checked" : ""
                        }> バリアフリー</label><br>
                        <label><input type="checkbox" name="toilet_available" ${
                          shelter.attributes?.toilet_available ? "checked" : ""
                        }> トイレ</label><br>
                        <label><input type="checkbox" name="food_available" ${
                          shelter.attributes?.food_available ? "checked" : ""
                        }> 食料提供</label><br>
                        <label><input type="checkbox" name="medical_available" ${
                          shelter.attributes?.medical_available ? "checked" : ""
                        }> 医療対応</label><br>
                        <label><input type="checkbox" name="wifi_available" ${
                          shelter.attributes?.wifi_available ? "checked" : ""
                        }> Wi-Fi</label><br>
                        <label><input type="checkbox" name="charging_available" ${
                          shelter.attributes?.charging_available ? "checked" : ""
                        }> 充電設備</label><br>
                    </div>
                </div>
                <div class="card">
                    <div class="card-header">運営情報</div>
                    <div class="card-body">
                        <label>連絡先: <input type="text" name="contact" value="${
                          shelter.contact || ""
                        }"></label><br>
                        <label>運営団体: <input type="text" name="operator" value="${
                          shelter.operator || ""
                        }"></label><br>
                        <label>開設日時: <input type="datetime-local" name="opened_at" value="${
                          shelter.opened_at ? new Date(shelter.opened_at).toISOString().slice(0, 16) : ""
                        }"></label><br>
                        <label>状態: 
                            <select name="status" required>
                                <option value="open" ${
                                  shelter.status === "open" ? "selected" : ""
                                }>開設中</option>
                                <option value="closed" ${
                                  shelter.status === "closed" ? "selected" : ""
                                }>閉鎖</option>
                            </select>
                        </label><br>
                    </div>
                </div>
                <div class="card">
                    <div class="card-header">写真</div>
                    <div class="card-body">
                        <input type="file" name="photo" accept="image/*" multiple>
                        ${
                          shelter.photos?.length
                            ? `<div class="photo-gallery">${shelter.photos
                                .map(
                                  (p) =>
                                    `<img src="${p}" class="photo-preview" alt="サムネイル" onerror="this.src='/static/placeholder.jpg'">`
                                )
                                .join("")}</div>`
                            : "<p>写真なし</p>"
                        }
                    </div>
                </div>
                <button type="submit" class="btn btn-primary">更新</button>
            </form>
        </div>
    `)
    .join("");
}

/**
 * 避難所更新（管理者用）
 */
async function updateShelter(event, shelterId) {
  event.preventDefault();
  try {
    const form = event.target;
    const formData = new FormData(form);
    const token = localStorage.getItem("auth_token") || "";
    
    // 属性を収集
    const attributes = {
      pets_allowed: formData.get("pets_allowed") === "on",
      barrier_free: formData.get("barrier_free") === "on",
      toilet_available: formData.get("toilet_available") === "on",
      food_available: formData.get("food_available") === "on",
      medical_available: formData.get("medical_available") === "on",
      wifi_available: formData.get("wifi_available") === "on",
      charging_available: formData.get("charging_available") === "on",
    };

    // 写真アップロード
    let photoIds = [];
    const files = formData.getAll("photo");
    if (files && files[0]?.size > 0) {
      const uploadFormData = new FormData();
      uploadFormData.append("shelter_id", shelterId);
      files.forEach((file) => uploadFormData.append("files", file));
      
      const uploadRes = await fetch("/api/shelters/upload-photos", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: uploadFormData,
      });
      if (!uploadRes.ok) throw new Error(`Photo upload failed: ${uploadRes.status}`);
      const uploadData = await uploadRes.json();
      photoIds = uploadData.ids || [];
    }

    // 避難所データ更新
    const shelterData = {
      name: formData.get("name"),
      address: formData.get("address"),
      latitude: parseFloat(formData.get("latitude")),
      longitude: parseFloat(formData.get("longitude")),
      capacity: parseInt(formData.get("capacity")),
      current_occupancy: parseInt(formData.get("current_occupancy")),
      attributes,
      contact: formData.get("contact") || null,
      operator: formData.get("operator") || null,
      opened_at: formData.get("opened_at") ? new Date(formData.get("opened_at")).toISOString() : null,
      status: formData.get("status"),
      photos: photoIds,
    };

    const res = await fetch(`/api/shelters/${shelterId}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(shelterData),
    });
    if (!res.ok) {
      if (res.status === 401) {
        window.location.href = "/login";
      }
      throw new Error(`Shelter update failed: ${res.status}`);
    }
    console.log("[updateShelter] Updated shelter:", shelterId);
    await fetchShelters();
  } catch (e) {
    console.error("[updateShelter] Error:", e.message);
    alert("避難所の更新に失敗しました。");
  }
}

/**
 * 距離計算
 */
function calculateDistanceKm(coord1, coord2) {
  try {
    const [lat1, lon1] = coord1;
    const [lat2, lon2] = coord2;
    const R = 6371; // 地球の半径（km）
    const dLat = ((lat2 - lat1) * Math.PI) / 180;
    const dLon = ((lon2 - lon1) * Math.PI) / 180;
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
  } catch (e) {
    console.error("[calculateDistanceKm] Error:", e.message);
    return 0;
  }
}

/**
 * 詳細モーダル表示
 */
async function showDetails(shelterId) {
  try {
    const token = localStorage.getItem("auth_token") || "";
    const response = await fetch(`/api/shelters`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      if (response.status === 401) {
        window.location.href = "/login";
      }
      throw new Error(`HTTP error: ${response.status}`);
    }
    const shelters = await response.json();
    const shelter = shelters.find((s) => s.id === shelterId);
    if (!shelter) {
      console.warn("[showDetails] Shelter not found:", shelterId);
      return;
    }
    const alerts = JSON.parse(localStorage.getItem("alerts") || "[]");
    const areaAlerts = alerts
      .filter((a) => shelter.address.includes(a.area))
      .map((a) => a.warning_type)
      .join(", ");

    const attributeLabels = {
      pets_allowed: "ペット可",
      barrier_free: "バリアフリー",
      toilet_available: "トイレ",
      food_available: "食料提供",
      medical_available: "医療対応",
      wifi_available: "Wi-Fi",
      charging_available: "充電設備",
    };
    const attributes = Object.entries(shelter.attributes || {})
      .filter(([_, v]) => v)
      .map(([k]) => attributeLabels[k])
      .join(", ");

    document.getElementById("modal-content").innerHTML = `
      <h4>${shelter.name || "不明"}</h4>
      <p><strong>住所:</strong> ${shelter.address || "―"}</p>
      <p><strong>連絡先:</strong> ${shelter.contact || "―"}</p>
      <p><strong>運営団体:</strong> ${shelter.operator || "―"}</p>
      <p><strong>開設日時:</strong> ${
        shelter.updated_at ? new Date(shelter.updated_at).toLocaleString("ja-JP") : "―"
      }</p>
      <p><strong>空き状況:</strong> ${shelter.current_occupancy || 0} / ${shelter.capacity || 0}人</p>
      <p><strong>設備:</strong> ${attributes || "なし"}</p>
      <p><strong>警報:</strong> ${areaAlerts || "なし"}</p>
      <p><strong>状態:</strong> ${shelter.status === "open" ? "開設中" : "閉鎖"}</p>
      ${
        shelter.photos?.length
          ? `<div class="photo-gallery">${shelter.photos
              .map(
                (p) =>
                  `<img src="${p}" class="photo-preview" alt="サムネイル" onerror="this.src='/static/placeholder.jpg'">`
              )
              .join("")}</div>`
          : "<p>写真なし</p>"
      }
    `;
    const modal = new bootstrap.Modal(document.getElementById("details-modal"));
    modal.show();
  } catch (e) {
    console.error("[showDetails] Error:", e.message);
    alert("詳細情報の取得に失敗しました。");
  }
}

/**
 * お気に入りトグル
 */
function toggleFavorite(shelterId) {
  try {
    let favorites = JSON.parse(localStorage.getItem("favorites") || []);
    const btn = document.querySelector(`.shelter[data-id="${shelterId}"] .favorite-btn`);
    if (favorites.includes(shelterId)) {
      favorites = favorites.filter((id) => id !== shelterId);
      btn.classList.remove("favorited");
      btn.textContent = "☆ お気に入り登録";
    } else {
      favorites.push(shelterId);
      btn.classList.add("favorited");
      btn.textContent = "★ お気に入り解除";
    }
    localStorage.setItem("favorites", JSON.stringify(favorites));
    console.log("[toggleFavorite] Updated favorites:", favorites);
  } catch (e) {
    console.error("[toggleFavorite] Error:", e.message);
  }
}

/**
 * マップ初期化
 */
function initMap() {
  try {
    const mapContainer = document.getElementById("map");
    if (!mapContainer) {
      console.error("[initMap] #map not found");
      return;
    }

    map = L.map("map").setView([35.6762, 139.6503], 10);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap contributors",
      maxZoom: 18,
    }).addTo(map);

    console.log("[initMap] Map initialized");

    const geoButton = document.createElement("button");
    geoButton.textContent = "現在地を取得";
    geoButton.className = "btn btn-primary mb-3";
    geoButton.onclick = () => {
      if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
          async (position) => {
            userLocation = [position.coords.latitude, position.coords.longitude];
            L.marker(userLocation, {
              icon: L.divIcon({ className: "user-icon", html: "📍" }),
            })
              .addTo(map)
              .bindPopup("現在地")
              .openPopup();
            map.setView(userLocation, 12);
            console.log("[initMap] User location:", userLocation);
            fetchShelters();
            fetchAlerts();
            fetchDisasterAlerts(userLocation[0], userLocation[1]);
          },
          (error) => {
            console.warn("[initMap] Geolocation error:", error.message);
            userLocation = [35.6762, 139.6503]; // fallback
            fetchShelters();
            fetchAlerts();
          },
          {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 0,
          }
        );
      } else {
        console.warn("[initMap] Geolocation not supported");
        userLocation = [35.6762, 139.6503];
        fetchShelters();
        fetchAlerts();
      }
    };
    document.querySelector(".container").prepend(geoButton);
    geoButton.click();

    // 距離フィルターの円表示
    document.getElementById("filter-distance")?.addEventListener("change", (e) => {
      const maxDist = parseFloat(e.target.value);
      if (map._circle) map.removeLayer(map._circle);
      if (maxDist > 0 && userLocation) {
        map._circle = L.circle(userLocation, {
          radius: maxDist * 1000,
          color: "blue",
          fillOpacity: 0.1,
        }).addTo(map);
      }
    });

  } catch (e) {
    console.error("[initMap] Error:", e.message);
  }
}


async function fetchDisasterAlerts(lat, lon) {
  try {
    // 都道府県名を取得（FastAPI経由）
    const res = await fetch(`/api/reverse-geocode?lat=${lat}&lon=${lon}`);
    const data = await res.json();

    const prefecture = data.prefecture;
    if (!prefecture) {
      console.warn("[fetchDisasterAlerts] 都道府県名が取得できませんでした");
      return;
    }
    console.log("[fetchDisasterAlerts] 都道府県名:", prefecture);

    // 警報データ取得
    const alertRes = await fetch(`/api/disaster-alerts`);
    if (!alertRes.ok) {
      throw new Error(`HTTP error! status: ${alertRes.status}`);
    }

    const alerts = await alertRes.json();  // ✅ ここ1回だけ
    if (!Array.isArray(alerts)) {
      console.error("[fetchDisasterAlerts] alertsが配列ではありません", alerts);
      return;
    }

    const relevantAlerts = alerts.filter(alert =>
      alert.area.includes(prefecture)
    );

    if (relevantAlerts.length === 0) {
      console.log(`[fetchDisasterAlerts] 該当地域「${prefecture}」に警報はありません`);
    } else {
      console.log(`[fetchDisasterAlerts] 該当地域「${prefecture}」の警報`, relevantAlerts);

      alert(
        `【警報あり】${prefecture}\n` +
        relevantAlerts.map(a => `・${a.type}：${a.level}`).join("\n")
      );
    }
  } catch (err) {
    console.error("[fetchDisasterAlerts エラー]", err);
  }
}


    // 位置情報ボタン
    const geoButton = document.createElement("button");
    geoButton.textContent = "現在地を取得";
    geoButton.className = "btn btn-primary mb-3";
    geoButton.onclick = () => {
      if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
          (position) => {
            userLocation = [position.coords.latitude, position.coords.longitude];
            L.marker(userLocation, {
              icon: L.divIcon({ className: "user-icon", html: "📍" }),
            })
              .addTo(map)
              .bindPopup("現在地")
              .openPopup();
            map.setView(userLocation, 12);
            console.log("[initMap] User location:", userLocation);
            fetchShelters();
            fetchAlerts();
            fetchDisasterAlerts(userLocation[0], userLocation[1]);
          },
          (error) => {
            console.warn("[initMap] Geolocation error:", error.message);
            userLocation = [35.6762, 139.6503]; // Fallback
            fetchShelters();
            fetchAlerts();
          },
          {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 0,
          }
        );
      } else {
        console.warn("[initMap] Geolocation not supported");
        userLocation = [35.6762, 139.6503];
        fetchShelters();
        fetchAlerts();
      }
    };
    document.querySelector(".container").prepend(geoButton);
    geoButton.click();



/**
 * DOM読み込み完了時の初期化
 */
document.addEventListener("DOMContentLoaded", () => {
  initMap();
  initAdminMap();

  // 検索バー
const searchInput = document.getElementById("search");
if (!searchInput) {
  console.error("[DOMContentLoaded] #search not found");
} else {
  searchInput.addEventListener("input", () => {
    clearTimeout(searchInput.debounceTimer);
    searchInput.debounceTimer = setTimeout(fetchShelters, 300);
  });
}

const filterForm = document.getElementById("filter-form");
if (filterForm) {
  filterForm.addEventListener("change", () => {
    fetchShelters();
  });
}



  // フィルター
  ["filter-status", "filter-distance"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener("change", fetchShelters);
    } else {
      console.error(`[DOMContentLoaded] #${id} not found`);
    }
  });

  // 属性チェックボックス
  [
    "pets_allowed",
    "barrier_free",
    "toilet_available",
    "food_available",
    "medical_available",
    "wifi_available",
    "charging_available",
  ].forEach((name) => {
    document.getElementsByName(name).forEach((cb) => {
      cb.addEventListener("change", fetchShelters);
    });
  });

  // 画像クリックで拡大
  const shelterList = document.getElementById("shelter-list");
  if (shelterList) {
    shelterList.addEventListener("click", (ev) => {
      if (ev.target.classList.contains("photo-preview")) {
        const modalImg = document.getElementById("modalImg");
        if (modalImg) {
          modalImg.src = ev.target.src;
          new bootstrap.Modal(document.getElementById("imageModal")).show();
        }
      }
    });
  } else {
    console.error("[DOMContentLoaded] #shelter-list not found");
  }

  // WebSocket
  const proto = location.protocol === "https:" ? "wss://" : "ws://";
  let ws = new WebSocket(`${proto}${location.host}/ws/shelters?token=${encodeURIComponent(localStorage.getItem("auth_token") || "")}`);
  ws.onopen = () => console.log("[WebSocket] Connected");
  ws.onerror = (e) => console.error("[WebSocket] Error:", e);
  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      console.log("[WebSocket] Received:", data);
      fetchShelters(); // 最新データを取得
    } catch (err) {
      console.error("[WebSocket] Parse error:", err.message);
    }
  };
  ws.onclose = () => {
    console.log("[WebSocket] Disconnected, reconnecting...");
    setTimeout(() => {
      const reconnectWs = new WebSocket(`${proto}${location.host}/ws/shelters?token=${encodeURIComponent(localStorage.getItem("auth_token") || "")}`);
      ws = reconnectWs;
    }, 5000);
  };

  // 定期更新
  setInterval(fetchAlerts, 5 * 60 * 1000); // 5分毎
  setInterval(fetchShelters, 5 * 60 * 1000); // 5分毎
});