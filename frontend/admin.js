// =========================================================================
// PALAYSCAN ADMIN PANEL LOGIC (admin.js)
// =========================================================================
// This script runs the administration control panel.
// It performs security check-ins, runs tab switching, renders statistical data charts
// (Chart.js), loads and wipes user data tables, manages the disease advice database (CRUD),
// and triggers secure CSV downloads.

// --- PAGINATION STATE ---
const ITEMS_PER_PAGE = 10;
let scansData = [];
let filteredScansData = [];
let scansPage = 1;
let usersData = [];
let filteredUsersData = [];
let usersPage = 1;
let diseasesData = [];
let filteredDiseasesData = [];
let diseasesPage = 1;
let auditData = [];
let filteredAuditData = [];
let auditPage = 1;

function renderPagination(totalItems, currentPage, containerId, clickHandlerName) {
    const totalPages = Math.ceil(totalItems / ITEMS_PER_PAGE);
    const container = document.getElementById(containerId);
    if (!container) return;
    if (totalPages <= 1) {
        container.innerHTML = '';
        return;
    }

    let html = '';
    html += `<button class="page-btn" ${currentPage === 1 ? 'disabled' : `onclick="${clickHandlerName}(${currentPage - 1})"`}>&laquo; Prev</button>`;

    // Show max 5 pages logic could be added, but for simplicity we'll show all or a subset
    let startPage = Math.max(1, currentPage - 2);
    let endPage = Math.min(totalPages, currentPage + 2);

    if (startPage > 1) html += `<button class="page-btn" onclick="${clickHandlerName}(1)">1</button>${startPage > 2 ? '<span class="page-dots">...</span>' : ''}`;

    for (let i = startPage; i <= endPage; i++) {
        html += `<button class="page-btn ${currentPage === i ? 'active' : ''}" onclick="${clickHandlerName}(${i})">${i}</button>`;
    }

    if (endPage < totalPages) html += `${endPage < totalPages - 1 ? '<span class="page-dots">...</span>' : ''}<button class="page-btn" onclick="${clickHandlerName}(${totalPages})">${totalPages}</button>`;

    html += `<button class="page-btn" ${currentPage === totalPages ? 'disabled' : `onclick="${clickHandlerName}(${currentPage + 1})"`}>Next &raquo;</button>`;

    container.innerHTML = html;
}

// --- 1. ADMIN SECURITY SHIELD (AUTH GUARD) ---
// Validates that the active session belongs to an authorized administrator.
// Prevents standard farmers/staff from accessing confidential admin endpoints.
const token = localStorage.getItem('palayscan_token');
const user = JSON.parse(localStorage.getItem('palayscan_user') || 'null');

const isApprovedStaff = user && user.role === 'staff' && (user.staff_status === 'approved' || !user.staff_status);
const isSuperAdmin = user && user.role === 'admin';

if (!token || !user) {
    window.location.href = 'login.html'; // No credentials? Force login.
} else if (!isSuperAdmin && !isApprovedStaff) {
    if (user.role === 'staff' && user.staff_status === 'pending') {
        alert('Access denied. Your MAO Staff account is still pending Admin approval.');
    } else {
        alert('Access denied. Admin or approved MAO Staff access required.');
    }
    window.location.href = 'index.html'; // Redirect to scanner dashboard.
}

// Display admin/staff name in sidebar greeting banner
const roleLabel = isSuperAdmin ? 'Admin' : 'MAO Staff';
document.getElementById('adminName').textContent = `${user.full_name || 'Staff'} (${roleLabel})`;

// Helper: Generates standard authorization headers including the session token.
function authHeaders() {
    return { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };
}

// Admin logout helper. Wipes session keys and redirects.
function adminLogout() {
    fetch(`${API_BASE_URL}/logout`, { method: 'POST', headers: authHeaders() });
    localStorage.removeItem('palayscan_token');
    localStorage.removeItem('palayscan_user');
    sessionStorage.removeItem('analysisData');
    sessionStorage.removeItem('previewImageSrc');
    window.location.href = 'login.html';
}

// --- 2. MULTI-TAB NAVIGATION ROUTER ---
// Handles tab navigation inside the admin layout sidebar dynamically,
// displaying selected tabs and triggering content loads.
function switchTab(tabName, el) {
    // Hide all tab screens
    document.querySelectorAll('.admin-tab').forEach(t => t.style.display = 'none');

    // Remove "active" highlighting from all sidebar menu links
    document.querySelectorAll('.admin-nav-link').forEach(l => l.classList.remove('active'));

    // Display the targeted tab panel
    document.getElementById(`tab-${tabName}`).style.display = 'block';

    // Add "active" class to the clicked navigation item
    el.classList.add('active');

    // Trigger target load functions depending on selected tab
    if (tabName === 'dashboard') loadDashboard();
    if (tabName === 'heatmap') loadHeatmapData();
    if (tabName === 'scans') loadScans();
    if (tabName === 'users') loadUsers();
    if (tabName === 'diseases') loadDiseases();
    if (tabName === 'audit') loadAuditLogs();
    if (tabName === 'reports') initReportsTab();
}

// --- 3. STATISTICAL METRICS & CHART VISUALIZATION ---
// Queries stats from database and constructs a disease prevalence chart (Chart.js)
let diseaseChartInstance = null; // Container to hold the Chart.js canvas instance
let genderChartInstance = null;
let ageChartInstance = null;
let barangayChartInstance = null;

