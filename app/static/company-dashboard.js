async function createShelter() {
    const token = localStorage.getItem('company_token');
    if (!token) {
        alert('ログインしてください');
        window.location.href = '/login';
        return;
    }
    const payload = {
        name: document.getElementById('shelter-name')?.value || "Test Shelter",
        address: document.getElementById('shelter-address')?.value || "Tokyo",
        latitude: parseFloat(document.getElementById('shelter-latitude')?.value) || 35.6762,
        longitude: parseFloat(document.getElementById('shelter-longitude')?.value) || 139.6503,
        capacity: parseInt(document.getElementById('shelter-capacity')?.value) || 100,
        current_occupancy: parseInt(document.getElementById('shelter-occupancy')?.value) || 0,
        attributes: {
            pets_allowed: document.getElementById('pets-allowed')?.checked || true,
            barrier_free: document.getElementById('barrier-free')?.checked || true,
            toilet_available: document.getElementById('toilet-available')?.checked || true,
            food_available: document.getElementById('food-available')?.checked || true,
            medical_available: document.getElementById('medical-available')?.checked || false,
            wifi_available: document.getElementById('wifi-available')?.checked || true,
            charging_available: document.getElementById('charging-available')?.checked || true
        },
        photos: [],
        contact: document.getElementById('shelter-contact')?.value || "123-456-7890",
        operator: document.getElementById('shelter-operator')?.value || "Test Company",
        opened_at: document.getElementById('shelter-opened-at')?.value || "2025-05-25T12:00:00Z",
        status: document.getElementById('shelter-status')?.value || "open"
    };
    try {
        const res = await fetch("/api/shelters", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify(payload)
        });
        if (!res.ok) {
            const error = await res.json();
            throw new Error(error.detail || 'Failed to create shelter');
        }
        const data = await res.json();
        console.log('Shelter created:', data);
        alert('避難所が作成されました');
    } catch (error) {
        console.error('Error:', error);
        alert('避難所作成に失敗しました: ' + error.message);
    }
}

document.getElementById('shelter-form')?.addEventListener('submit', async e => {
    e.preventDefault();
    await createShelter();
});