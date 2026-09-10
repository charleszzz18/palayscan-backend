// =========================================================================
// PALAYSCAN LOGIN LOGIC (login.js)
// =========================================================================
// This script handles logging into the Palayscan system.
// It verifies who is logging in, requests a secure session token from the Flask backend,
// and routes the user to either the User Dashboard or Admin Panel depending on their role.

// --- 1. AUTHENTICATION REDIRECT GUARD ---
// If the user has already logged in previously and has a valid token saved in their browser,
// they don't need to log in again. Redirect them to the correct dashboard automatically.
if (localStorage.getItem('palayscan_token')) {
    const user = JSON.parse(localStorage.getItem('palayscan_user') || '{}');
    const isApprovedStaff = user.role === 'staff' && (user.staff_status === 'approved' || !user.staff_status);
    if (user.role === 'admin' || isApprovedStaff) {
        window.location.href = 'admin.html'; // Go to Admin / MAO Staff Panel
    } else {
        window.location.href = 'index.html'; // Go to Farmer Scanning Dashboard
    }
}

// Clear any cached or autofilled credentials whenever the page is displayed (including bfcache)
window.addEventListener('pageshow', function() {
    const form = document.getElementById('loginForm');
    if (form) form.reset();
    const emailField = document.getElementById('email');
    if (emailField) emailField.value = '';
    const passField = document.getElementById('password');
    if (passField) passField.value = '';
});

// --- 2. LOGIN FORM SUBMISSION HANDLER ---
// Listen for when the user clicks the "Sign In" button or presses Enter
document.getElementById('loginForm').addEventListener('submit', async function(e) {
    e.preventDefault(); // Stop the form from performing a normal browser page reload

    // Extract user inputs from the text fields
    const email    = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;
    
    // Grab references to button labels, loaders, and error display boxes
    const btnText  = document.getElementById('loginBtnText');
    const spinner  = document.getElementById('loginSpinner');
    const errorBox = document.getElementById('authError');
    const btn      = document.getElementById('loginBtn');

    // Reset UI state: hide error box, show loading spinner, disable button to prevent double submission
    errorBox.style.display = 'none';
    btnText.style.display = 'none';
    spinner.style.display = 'inline';
    btn.disabled = true;

    try {
        // Send a POST request to the backend server's login endpoint
        const response = await fetch(`${API_BASE_URL}/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }) // Send credentials as JSON payload
        });

        const data = await response.json(); // Parse the JSON response from Flask

        // If the server returns a bad status code (e.g. 400 or 401), throw an error with the backend's message
        if (!response.ok) {
            throw new Error(data.error || 'Login failed. Check your credentials.');
        }

        // --- SUCCESS STATE ---
        // Save the authentication session token and user profile details locally in the browser storage
        localStorage.setItem('palayscan_token', data.token);
        localStorage.setItem('palayscan_user', JSON.stringify(data.user));
        
        // Clear previous session analysis data to ensure a fresh scan page
        sessionStorage.removeItem('analysisData');
        sessionStorage.removeItem('previewImageSrc');

        // Redirect the user to the correct page based on their system role
        const isApprovedStaff = data.user.role === 'staff' && (data.user.staff_status === 'approved' || !data.user.staff_status);
        if (data.user.role === 'admin' || isApprovedStaff) {
            window.location.href = 'admin.html'; // Admins and admitted MAO Staff go to central panel
        } else {
            window.location.href = 'index.html'; // Regular farmers and pending staff go to scan page
        }

    } catch (err) {
        // --- ERROR STATE ---
        // Catch any network errors or authentication errors and display them on the login form
        errorBox.textContent = err.message;
        errorBox.style.display = 'block';
    } finally {
        // --- FINALLY STATE ---
        // Re-enable the submit button and restore the text, hiding the loading spinner
        btnText.style.display = 'inline';
        spinner.style.display = 'none';
        btn.disabled = false;
    }
});