async function loadDashboard() {
    try {
        // Fetch aggregated numbers from backend
        const res = await fetch(`${API_BASE_URL}/admin/stats`, { headers: authHeaders() });
        const data = await res.json();

        // Bind numerical stats to HTML cards
        document.getElementById('statUsers').textContent = data.total_users ?? 0;
        document.getElementById('statScans').textContent = data.total_scans ?? 0;
        document.getElementById('statHealthy').textContent = data.healthy_scans ?? 0;
        document.getElementById('statDiseased').textContent = data.diseased_scans ?? 0;

        const trendUsersEl = document.getElementById('trendUsers');
        if (trendUsersEl) trendUsersEl.textContent = `+${data.new_users_today ?? 0} New Today`;

        const trendScansEl = document.getElementById('trendScans');
        if (trendScansEl) trendScansEl.textContent = `+${data.new_scans_today ?? 0} New Today`;

        const avgAgeEl = document.getElementById('avgAgeText');
        if (avgAgeEl) avgAgeEl.textContent = data.avg_age ?? 0;

        // --- 1. Disease Chart ---
        const labels = (data.top_diseases || []).map(d => d.disease);
        const counts = (data.top_diseases || []).map(d => d.count);
        if (diseaseChartInstance) diseaseChartInstance.destroy();
        const ctx = document.getElementById('diseaseChart').getContext('2d');
        diseaseChartInstance = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels.length ? labels : ['No data yet'],
                datasets: [{
                    label: 'Occurrences',
                    data: counts.length ? counts : [0],
                    backgroundColor: ['#ef4444', '#f59e0b', '#3b82f6', '#10b981', '#6366f1'],
                    borderRadius: 8,
                }]
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
                scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } }
            }
        });

        // --- 2. Gender Distribution Chart ---
        const genderLabels = (data.gender_distribution || []).map(g => `${g.sex} (${g.count})`);
        const genderCounts = (data.gender_distribution || []).map(g => g.count);
        if (genderChartInstance) genderChartInstance.destroy();
        const genderCtx = document.getElementById('genderChart').getContext('2d');
        genderChartInstance = new Chart(genderCtx, {
            type: 'doughnut',
            data: {
                labels: genderLabels.length ? genderLabels : ['No data'],
                datasets: [{
                    data: genderCounts.length ? genderCounts : [1],
                    backgroundColor: ['#3b82f6', '#ec4899', '#f59e0b'],
                    borderWidth: 2,
                    borderColor: '#ffffff'
                }]
            },
            options: {
                responsive: true,
                plugins: { legend: { position: 'bottom' } }
            }
        });

        // --- 3. Age Demographics Chart (Precise Individual Ages) ---
        const ageData = data.age_demographics || {};
        const ageKeys = Object.keys(ageData);
        // Sort numerically to ensure precise ascending order of ages
        ageKeys.sort((a, b) => {
            const numA = parseInt(a, 10);
            const numB = parseInt(b, 10);
            if (!isNaN(numA) && !isNaN(numB)) return numA - numB;
            return a.localeCompare(b);
        });
        const ageLabels = ageKeys.map(a => (!isNaN(a) ? `${a} yrs` : a));
        const ageCounts = ageKeys.map(k => ageData[k]);

        // Dynamic curated color palette for individual age bars
        const agePalette = [
            '#10b981', '#06b6d4', '#3b82f6', '#6366f1',
            '#8b5cf6', '#ec4899', '#f43f5e', '#f97316',
            '#eab308', '#84cc16', '#14b8a6', '#0ea5e9'
        ];
        const barColors = ageKeys.map((_, i) => agePalette[i % agePalette.length]);

        if (ageChartInstance) ageChartInstance.destroy();
        const ageCtx = document.getElementById('ageChart').getContext('2d');
        ageChartInstance = new Chart(ageCtx, {
            type: 'bar',
            data: {
                labels: ageLabels.length ? ageLabels : ['No data'],
                datasets: [{
                    label: 'Farmers',
                    data: ageCounts.length ? ageCounts : [0],
                    backgroundColor: ageKeys.length > 0 ? barColors : '#10b981',
                    borderRadius: 8,
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function (context) {
                                const val = context.parsed.y;
                                return `${val} farmer${val === 1 ? '' : 's'}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        title: { display: true, text: '' }
                    },
                    y: {
                        beginAtZero: true,
                        ticks: { stepSize: 1 },
                        title: { display: true, text: 'Number of Farmers' }
                    }
                }
            }
        });

        // --- 4. Users per Barangay Chart ---
        const brgyLabels = (data.users_per_barangay || []).map(b => b.barangay);
        const brgyCounts = (data.users_per_barangay || []).map(b => b.count);
        if (barangayChartInstance) barangayChartInstance.destroy();
        const brgyCtx = document.getElementById('barangayChart').getContext('2d');
        barangayChartInstance = new Chart(brgyCtx, {
            type: 'bar',
            data: {
                labels: brgyLabels.length ? brgyLabels : ['No data yet'],
                datasets: [{
                    label: 'Registered Users',
                    data: brgyCounts.length ? brgyCounts : [0],
                    backgroundColor: '#22c55e',
                    borderRadius: 8,
                }]
            },
            options: {
                responsive: true,
                indexAxis: 'y',
                plugins: { legend: { display: false } },
                scales: { x: { beginAtZero: true, ticks: { stepSize: 1 } } }
            }
        });
    } catch (err) {
        console.error('Dashboard load error:', err);
    }
}

// --- 4. SCAN HISTORICAL RECORDS VIEW ---
// Loads the history log of all farmer scan events from the database.
async function loadScans() {
    const tbody = document.getElementById('scansBody');
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:30px;">Loading...</td></tr>';
    try {
        const res = await fetch(`${API_BASE_URL}/admin/records`, { headers: authHeaders() });
        scansData = await res.json();
        filteredScansData = [...scansData];
        scansPage = 1;
        renderScansTable();
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:red;padding:20px;">Error loading records: ${err.message || err}</td></tr>`;
        console.error(err);
    }
}

function goToScansPage(page) {
    scansPage = page;
    renderScansTable();
}

function renderScansTable() {
    const tbody = document.getElementById('scansBody');
    if (!filteredScansData.length) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:30px;color:#999;">No scan records found.</td></tr>';
        document.getElementById('scansPagination').innerHTML = '';
        return;
    }

    const start = (scansPage - 1) * ITEMS_PER_PAGE;
    const paginatedItems = filteredScansData.slice(start, start + ITEMS_PER_PAGE);

    tbody.innerHTML = paginatedItems.map(r => `
        <tr>
            <td>#${r.id}</td>
            <td>${r.created_at.substring(0, 16)}</td>
            <td><strong>${r.user_name}</strong><br><small>${r.user_email || ''}</small></td>
            <td>${r.barangay || '—'}</td>
            <td>${r.detected_diseases || '—'}</td>
            <td>${r.is_healthy ? '<span style="color:#16a34a;font-weight:600;">Healthy</span>' : '<span style="color:#dc2626;font-weight:600;">Not Healthy</span>'}</td>
            <td>${r.weather_condition || '—'}</td>
            <td>
                <div style="display:flex;gap:6px;align-items:center;">
                    <a href="index.html?scan_id=${r.id}" style="padding:5px 10px;background:#166534;color:#fff;border-radius:6px;font-size:0.8rem;text-decoration:none;font-weight:600;display:inline-flex;align-items:center;gap:4px;" title="Go to scanned image page">
                        🌾 Page &rarr;
                    </a>
                    <button type="button" onclick="openScanModal(${r.id})" style="padding:5px 10px;background:#0284c7;color:#fff;border:none;border-radius:6px;font-size:0.8rem;cursor:pointer;font-weight:600;display:inline-flex;align-items:center;gap:4px;transition:0.2s;" onmouseover="this.style.background='#0369a1'" onmouseout="this.style.background='#0284c7'">
                        📷 View
                    </button>
                </div>
            </td>
        </tr>
    `).join('');
    renderPagination(filteredScansData.length, scansPage, 'scansPagination', 'goToScansPage');
}

// --- 5. USER ACCOUNTS MANAGEMENT ---
// Handles viewing all registered user accounts and admitting/rejecting/deleting profiles.
async function loadUsers() {
    const tbody = document.getElementById('usersBody');
    tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;padding:30px;">Loading...</td></tr>';
    try {
        const res = await fetch(`${API_BASE_URL}/admin/users`, { headers: authHeaders() });
        usersData = await res.json();

        // Update pending staff banner notification
        const pendingCount = usersData.filter(u => u.role === 'staff' && u.staff_status === 'pending').length;
        const banner = document.getElementById('pendingStaffBanner');
        const countText = document.getElementById('pendingStaffCountText');
        if (banner && countText) {
            if (pendingCount > 0) {
                countText.textContent = pendingCount;
                banner.style.display = 'flex';
            } else {
                banner.style.display = 'none';
            }
        }

        filteredUsersData = [...usersData];
        usersPage = 1;
        renderUsersTable();
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="11" style="text-align:center;color:red;padding:20px;">Error loading users: ${err.message || err}</td></tr>`;
        console.error(err);
    }
}

function goToUsersPage(page) {
    usersPage = page;
    renderUsersTable();
}

function renderUsersTable() {
    const tbody = document.getElementById('usersBody');
    if (!filteredUsersData.length) {
        tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;padding:30px;color:#999;">No users found.</td></tr>';
        document.getElementById('usersPagination').innerHTML = '';
        return;
    }

    const start = (usersPage - 1) * ITEMS_PER_PAGE;
    const paginatedItems = filteredUsersData.slice(start, start + ITEMS_PER_PAGE);

    tbody.innerHTML = paginatedItems.map(u => {
        // Build styled role/status badge
        let roleBadge = '';
        if (u.role === 'admin') {
            roleBadge = `<span class="badge badge-role-admin" style="background:#ede9fe;color:#6d28d9;font-weight:600;">👑 Admin</span>`;
        } else if (u.role === 'staff') {
            if (u.staff_status === 'pending') {
                roleBadge = `<span class="badge" style="background:#fef3c7;color:#b45309;font-weight:600;border:1px solid #fcd34d;">⏳ Pending Staff</span>`;
            } else {
                roleBadge = `<span class="badge badge-role-staff" style="background:#dcfce7;color:#15803d;font-weight:600;">🌿 MAO Staff</span>`;
            }
        } else {
            if (u.staff_status === 'rejected') {
                roleBadge = `<span class="badge badge-role-farmer" style="background:#f1f5f9;color:#475569;">🌾 Farmer <small style="color:#ef4444;font-size:0.75rem;">(Staff Rejected)</small></span>`;
            } else {
                roleBadge = `<span class="badge badge-role-farmer" style="background:#f1f5f9;color:#475569;">🌾 Farmer</span>`;
            }
        }

        // Build action buttons depending on permissions and status
        let actionButtons = '';
        if (u.role === 'admin') {
            actionButtons = '<span style="color:#94a3b8;font-size:0.85rem;">Super Admin</span>';
        } else if (isSuperAdmin) {
            if (u.role === 'staff' && u.staff_status === 'pending') {
                actionButtons = `
                    <div style="display:flex;gap:4px;flex-wrap:wrap;">
                        <button onclick="admitUser(${u.id})" class="admin-admit-btn" title="Admit as MAO Staff" style="background:#16a34a;color:white;border:none;padding:5px 9px;border-radius:6px;font-size:0.75rem;cursor:pointer;font-weight:600;">✅ Admit</button>
                        <button onclick="rejectUser(${u.id})" class="admin-reject-btn" title="Reject and list as Farmer" style="background:#ea580c;color:white;border:none;padding:5px 9px;border-radius:6px;font-size:0.75rem;cursor:pointer;font-weight:600;">❌ Reject</button>
                        <button onclick="deleteUser(${u.id})" class="admin-del-btn" title="Delete account">🗑</button>
                    </div>`;
            } else if (u.role === 'staff') {
                actionButtons = `
                    <div style="display:flex;gap:4px;flex-wrap:wrap;">
                        <button onclick="rejectUser(${u.id})" class="admin-reject-btn" title="Demote to Farmer" style="background:#64748b;color:white;border:none;padding:5px 9px;border-radius:6px;font-size:0.75rem;cursor:pointer;">Set Farmer</button>
                        <button onclick="deleteUser(${u.id})" class="admin-del-btn" title="Delete account">🗑</button>
                    </div>`;
            } else {
                actionButtons = `
                    <div style="display:flex;gap:4px;flex-wrap:wrap;">
                        <button onclick="admitUser(${u.id})" class="admin-admit-btn" title="Promote to MAO Staff" style="background:#0ea5e9;color:white;border:none;padding:5px 9px;border-radius:6px;font-size:0.75rem;cursor:pointer;">Promote Staff</button>
                        <button onclick="deleteUser(${u.id})" class="admin-del-btn" title="Delete account">🗑</button>
                    </div>`;
            }
        } else {
            actionButtons = '<span style="color:#94a3b8;font-size:0.8rem;">View Only</span>';
        }

        return `
            <tr>
                <td>#${u.id}</td>
                <td><strong>${u.full_name}</strong></td>
                <td>${u.username ? `<strong>${u.username}</strong>` : (u.email || '—')}${u.username && u.email ? `<br><small style="color:#64748b;">${u.email}</small>` : ''}</td>
                <td>${roleBadge}</td>
                <td>${u.address || '—'}</td>
                <td>${u.sex || '—'}</td>
                <td>${u.age !== undefined && u.age !== null ? u.age : '—'}${u.dob ? `<br><small style="color:#64748b;">(${u.dob})</small>` : ''}</td>
                <td>${u.barangay || '—'}</td>
                <td>${u.contact_number || '—'}</td>
                <td>${u.created_at ? u.created_at.substring(0, 10) : '—'}</td>
                <td>${actionButtons}</td>
            </tr>
        `;
    }).join('');

    renderPagination(filteredUsersData.length, usersPage, 'usersPagination', 'goToUsersPage');
}

// Admit MAO Staff request
async function admitUser(userId) {
    if (!confirm('Admit this user as MAO Staff? They will be granted full access to the Admin / Staff Panel.')) return;
    try {
        const res = await fetch(`${API_BASE_URL}/admin/users/${userId}/admit`, {
            method: 'POST',
            headers: authHeaders()
        });
        const data = await res.json();
        if (res.ok) {
            alert(data.message || 'User admitted as MAO Staff successfully!');
            loadUsers();
        } else {
            alert(data.error || 'Failed to admit user.');
        }
    } catch (err) {
        alert('Network error. Please try again.');
        console.error(err);
    }
}

// Reject MAO Staff request (automatically converts to Farmer)
async function rejectUser(userId) {
    if (!confirm('Reject this MAO Staff request? The user will automatically be set as a Farmer and restricted to the Farmer panel.')) return;
    try {
        const res = await fetch(`${API_BASE_URL}/admin/users/${userId}/reject`, {
            method: 'POST',
            headers: authHeaders()
        });
        const data = await res.json();
        if (res.ok) {
            alert(data.message || 'MAO Staff request rejected. User is now listed as a Farmer.');
            loadUsers();
        } else {
            alert(data.error || 'Failed to reject user.');
        }
    } catch (err) {
        alert('Network error. Please try again.');
        console.error(err);
    }
}

// Send DELETE request to wipe user account from database
async function deleteUser(userId) {
    if (!confirm('Are you sure you want to delete this user? This cannot be undone.')) return;
    try {
        const res = await fetch(`${API_BASE_URL}/admin/users/${userId}`, {
            method: 'DELETE',
            headers: authHeaders()
        });
        const data = await res.json();
        if (res.ok) {
            alert(data.message);
            loadUsers(); // Refresh accounts table
        } else {
            alert(data.error || 'Delete failed.');
        }
    } catch (err) {
        alert('Network error. Please try again.');
        console.error(err);
    }
}

// --- 6. DISEASE ADVICE DATABASE CRUD CONTROL ---
// Manages adding, viewing, modifying, and removing treatment guidelines.
async function loadDiseases() {
    const tbody = document.getElementById('diseasesBody');
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:30px;">Loading...</td></tr>';
    try {
        const res = await fetch(`${API_BASE_URL}/admin/diseases`, { headers: authHeaders() });
        diseasesData = await res.json();
        filteredDiseasesData = [...diseasesData];
        diseasesPage = 1;
        renderDiseasesTable();
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;color:red;padding:20px;">Error loading disease data: ${err.message || err}</td></tr>`;
        console.error(err);
    }
}

function goToDiseasesPage(page) {
    diseasesPage = page;
    renderDiseasesTable();
}

function renderDiseasesTable() {
    const tbody = document.getElementById('diseasesBody');
    if (!filteredDiseasesData.length) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:30px;color:#999;">No advice entries found.</td></tr>';
        document.getElementById('diseasesPagination').innerHTML = '';
        return;
    }

    const start = (diseasesPage - 1) * ITEMS_PER_PAGE;
    const paginatedItems = filteredDiseasesData.slice(start, start + ITEMS_PER_PAGE);

    tbody.innerHTML = paginatedItems.map(item => `
        <tr>
            <td>#${item.id}</td>
            <td><span class="badge badge-role-farmer">${item.disease_name}</span></td>
            <td id="adviceText_${item.id}">${item.advice}</td>
            <td style="display:flex;gap:8px;flex-wrap:wrap;">
                <button onclick="editAdvice(${item.id})" style="padding:5px 12px;background:#e0e7ff;color:#3730a3;border:1px solid #c7d2fe;border-radius:7px;cursor:pointer;font-size:0.8rem;font-weight:600;">✏️ Edit</button>
                <button onclick="deleteAdvice(${item.id})" class="admin-del-btn">🗑 Delete</button>
            </td>
        </tr>
    `).join('');
    renderPagination(filteredDiseasesData.length, diseasesPage, 'diseasesPagination', 'goToDiseasesPage');
}

// Add advice entry (POST)
async function addAdvice() {
    const disease = document.getElementById('newDiseaseSelect').value;
    const advice = document.getElementById('newAdviceText').value.trim();
    const msg = document.getElementById('diseaseFormMsg');

    if (!disease || !advice) {
        msg.style.color = '#991b1b';
        msg.textContent = 'Please select a disease and enter advice text.';
        return;
    }

    try {
        const res = await fetch(`${API_BASE_URL}/admin/diseases`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify({ disease_name: disease, advice })
        });
        const data = await res.json();
        if (res.ok) {
            msg.style.color = '#166534';
            msg.textContent = 'Advice added successfully!';
            document.getElementById('newAdviceText').value = '';
            document.getElementById('newDiseaseSelect').value = '';
            loadDiseases(); // Refresh list
        } else {
            msg.style.color = '#991b1b';
            msg.textContent = data.error || 'Failed to add advice.';
        }
    } catch (err) {
        msg.style.color = '#991b1b';
        msg.textContent = 'Network error.';
    }
}

// Edit advice entry (PUT)
async function editAdvice(id) {
    const currentText = document.getElementById(`adviceText_${id}`).textContent;
    const newText = prompt('Edit advice text:', currentText);
    if (!newText || newText.trim() === currentText) return;

    try {
        const res = await fetch(`${API_BASE_URL}/admin/diseases/${id}`, {
            method: 'PUT',
            headers: authHeaders(),
            body: JSON.stringify({ advice: newText.trim() })
        });
        const data = await res.json();
        if (res.ok) {
            loadDiseases(); // Refresh list
        } else {
            alert(data.error || 'Update failed.');
        }
    } catch (err) {
        alert('Network error.');
    }
}

// Delete advice entry (DELETE)
async function deleteAdvice(id) {
    if (!confirm('Delete this advice entry?')) return;
    try {
        const res = await fetch(`${API_BASE_URL}/admin/diseases/${id}`, {
            method: 'DELETE',
            headers: authHeaders()
        });
        const data = await res.json();
        if (res.ok) {
            loadDiseases(); // Refresh list
        } else {
            alert(data.error || 'Delete failed.');
        }
    } catch (err) {
        alert('Network error.');
    }
}

// --- 7. EXPORT CSV REPORTS ---
// Downloads a compiled scan records list in a clean spreadsheet format (CSV).
function downloadCSV() {
    const url = `${API_BASE_URL}/admin/report/csv`;
    fetch(url, { headers: authHeaders() })
        .then(res => {
            if (!res.ok) throw new Error('Report generation failed.');
            return res.blob(); // Convert binary file contents to blob
        })
        .then(blob => {
            // Programmatically download file using an ephemeral anchor tag
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = `PALAYSCAN_Report_${new Date().toISOString().slice(0, 10)}.csv`;
            link.click();
        })
        .catch(err => {
            alert('Failed to generate report. ' + err.message);
            console.error(err);
        });
}

// --- INITIALIZE PANEL ---
// Automatically trigger dashboard loading on script startup
loadDashboard();

// --- 8. SEARCH & FILTER LOGIC ---
// Instantly filters the table data arrays based on user input and triggers a re-render.

function filterScans() {
    const query = document.getElementById('scanSearch').value.toLowerCase();
    const statusFilter = document.getElementById('scanStatusFilter').value;
    const diseaseFilter = document.getElementById('scanDiseaseFilter').value;

    filteredScansData = scansData.filter(r => {
        const matchesQuery =
            (r.user_name && r.user_name.toLowerCase().includes(query)) ||
            (r.user_email && r.user_email.toLowerCase().includes(query)) ||
            (r.barangay && r.barangay.toLowerCase().includes(query)) ||
            (r.detected_diseases && r.detected_diseases.toLowerCase().includes(query)) ||
            (r.weather_condition && r.weather_condition.toLowerCase().includes(query));

        const rStatus = r.is_healthy ? 'healthy' : 'unhealthy';
        const matchesStatus = !statusFilter || rStatus === statusFilter;

        const rDisease = (r.detected_diseases || 'healthy').toLowerCase();
        const matchesDisease = !diseaseFilter || rDisease.includes(diseaseFilter);

        return matchesQuery && matchesStatus && matchesDisease;
    });
    scansPage = 1; // Reset pagination
    renderScansTable();
}

function filterUsers() {
    const query = document.getElementById('userSearch').value.toLowerCase();
    const roleFilter = document.getElementById('userRoleFilter').value;

    filteredUsersData = usersData.filter(u => {
        const matchesQuery =
            (u.full_name && u.full_name.toLowerCase().includes(query)) ||
            (u.username && u.username.toLowerCase().includes(query)) ||
            (u.email && u.email.toLowerCase().includes(query)) ||
            (u.barangay && u.barangay.toLowerCase().includes(query)) ||
            (u.contact_number && u.contact_number.toLowerCase().includes(query));

        let matchesRole = true;
        if (roleFilter === 'pending') {
            matchesRole = u.role === 'staff' && u.staff_status === 'pending';
        } else if (roleFilter === 'staff') {
            matchesRole = u.role === 'staff' && (u.staff_status === 'approved' || !u.staff_status);
        } else if (roleFilter === 'farmer') {
            matchesRole = u.role === 'farmer';
        } else if (roleFilter === 'admin') {
            matchesRole = u.role === 'admin';
        }

        return matchesQuery && matchesRole;
    });
    usersPage = 1; // Reset pagination
    renderUsersTable();
}

function filterDiseases() {
    const query = document.getElementById('diseaseSearch').value.toLowerCase();
    filteredDiseasesData = diseasesData.filter(d =>
        (d.disease_name && d.disease_name.toLowerCase().includes(query)) ||
        (d.advice && d.advice.toLowerCase().includes(query))
    );
    diseasesPage = 1; // Reset pagination
    renderDiseasesTable();
}

// --- MOBILE ANIMATED TAB NAVIGATION ---
document.addEventListener("DOMContentLoaded", () => {
    const tabs = document.querySelectorAll("#mobile-nav-container .tab");

    tabs.forEach(clickedTab => {
        clickedTab.addEventListener('click', () => {
            if (clickedTab.classList.contains("active")) return;

            // Remove active from all tabs
            tabs.forEach(tab => {
                tab.classList.remove('active');
            });
            // Add active to clicked
            clickedTab.classList.add('active');

            // Trigger the existing switchTab logic
            const tabId = clickedTab.getAttribute("data-target-tab");
            const realNavLink = document.querySelector(`.admin-nav-link[data-tab="${tabId}"]`);
            if (realNavLink) {
                switchTab(tabId, realNavLink);
            }
        });
    });
});

// =========================================================================
// 9. BARANGAY DISEASE HEAT MAP (LEAFLET)
// =========================================================================
let leafletMap = null;
let heatmapMarkersGroup = null;
let rawHeatmapData = [];
let heatmapMarkersMap = {};

async function loadHeatmapData() {
    try {
        const res = await fetch(`${API_BASE_URL}/admin/heatmap-data`, { headers: authHeaders() });
        if (!res.ok) throw new Error('Failed to load heatmap data');
        rawHeatmapData = await res.json();

        populateBarangayDropdowns();
        updateHeatmapMetrics();
        initOrUpdateMap();
        renderHeatmapMarkers();
        renderBarangayTable();
    } catch (err) {
        console.error('Heatmap load error:', err);
    }
}

function updateHeatmapMetrics() {
    if (!rawHeatmapData || !rawHeatmapData.length) return;

    let totalCases = 0;
    let cleanCount = 0;
    let maxCases = -1;
    let hotspotBrgy = 'None';

    rawHeatmapData.forEach(d => {
        totalCases += (d.total_scans || 0);
        const diseased = (d.unhealthy_scans !== undefined ? d.unhealthy_scans : d.diseased_scans) || 0;
        if (diseased === 0) {
            cleanCount++;
        }
        if (diseased > maxCases) {
            maxCases = diseased;
            hotspotBrgy = `${d.barangay} (${diseased})`;
        }
    });

    const totalEl = document.getElementById('hmTotalBarangays');
    if (totalEl) totalEl.textContent = rawHeatmapData.length;

    const hotspotEl = document.getElementById('hmHotspotBarangay');
    if (hotspotEl) hotspotEl.textContent = maxCases > 0 ? hotspotBrgy : 'None Detected';

    const cleanEl = document.getElementById('hmCleanBarangays');
    if (cleanEl) cleanEl.textContent = `${cleanCount} / ${rawHeatmapData.length}`;

    const casesEl = document.getElementById('hmTotalCasesMapped');
    if (casesEl) casesEl.textContent = totalCases;
}

function initOrUpdateMap() {
    const mapEl = document.getElementById('barangayHeatmap');
    if (!mapEl) return;

    if (!leafletMap) {
        // Bacnotan, La Union real geographic center coordinates: [16.7450, 120.3600]
        leafletMap = L.map('barangayHeatmap').setView([16.7450, 120.3600], 13);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            maxZoom: 18
        }).addTo(leafletMap);
        heatmapMarkersGroup = L.layerGroup().addTo(leafletMap);
    }

    setTimeout(() => {
        if (leafletMap) leafletMap.invalidateSize();
    }, 150);
}

