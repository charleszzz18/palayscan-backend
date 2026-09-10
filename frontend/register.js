// =========================================================================
// PALAYSCAN USER REGISTRATION LOGIC (register.js)
// =========================================================================
// This script handles new user registration.
// It performs client-side password verification before sending data to the Flask backend,
// preventing network round-trips for simple mistakes (like mismatching passwords).

document.getElementById('registerForm').addEventListener('submit', async function(e) {
    e.preventDefault(); // Prevent standard page reload on form submit

    // Collect all input values from the registration form fields
    const first_name     = document.getElementById('first_name').value.trim();
    const middle_initial = document.getElementById('middle_initial').value.trim();
    const last_name      = document.getElementById('last_name').value.trim();
    const full_name      = middle_initial ? `${first_name} ${middle_initial}. ${last_name}` : `${first_name} ${last_name}`;
    const email          = document.getElementById('email').value.trim();
    const role           = document.getElementById('role').value;
    const barangay       = document.getElementById('barangay').value;
    const address        = `${barangay}, Bacnotan, La Union`;
    const sex            = document.getElementById('sex').value;
    const age            = parseInt(document.getElementById('age').value || 0, 10);
    const contact_number = document.getElementById('contact_number').value.trim();
    const password       = document.getElementById('password').value;
    const confirm        = document.getElementById('confirm_password').value;

    // Grab element handles for error/success message boxes and loading button indicators
    const errorBox   = document.getElementById('authError');
    const successBox = document.getElementById('authSuccess');
    const btnText    = document.getElementById('registerBtnText');
    const spinner    = document.getElementById('registerSpinner');
    const btn        = document.getElementById('registerBtn');

    // Reset visibility of the message containers
    errorBox.style.display = 'none';
    successBox.style.display = 'none';

    // --- CLIENT-SIDE VALIDATION ---
    // 1. Check if the password matches the confirmation password input
    if (password !== confirm) {
        errorBox.textContent = 'Passwords do not match.';
        errorBox.style.display = 'block';
        return; // Halt form execution
    }
    // 2. Validate password strength/length requirement (minimum 6 characters)
    if (password.length < 6) {
        errorBox.textContent = 'Password must be at least 6 characters.';
        errorBox.style.display = 'block';
        return; // Halt form execution
    }
    // 3. Validate age
    if (age < 1 || age > 120) {
        errorBox.textContent = 'Please enter a valid age between 1 and 120.';
        errorBox.style.display = 'block';
        return;
    }

    // Toggle button UI to loading state (disable double clicks, show spinner)
    btnText.style.display = 'none';
    spinner.style.display = 'inline';
    btn.disabled = true;

    try {
        // Send registration form parameters to the Flask register API endpoint
        const response = await fetch(`${API_BASE_URL}/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ full_name, email, password, role, address, sex, age, barangay, contact_number })
        });

        const data = await response.json(); // Decode json response from Flask

        // If the registration is rejected by the backend database (e.g. Email already exists), throw an error
        if (!response.ok) {
            throw new Error(data.error || 'Registration failed. Please try again.');
        }

        // --- SUCCESS STATE ---
        // Notify the user of successful account creation
        if (role === 'staff') {
            successBox.textContent = 'Account created! Since you registered as MAO Staff, your account is pending Admin approval. You may log in as a Farmer in the meantime. Redirecting...';
        } else {
            successBox.textContent = 'Account created successfully! Redirecting to login page...';
        }
        successBox.style.display = 'block';
        
        // Wait 2.5 seconds so the user can read the success message, then redirect to login screen
        setTimeout(() => { window.location.href = 'login.html'; }, 2500);

    } catch (err) {
        // --- ERROR STATE ---
        // Output validation/database error messages directly on the registration form
        errorBox.textContent = err.message;
        errorBox.style.display = 'block';
    } finally {
        // --- FINALLY STATE ---
        // Restore the submit button state
        btnText.style.display = 'inline';
        spinner.style.display = 'none';
        btn.disabled = false;
    }
});
