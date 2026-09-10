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
const user  = JSON.parse(localStorage.getItem('palayscan_user') || 'null');

const isApprovedStaff = user && user.role === 'staff' && (user.staff_status === 'approved' || !user.staff_status);
const isSuperAdmin    = user && user.role === 'admin';

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
    if (tabName === 'scans')     loadScans();
    if (tabName === 'users')     loadUsers();
    if (tabName === 'diseases')  loadDiseases();
}

// --- 3. STATISTICAL METRICS & CHART VISUALIZATION ---
// Queries stats from database and constructs a disease prevalence chart (Chart.js)
let diseaseChartInstance  = null; // Container to hold the Chart.js canvas instance
let genderChartInstance   = null;
let ageChartInstance      = null;
let barangayChartInstance = null;

async function loadDashboard() {
    try {
        // Fetch aggregated numbers from backend
        const res  = await fetch(`${API_BASE_URL}/admin/stats`, { headers: authHeaders() });
        const data = await res.json();

        // Bind numerical stats to HTML cards
        document.getElementById('statUsers').textContent    = data.total_users   ?? 0;
        document.getElementById('statScans').textContent    = data.total_scans   ?? 0;
        document.getElementById('statHealthy').textContent  = data.healthy_scans ?? 0;
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

        // --- 3. Age Demographics Chart ---
        const ageData = data.age_demographics || {};
        const ageLabels = Object.keys(ageData);
        const ageCounts = Object.values(ageData);
        if (ageChartInstance) ageChartInstance.destroy();
        const ageCtx = document.getElementById('ageChart').getContext('2d');
        ageChartInstance = new Chart(ageCtx, {
            type: 'bar',
            data: {
                labels: ageLabels.length ? ageLabels : ['No data'],
                datasets: [{
                    label: 'Farmers',
                    data: ageCounts.length ? ageCounts : [0],
                    backgroundColor: ['#10b981', '#22c55e', '#84cc16', '#eab308', '#f97316'],
                    borderRadius: 8,
                }]
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
                scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } }
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
            <td>${r.created_at.substring(0,16)}</td>
            <td><strong>${r.user_name}</strong><br><small>${r.user_email}</small></td>
            <td>${r.barangay || '—'}</td>
            <td>${r.detected_diseases || '—'}</td>
            <td>${r.health_score}%</td>
            <td><span class="badge ${r.is_healthy ? 'badge-healthy' : 'badge-disease'}">${r.is_healthy ? '✅ Healthy' : '⚠️ Unhealthy'}</span></td>
            <td>${r.weather_condition || '—'}</td>
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
        const res   = await fetch(`${API_BASE_URL}/admin/users`, { headers: authHeaders() });
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
                <td>${u.email}</td>
                <td>${roleBadge}</td>
                <td>${u.address || '—'}</td>
                <td>${u.sex || '—'}</td>
                <td>${u.age || '—'}</td>
                <td>${u.barangay || '—'}</td>
                <td>${u.contact_number || '—'}</td>
                <td>${u.created_at ? u.created_at.substring(0,10) : '—'}</td>
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
        const res  = await fetch(`${API_BASE_URL}/admin/users/${userId}`, {
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
        const res   = await fetch(`${API_BASE_URL}/admin/diseases`, { headers: authHeaders() });
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
    const advice  = document.getElementById('newAdviceText').value.trim();
    const msg     = document.getElementById('diseaseFormMsg');

    if (!disease || !advice) {
        msg.style.color = '#991b1b';
        msg.textContent = 'Please select a disease and enter advice text.';
        return;
    }

    try {
        const res  = await fetch(`${API_BASE_URL}/admin/diseases`, {
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
        const res  = await fetch(`${API_BASE_URL}/admin/diseases/${id}`, {
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
        const res  = await fetch(`${API_BASE_URL}/admin/diseases/${id}`, {
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
            link.href  = URL.createObjectURL(blob);
            link.download = `PALAYSCAN_Report_${new Date().toISOString().slice(0,10)}.csv`;
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
            if(realNavLink) {
                switchTab(tabId, realNavLink);
            }
        });
    });
});