function getConcentrationStyle(count, diseasedCount) {
    if (diseasedCount === 0 && count === 0) {
        return { color: '#22c55e', fillColor: '#22c55e', radius: 10, fillOpacity: 0.35, label: 'Safe / Clean' };
    }
    if (diseasedCount === 0) {
        return { color: '#10b981', fillColor: '#10b981', radius: 12, fillOpacity: 0.45, label: 'Healthy Scans' };
    }
    if (diseasedCount <= 2) {
        return { color: '#eab308', fillColor: '#eab308', radius: 16, fillOpacity: 0.6, label: 'Low Risk' };
    }
    if (diseasedCount <= 5) {
        return { color: '#f97316', fillColor: '#f97316', radius: 22, fillOpacity: 0.7, label: 'Moderate Risk' };
    }
    return { color: '#ef4444', fillColor: '#ef4444', radius: 28, fillOpacity: 0.85, label: 'Hotspot / High Risk' };
}

function renderHeatmapMarkers() {
    if (!leafletMap || !heatmapMarkersGroup) return;
    heatmapMarkersGroup.clearLayers();
    heatmapMarkersMap = {};

    const diseaseFilter = (document.getElementById('heatmapDiseaseFilter')?.value || '').trim().toLowerCase();

    const validBarangays = rawHeatmapData.filter(d => d.barangay && d.barangay.toLowerCase() !== 'bacnotan' && d.barangay.toLowerCase() !== 'unknown');

    validBarangays.forEach(d => {
        const lat = d.lat || 16.7450;
        const lng = d.lng || 120.3600;

        const diseasedTotal = (d.unhealthy_scans !== undefined ? d.unhealthy_scans : d.diseased_scans) || 0;
        let targetCount = d.total_scans || 0;
        let targetDiseased = diseasedTotal;

        if (diseaseFilter) {
            const counts = d.disease_counts || d.diseases || {};
            const matchedKey = Object.keys(counts).find(k => k.toLowerCase() === diseaseFilter);
            targetCount = matchedKey ? counts[matchedKey] : 0;
            targetDiseased = targetCount;
        }

        const style = getConcentrationStyle(targetCount, targetDiseased);

        // Circle marker representing barangay
        const marker = L.circleMarker([lat, lng], {
            radius: style.radius,
            color: style.color,
            fillColor: style.fillColor,
            fillOpacity: style.fillOpacity,
            weight: 2
        });

        // Pulsing heat halo for hotspots
        if (targetDiseased >= 3) {
            L.circle([lat, lng], {
                radius: style.radius * 25,
                color: style.color,
                fillColor: style.fillColor,
                fillOpacity: 0.15,
                weight: 1
            }).addTo(heatmapMarkersGroup);
        }

        // Popup HTML with details and link to view barangay report
        const countsObj = d.disease_counts || d.diseases || {};
        const diseaseBreakdownHtml = Object.entries(countsObj)
            .filter(([_, cnt]) => cnt > 0)
            .map(([name, cnt]) => `<li style="display:flex;justify-content:space-between;font-size:0.8rem;margin-bottom:2px;"><span>${name}</span><strong style="color:#ef4444;">${cnt}</strong></li>`)
            .join('') || '<li style="color:#16a34a;font-size:0.8rem;">No diseases reported</li>';

        const topDiseaseName = d.top_disease || d.most_common_disease || 'None';

        const popupHtml = `
            <div style="font-family:Poppins,sans-serif;min-width:210px;padding:4px;">
                <h4 style="margin:0 0 6px 0;color:#166534;font-size:1.05rem;">📍 Brgy. ${d.barangay}</h4>
                <div style="margin-bottom:8px;">
                    <span style="display:inline-block;padding:3px 8px;border-radius:12px;font-size:0.75rem;font-weight:600;background:${style.fillColor}20;color:${style.color};border:1px solid ${style.color};">${style.label}</span>
                </div>
                <p style="margin:2px 0;font-size:0.82rem;"><strong>Total Scans:</strong> ${d.total_scans || 0}</p>
                <p style="margin:2px 0;font-size:0.82rem;"><strong>Diseased:</strong> <span style="color:#ef4444;font-weight:600;">${diseasedTotal}</span> | <strong>Healthy:</strong> <span style="color:#16a34a;font-weight:600;">${d.healthy_scans || 0}</span></p>
                <p style="margin:2px 0;font-size:0.82rem;"><strong>Top Disease:</strong> ${topDiseaseName}</p>
                
                <div style="margin-top:8px;border-top:1px solid #e2e8f0;padding-top:6px;">
                    <span style="font-size:0.75rem;font-weight:600;color:#64748b;">Disease Counts:</span>
                    <ul style="margin:4px 0 8px 0;padding-left:14px;list-style-type:circle;">
                        ${diseaseBreakdownHtml}
                    </ul>
                </div>

                <button onclick="openBarangaySummaryModal('${d.barangay}')" style="width:100%;padding:6px;background:#166534;color:white;border:none;border-radius:6px;font-size:0.8rem;cursor:pointer;font-weight:600;">📋 View Barangay Report</button>
            </div>
        `;

        marker.bindPopup(popupHtml);
        marker.addTo(heatmapMarkersGroup);
        heatmapMarkersMap[d.barangay.toLowerCase()] = marker;
    });
}

function filterHeatmapMarkers() {
    renderHeatmapMarkers();
}

function zoomToBarangay(brgyName) {
    if (!brgyName) {
        if (leafletMap) leafletMap.setView([16.7450, 120.3600], 13);
        return;
    }
    const found = rawHeatmapData.find(d => d.barangay.toLowerCase() === brgyName.toLowerCase());
    if (found && leafletMap) {
        leafletMap.setView([found.lat, found.lng], 15);
        const marker = heatmapMarkersMap[found.barangay.toLowerCase()];
        if (marker) marker.openPopup();
    }
}

function renderBarangayTable() {
    const tbody = document.getElementById('barangayBreakdownBody');
    if (!tbody) return;

    if (!rawHeatmapData.length) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:24px;color:#94a3b8;">No barangay data available.</td></tr>';
        return;
    }

    const query = (document.getElementById('barangayTableSearch')?.value || '').toLowerCase();

    const rows = rawHeatmapData
        .filter(b => b.barangay && b.barangay.toLowerCase() !== 'bacnotan' && b.barangay.toLowerCase() !== 'unknown')
        .filter(b => !query || b.barangay.toLowerCase().includes(query))
        .sort((a, b) => {
            const disA = (a.unhealthy_scans !== undefined ? a.unhealthy_scans : a.diseased_scans) || 0;
            const disB = (b.unhealthy_scans !== undefined ? b.unhealthy_scans : b.diseased_scans) || 0;
            return disB - disA;
        })
        .map(b => {
            const diseased = (b.unhealthy_scans !== undefined ? b.unhealthy_scans : b.diseased_scans) || 0;
            const topDisease = b.top_disease || b.most_common_disease || 'None';
            const style = getConcentrationStyle(b.total_scans || 0, diseased);
            return `
                <tr>
                    <td><strong>${b.barangay}</strong></td>
                    <td>${b.total_scans || 0}</td>
                    <td><strong style="color:${diseased > 0 ? '#dc2626' : '#64748b'};">${diseased}</strong></td>
                    <td><strong style="color:${(b.healthy_scans || 0) > 0 ? '#16a34a' : '#64748b'};">${b.healthy_scans || 0}</strong></td>
                    <td>${topDisease}</td>
                    <td><span style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:0.75rem;font-weight:600;background:${style.fillColor}20;color:${style.color};border:1px solid ${style.color};">${style.label}</span></td>
                    <td>
                        <button onclick="openBarangaySummaryModal('${b.barangay}')" style="padding:4px 10px;background:#f1f5f9;color:#0f172a;border:1px solid #cbd5e1;border-radius:6px;font-size:0.78rem;cursor:pointer;font-weight:600;">📋 Report</button>
                    </td>
                </tr>
            `;
        }).join('');

    tbody.innerHTML = rows || '<tr><td colspan="7" style="text-align:center;padding:20px;color:#94a3b8;">No matching barangay found.</td></tr>';
}

function filterBarangayTable() {
    renderBarangayTable();
}

// =========================================================================
// 10. SYSTEM AUDIT TRAIL LOGS
// =========================================================================
async function loadAuditLogs() {
    const tbody = document.getElementById('auditBody');
    if (tbody) tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:30px;">Loading audit logs...</td></tr>';

    try {
        const res = await fetch(`${API_BASE_URL}/admin/audit-logs?limit=500`, { headers: authHeaders() });
        if (!res.ok) throw new Error('Failed to fetch audit trail');
        auditData = await res.json();
        filteredAuditData = [...auditData];
        auditPage = 1;
        renderAuditTable();
    } catch (err) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:red;padding:20px;">Error loading audit logs: ${err.message || err}</td></tr>`;
        console.error(err);
    }
}

function getAuditBadgeStyle(action) {
    if (action.includes('LOGIN')) return { bg: '#dcfce7', color: '#15803d' };
    if (action.includes('REGISTER')) return { bg: '#e0e7ff', color: '#3730a3' };
    if (action.includes('SCAN')) return { bg: '#fef3c7', color: '#b45309' };
    if (action.includes('DELETE') || action.includes('REJECT')) return { bg: '#fee2e2', color: '#991b1b' };
    if (action.includes('ADMIT') || action.includes('ADVICE')) return { bg: '#f3e8ff', color: '#6b21a8' };
    if (action.includes('BACKUP') || action.includes('RESTORE')) return { bg: '#e0f2fe', color: '#0369a1' };
    return { bg: '#f1f5f9', color: '#475569' };
}

function renderAuditTable() {
    const tbody = document.getElementById('auditBody');
    if (!tbody) return;

    if (!filteredAuditData.length) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:30px;color:#94a3b8;">No audit trail events found.</td></tr>';
        const pag = document.getElementById('auditPagination');
        if (pag) pag.innerHTML = '';
        return;
    }

    const start = (auditPage - 1) * ITEMS_PER_PAGE;
    const paginatedItems = filteredAuditData.slice(start, start + ITEMS_PER_PAGE);

    tbody.innerHTML = paginatedItems.map(log => {
        const badge = getAuditBadgeStyle(log.action || '');
        const timeStr = log.created_at ? log.created_at.substring(0, 19).replace('T', ' ') : '—';
        const userDisplay = log.username ? `<strong>${log.username}</strong>` : (log.user_name || 'System / Guest');
        const roleDisplay = log.user_role ? `<span style="font-size:0.75rem;color:#64748b;">(${log.user_role})</span>` : '';

        let detailsHtml = log.details || '—';
        const scanMatch = detailsHtml.match(/Scan #(\d+)/i);
        if (scanMatch) {
            const scanId = scanMatch[1];
            detailsHtml = detailsHtml.replace(
                /Scan #(\d+)/i,
                `<div style="display:inline-flex;align-items:center;gap:6px;flex-wrap:wrap;">
                    <a href="index.html?scan_id=${scanId}" style="display:inline-flex;align-items:center;gap:5px;padding:4px 11px;background:#e0f2fe;color:#0369a1;border:1px solid #7dd3fc;border-radius:7px;font-size:0.82rem;font-weight:700;text-decoration:none;transition:0.15s;box-shadow:0 1px 3px rgba(3,105,161,0.12);" onmouseover="this.style.background='#bae6fd'" onmouseout="this.style.background='#e0f2fe'" title="Tap to automatically go to the scanned image page">
                        🌾 <strong>Scan #${scanId}</strong> &rarr;
                    </a>
                    <button type="button" onclick="event.stopPropagation(); openScanModal(${scanId})" style="display:inline-flex;align-items:center;gap:3px;padding:3px 8px;background:#f8fafc;color:#475569;border:1px solid #cbd5e1;border-radius:6px;font-size:0.75rem;cursor:pointer;transition:0.15s;" onmouseover="this.style.background='#e2e8f0'" onmouseout="this.style.background='#f8fafc'" title="Quick preview popup modal">
                        👁️ Preview
                    </button>
                </div>`
            );
        }

        return `
            <tr ${scanMatch ? `style="cursor:pointer;" onclick="if(!event.target.closest('a') && !event.target.closest('button')) window.location.href='index.html?scan_id=${scanMatch[1]}';"` : ''}>
                <td>#${log.id}</td>
                <td style="white-space:nowrap;font-size:0.85rem;color:#475569;">${timeStr}</td>
                <td>
                    <span style="display:inline-block;padding:3px 9px;border-radius:6px;font-size:0.75rem;font-weight:700;background:${badge.bg};color:${badge.color};">
                        ${log.action}
                    </span>
                </td>
                <td>${userDisplay} ${roleDisplay}</td>
                <td style="font-family:monospace;font-size:0.82rem;color:#64748b;">${log.ip_address || '—'}</td>
                <td style="font-size:0.85rem;max-width:340px;word-break:break-word;">${detailsHtml}</td>
            </tr>
        `;
    }).join('');

    renderPagination(filteredAuditData.length, auditPage, 'auditPagination', 'goToAuditPage');
}

// --- SCAN DETAILS & IMAGE INSPECTION MODAL ---
async function openScanModal(scanId) {
    const modal = document.getElementById('scanDetailModal');
    const body = document.getElementById('modalScanBody');
    const title = document.getElementById('modalScanTitle');
    const fullImgBtn = document.getElementById('modalFullImgBtn');
    const viewInTableBtn = document.getElementById('modalViewInTableBtn');
    const goToScanPageBtn = document.getElementById('modalGoToScanPageBtn');
    if (!modal || !body) return;

    modal.style.display = 'flex';
    title.textContent = `Scan #${scanId} Details`;
    body.innerHTML = '<div style="text-align:center;padding:40px;color:#64748b;">Loading scan details and image...</div>';

    try {
        let scan = (scansData || []).find(s => String(s.id) === String(scanId));
        if (!scan) {
            const res = await fetch(`${API_BASE_URL}/admin/records/${scanId}`, { headers: authHeaders() });
            if (res.ok) {
                scan = await res.json();
            }
        }

        if (!scan) {
            body.innerHTML = `<div style="text-align:center;padding:30px;color:#dc2626;">Scan #${scanId} record could not be found.</div>`;
            return;
        }

        if (goToScanPageBtn) {
            goToScanPageBtn.href = `index.html?scan_id=${scanId}`;
        }

        const imgUrl = scan.image_filename ? `${API_BASE_URL}/uploads/${scan.image_filename}` : '';
        if (fullImgBtn) {
            if (imgUrl) {
                fullImgBtn.href = imgUrl;
                fullImgBtn.style.display = 'inline-flex';
            } else {
                fullImgBtn.style.display = 'none';
            }
        }

        if (viewInTableBtn) {
            viewInTableBtn.onclick = () => {
                closeScanModal();
                switchTab('scans');
                const searchInput = document.getElementById('scanSearch');
                if (searchInput) {
                    searchInput.value = `${scanId}`;
                    filterScans();
                }
            };
        }

        const isHealthy = scan.is_healthy;
        const diseaseName = scan.detected_diseases || (isHealthy ? 'Healthy' : 'Unknown Issue');
        const infectionPct = scan.infected_area_pct !== undefined ? `${scan.infected_area_pct}%` : (isHealthy ? '0%' : 'Low');

        body.innerHTML = `
            <!-- Scanned Leaf Photo -->
            <div style="background:#0f172a; border-radius:14px; padding:16px; text-align:center; margin-bottom:20px; box-shadow: inset 0 2px 6px rgba(0,0,0,0.5);">
                ${imgUrl ? `
                    <div style="position:relative; display:inline-block; max-width:100%;">
                        <img src="${imgUrl}" alt="Scanned Leaf Photo" style="max-height:380px; max-width:100%; border-radius:8px; object-fit:contain; display:block; margin:0 auto; box-shadow:0 8px 25px rgba(0,0,0,0.4);" />
                        <span style="position:absolute; bottom:10px; right:10px; background:rgba(15,23,42,0.85); color:#fff; font-size:0.75rem; padding:4px 10px; border-radius:20px; backdrop-filter:blur(4px);">🌾 Scanned Leaf Photo</span>
                    </div>
                ` : `
                    <div style="padding:50px 20px; color:#94a3b8; font-size:0.95rem;">
                        📷 No image file found on server for this scan record.
                    </div>
                `}
            </div>

            <!-- Key Diagnosis Summary Cards -->
            <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:12px; margin-bottom:20px;">
                <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:14px; text-align:left;">
                    <span style="font-size:0.75rem; color:#64748b; font-weight:700; text-transform:uppercase;">Detected Disease</span>
                    <h3 style="margin:4px 0 0; font-size:1.25rem; font-weight:800; color:${isHealthy ? '#16a34a' : '#dc2626'};">${diseaseName}</h3>
                </div>
                <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:14px; text-align:left;">
                    <span style="font-size:0.75rem; color:#64748b; font-weight:700; text-transform:uppercase;">Infection Spread</span>
                    <h3 style="margin:4px 0 0; font-size:1.25rem; font-weight:800; color:${isHealthy ? '#16a34a' : '#ea580c'};">${infectionPct}</h3>
                </div>
                <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:14px; text-align:left;">
                    <span style="font-size:0.75rem; color:#64748b; font-weight:700; text-transform:uppercase;">Barangay Location</span>
                    <h3 style="margin:4px 0 0; font-size:1.1rem; font-weight:700; color:#1e293b;">${scan.barangay || 'Bacnotan'}</h3>
                </div>
                <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:14px; text-align:left;">
                    <span style="font-size:0.75rem; color:#64748b; font-weight:700; text-transform:uppercase;">Farmer / Account</span>
                    <h3 style="margin:4px 0 0; font-size:1.05rem; font-weight:700; color:#1e293b;">${scan.user_name || scan.username}</h3>
                </div>
            </div>

            <!-- Context Info -->
            <div style="display:flex; gap:16px; flex-wrap:wrap; background:#f1f5f9; border-radius:10px; padding:10px 16px; margin-bottom:18px; font-size:0.85rem; color:#475569;">
                <span>📅 <strong>Date:</strong> ${scan.created_at ? scan.created_at.substring(0, 19).replace('T', ' ') : '—'}</span>
                <span>☀️ <strong>Weather:</strong> ${scan.weather_condition || 'Normal'}</span>
            </div>

            <!-- Treatment & Clinical Advice -->
            ${scan.advice && scan.advice.length > 0 ? `
                <div style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:12px; padding:16px; text-align:left;">
                    <h4 style="margin:0 0 10px; color:#166534; font-size:0.95rem; font-weight:700;">🌱 Recommended Treatment Advice</h4>
                    <ul style="margin:0; padding-left:20px; color:#14532d; font-size:0.88rem; line-height:1.6;">
                        ${scan.advice.map(a => `<li>${a}</li>`).join('')}
                    </ul>
                </div>
            ` : ''}
        `;
    } catch (err) {
        body.innerHTML = `<div style="text-align:center;padding:30px;color:#dc2626;">Error loading scan #${scanId}: ${err.message || err}</div>`;
        console.error(err);
    }
}

function closeScanModal() {
    const modal = document.getElementById('scanDetailModal');
    if (modal) modal.style.display = 'none';
}

function goToAuditPage(page) {
    auditPage = page;
    renderAuditTable();
}

function filterAuditLogs() {
    const query = (document.getElementById('auditSearchInput')?.value || '').toLowerCase();
    const actionFilter = (document.getElementById('auditActionFilter')?.value || '');

    filteredAuditData = auditData.filter(log => {
        const matchesAction = !actionFilter || log.action === actionFilter;
        const matchesQuery =
            (log.action && log.action.toLowerCase().includes(query)) ||
            (log.username && log.username.toLowerCase().includes(query)) ||
            (log.user_name && log.user_name.toLowerCase().includes(query)) ||
            (log.ip_address && log.ip_address.toLowerCase().includes(query)) ||
            (log.details && log.details.toLowerCase().includes(query));

        return matchesAction && matchesQuery;
    });

    auditPage = 1;
    renderAuditTable();
}

// =========================================================================
// 11. DATABASE & IMAGES BACKUP AND RESTORE
// =========================================================================
async function downloadBackup() {
    const btn = document.getElementById('backupBtn');
    const msg = document.getElementById('backupMsg');

    if (btn) btn.disabled = true;
    if (msg) {
        msg.style.color = '#0369a1';
        msg.innerHTML = '⏳ Generating full archive (database dump & uploaded images)... Please wait.';
    }

    try {
        const res = await fetch(`${API_BASE_URL}/admin/backup`, { headers: authHeaders() });
        if (!res.ok) {
            const errJson = await res.json().catch(() => ({}));
            throw new Error(errJson.error || 'Backup creation failed');
        }

        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        const timestamp = new Date().toISOString().replace(/[:T]/g, '-').slice(0, 19);
        a.href = url;
        a.download = `palayscan_full_backup_${timestamp}.zip`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        if (msg) {
            msg.style.color = '#166534';
            msg.innerHTML = '✅ Full system backup downloaded successfully!';
        }
    } catch (err) {
        if (msg) {
            msg.style.color = '#991b1b';
            msg.innerHTML = `❌ Error downloading backup: ${err.message}`;
        }
        alert('Failed to generate backup: ' + err.message);
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function performRestore() {
    const fileInput = document.getElementById('restoreFileInput');
    const btn = document.getElementById('restoreBtn');
    const msg = document.getElementById('restoreMsg');

    if (!fileInput || !fileInput.files || !fileInput.files[0]) {
        alert('Please select a PalayScan backup .zip file to restore.');
        return;
    }

    const file = fileInput.files[0];
    if (!file.name.toLowerCase().endsWith('.zip')) {
        alert('Invalid file type. Only .zip backup archives are accepted.');
        return;
    }

    const confirmed = confirm(
        '⚠️ CRITICAL RESTORE CONFIRMATION\n\n' +
        'Are you sure you want to restore the system from this backup archive?\n' +
        'This will import/overwrite database records and extract leaf images.\n\n' +
        'File: ' + file.name + ' (' + (file.size / 1024 / 1024).toFixed(2) + ' MB)\n\n' +
        'Click OK to proceed with system restoration.'
    );

    if (!confirmed) return;

    if (btn) btn.disabled = true;
    if (msg) {
        msg.style.color = '#b45309';
        msg.innerHTML = '⏳ Uploading and unpacking backup... This may take a moment.';
    }

    const formData = new FormData();
    formData.append('backup_file', file);

    try {
        const res = await fetch(`${API_BASE_URL}/admin/restore`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` },
            body: formData
        });

        const data = await res.json();
        if (res.ok) {
            if (msg) {
                msg.style.color = '#166534';
                msg.innerHTML = `✅ Restore successful! Records: ${data.records_restored || 0}, Images unpacked: ${data.images_restored || 0}`;
            }
            alert('Restore completed successfully!\n\n' + (data.message || 'Database records and leaf images restored.'));
            fileInput.value = '';
            // Refresh dashboards and data tables
            loadDashboard();
            loadScans();
            loadUsers();
        } else {
            throw new Error(data.error || 'Restore failed on server');
        }
    } catch (err) {
        if (msg) {
            msg.style.color = '#991b1b';
            msg.innerHTML = `❌ Restore error: ${err.message}`;
        }
        alert('Failed to restore backup: ' + err.message);
    } finally {
        if (btn) btn.disabled = false;
    }
}

// =========================================================================
// 12. LOCATION-SPECIFIC BARANGAY REPORTS
// =========================================================================
function populateBarangayDropdowns() {
    const heatSelect = document.getElementById('heatmapBarangaySelect');
    const reportSelect = document.getElementById('reportBarangaySelect');

    const defaultBarangays = [
        "Agtipal", "Arosip", "Bacqui", "Bacsil", "Bagutot", "Ballogo",
        "Baroro", "Bitalag", "Bulala", "Burayoc", "Bussaoit", "Cabaroan",
        "Cabarsican", "Cabugao", "Calautit", "Carcarmay", "Casiaman",
        "Galongen", "Guinabang", "Legleg", "Lisqueb", "Mabanengbeng 1st",
        "Mabanengbeng 2nd", "Maragayap", "Nagatiran", "Nagsaraboan",
        "Nagsimbaanan", "Nangalisan", "Narra", "Ortega", "Oya-oy",
        "Paagan", "Pandan", "Pang-pang", "Poblacion", "Quirino",
        "Raois", "Salincob", "San Martin", "Santa Cruz", "Santa Rita",
        "Sapilang", "Sayoan", "Sipulo", "Tammocalao", "Ubbog", "Zaragosa"
    ];

    const barangayList = (rawHeatmapData && rawHeatmapData.length)
        ? rawHeatmapData.map(d => d.barangay)
        : defaultBarangays;

    const uniqueBarangays = Array.from(new Set(barangayList))
        .filter(b => b && b.toLowerCase() !== 'bacnotan' && b.toLowerCase() !== 'unknown')
        .sort();

    if (heatSelect) {
        heatSelect.innerHTML = '<option value="">-- All 47 Barangays --</option>';
        uniqueBarangays.forEach(b => {
            const opt = document.createElement('option');
            opt.value = b;
            opt.textContent = b;
            heatSelect.appendChild(opt);
        });
    }

    if (reportSelect) {
        reportSelect.innerHTML = '<option value="">-- Select Barangay --</option>';
        uniqueBarangays.forEach(b => {
            const opt = document.createElement('option');
            opt.value = b;
            opt.textContent = b;
            reportSelect.appendChild(opt);
        });
    }
}

function initReportsTab() {
    populateBarangayDropdowns();
}

function downloadBarangayCSV() {
    const select = document.getElementById('reportBarangaySelect');
    const brgy = select ? select.value : '';

    if (!brgy) {
        alert('Please select a specific Barangay to download its dedicated report.');
        return;
    }

    const url = `${API_BASE_URL}/admin/report/csv?barangay=${encodeURIComponent(brgy)}`;
    fetch(url, { headers: authHeaders() })
        .then(res => {
            if (!res.ok) throw new Error('Failed to generate barangay report.');
            return res.blob();
        })
        .then(blob => {
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = `PALAYSCAN_${brgy.replace(/\s+/g, '_')}_Report_${new Date().toISOString().slice(0, 10)}.csv`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        })
        .catch(err => {
            alert('Failed to generate report: ' + err.message);
            console.error(err);
        });
}

async function openBarangaySummaryModal(barangayName) {
    let brgy = barangayName;
    if (!brgy) {
        const select = document.getElementById('reportBarangaySelect');
        brgy = select ? select.value : '';
    }

    if (!brgy) {
        alert('Please select a barangay first.');
        return;
    }

    const modal = document.getElementById('barangaySummaryModal');
    const title = document.getElementById('modalBarangayTitle');
    const content = document.getElementById('modalBarangayContent');

    if (!modal || !content) return;

    modal.style.display = 'flex';
    if (title) title.textContent = `📍 Barangay ${brgy} - Rice Health & Disease Report`;
    content.innerHTML = '<div style="text-align:center;padding:40px;color:#64748b;">Loading summary for Barangay ' + brgy + '...</div>';

    try {
        const res = await fetch(`${API_BASE_URL}/admin/report/barangay-summary?barangay=${encodeURIComponent(brgy)}`, { headers: authHeaders() });
        if (!res.ok) throw new Error('Could not load barangay summary');
        const data = await res.json();

        const totalScans = data.total_scans || 0;
        const diseasedScans = (data.unhealthy_scans !== undefined ? data.unhealthy_scans : data.diseased_scans) || 0;
        const healthyScans = data.healthy_scans || 0;
        const primaryDisease = data.primary_disease || data.top_disease || 'None';
        const recentScans = data.recent_scans || [];

        const counts = data.disease_counts || {};
        const diseaseBreakdownRows = (Array.isArray(counts)
            ? counts.map(item => [item.disease, item.count])
            : Object.entries(counts))
            .map(([disease, count]) => `
                <div style="background:#f8fafc;padding:12px;border-radius:10px;border:1px solid #e2e8f0;text-align:center;">
                    <div style="font-size:0.8rem;color:#64748b;">${disease}</div>
                    <div style="font-size:1.3rem;font-weight:700;color:${count > 0 ? '#dc2626' : '#16a34a'};margin-top:4px;">${count}</div>
                </div>
            `).join('');

        const scansRows = recentScans.length ? recentScans.map(s => `
            <tr>
                <td>${s.created_at ? s.created_at.substring(0, 16) : '—'}</td>
                <td><strong>${s.user_name || 'Farmer'}</strong></td>
                <td>${s.detected_diseases || 'Healthy'}</td>
                <td>${s.is_healthy ? '<span style="color:#16a34a;font-weight:600;">Healthy</span>' : '<span style="color:#dc2626;font-weight:600;">Not Healthy</span>'}</td>
                <td><span class="badge ${s.is_healthy ? 'badge-healthy' : 'badge-disease'}">${s.is_healthy ? 'Healthy' : 'Not Healthy'}</span></td>
            </tr>
        `).join('') : '<tr><td colspan="5" style="text-align:center;padding:20px;color:#94a3b8;">No scan records found in this barangay.</td></tr>';

        content.innerHTML = `
            <!-- Top Stat Cards -->
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:14px;margin-bottom:20px;">
                <div style="background:#f0fdf4;border:1.5px solid #bbf7d0;padding:14px;border-radius:12px;text-align:center;">
                    <span style="font-size:1.6rem;font-weight:700;color:#166534;">${totalScans}</span>
                    <p style="margin:2px 0 0;font-size:0.8rem;color:#15803d;font-weight:500;">Total Scans</p>
                </div>
                <div style="background:#fef2f2;border:1.5px solid #fecaca;padding:14px;border-radius:12px;text-align:center;">
                    <span style="font-size:1.6rem;font-weight:700;color:#991b1b;">${diseasedScans}</span>
                    <p style="margin:2px 0 0;font-size:0.8rem;color:#b91c1c;font-weight:500;">Diseased Cases</p>
                </div>
                <div style="background:#f0fdf4;border:1.5px solid #bbf7d0;padding:14px;border-radius:12px;text-align:center;">
                    <span style="font-size:1.6rem;font-weight:700;color:#166534;">${healthyScans}</span>
                    <p style="margin:2px 0 0;font-size:0.8rem;color:#15803d;font-weight:500;">Healthy Cases</p>
                </div>
                <div style="background:#fffbeb;border:1.5px solid #fde68a;padding:14px;border-radius:12px;text-align:center;">
                    <span style="font-size:1.1rem;font-weight:700;color:#92400e;display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${primaryDisease}</span>
                    <p style="margin:2px 0 0;font-size:0.8rem;color:#b45309;font-weight:500;">Primary Disease</p>
                </div>
            </div>

            <!-- Disease Distribution Breakdown -->
            <h4 style="margin:16px 0 10px 0;color:#1e293b;font-size:0.95rem;">🔬 Disease Occurrence in ${brgy}</h4>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px;margin-bottom:24px;">
                ${diseaseBreakdownRows}
            </div>

            <!-- Scan History in Barangay -->
            <h4 style="margin:16px 0 10px 0;color:#1e293b;font-size:0.95rem;">📜 Reported Scans in ${brgy}</h4>
            <div class="admin-table-wrap">
                <table class="admin-table">
                    <thead>
                        <tr>
                            <th>Date & Time</th>
                            <th>Farmer</th>
                            <th>Disease Detected</th>
                            <th>Health Status</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${scansRows}
                    </tbody>
                </table>
            </div>
        `;
    } catch (err) {
        content.innerHTML = `<div style="color:#ef4444;text-align:center;padding:30px;">Error loading barangay report: ${err.message}</div>`;
    }
}

function closeBarangayModal() {
    const modal = document.getElementById('barangaySummaryModal');
    if (modal) modal.style.display = 'none';
}

// --- CHANGE PASSWORD MODAL LOGIC ---
function openChangePasswordModal() {
    const modal = document.getElementById('changePasswordModal');
    if (modal) {
        modal.style.display = 'flex';
        const form = document.getElementById('changePasswordForm');
        if (form) form.reset();
        const err = document.getElementById('pwdError');
        const suc = document.getElementById('pwdSuccess');
        if (err) err.style.display = 'none';
        if (suc) suc.style.display = 'none';
        setTimeout(() => document.getElementById('currentPasswordInput')?.focus(), 100);
    }
}

function closeChangePasswordModal() {
    const modal = document.getElementById('changePasswordModal');
    if (modal) modal.style.display = 'none';
}

async function submitChangePassword(e) {
    e.preventDefault();
    const currentPassword = document.getElementById('currentPasswordInput').value;
    const newPassword = document.getElementById('newPasswordInput').value;
    const confirmPassword = document.getElementById('confirmPasswordInput').value;
    const errBox = document.getElementById('pwdError');
    const sucBox = document.getElementById('pwdSuccess');
    const btn = document.getElementById('savePasswordBtn');

    if (errBox) errBox.style.display = 'none';
    if (sucBox) sucBox.style.display = 'none';

    if (newPassword !== confirmPassword) {
        if (errBox) {
            errBox.textContent = 'New passwords do not match. Please verify.';
            errBox.style.display = 'block';
        }
        return;
    }

    if (newPassword.length < 6) {
        if (errBox) {
            errBox.textContent = 'New password must be at least 6 characters.';
            errBox.style.display = 'block';
        }
        return;
    }

    btn.disabled = true;
    btn.textContent = 'Updating...';

    try {
        const res = await fetch(`${API_BASE_URL}/change-password`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify({
                current_password: currentPassword,
                new_password: newPassword
            })
        });

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || 'Failed to update password.');
        }

        if (sucBox) {
            sucBox.textContent = 'Password changed successfully! You can use your new password next time you sign in.';
            sucBox.style.display = 'block';
        }
        const form = document.getElementById('changePasswordForm');
        if (form) form.reset();

        setTimeout(() => {
            closeChangePasswordModal();
        }, 2200);

    } catch (err) {
        if (errBox) {
            errBox.textContent = err.message;
            errBox.style.display = 'block';
        }
    } finally {
        btn.disabled = false;
        btn.textContent = 'Update Password';
    }
}


