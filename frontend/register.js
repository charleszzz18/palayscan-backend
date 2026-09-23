// =========================================================================
// PALAYSCAN USER REGISTRATION LOGIC (register.js)
// =========================================================================
// This script handles new user registration with Username and Date of Birth,
// automatically calculating the farmer's age dynamically.

function calculateAge(dobString) {
    if (!dobString) return 0;
    const birthDate = new Date(dobString);
    const today = new Date();
    let age = today.getFullYear() - birthDate.getFullYear();
    const m = today.getMonth() - birthDate.getMonth();
    if (m < 0 || (m === 0 && today.getDate() < birthDate.getDate())) {
        age--;
    }
    return age;
}

// Initialize dynamic DOB age calculator
const dobInput = document.getElementById('dob');
const ageBadge = document.getElementById('calculatedAgeBadge');
if (dobInput && ageBadge) {
    dobInput.max = new Date().toISOString().split('T')[0];
    dobInput.addEventListener('change', () => {
        const age = calculateAge(dobInput.value);
        if (age > 0 && age <= 120) {
            ageBadge.innerHTML = `🎂 Calculated Age: <strong>${age} years old</strong>`;
            ageBadge.style.display = 'block';
        } else if (dobInput.value) {
            ageBadge.innerHTML = `⚠️ Invalid birth date (Calculated age: ${age})`;
            ageBadge.style.display = 'block';
        } else {
            ageBadge.style.display = 'none';
        }
    });
}

document.getElementById('registerForm').addEventListener('submit', async function(e) {
    e.preventDefault();

    // Collect input values
    const first_name     = document.getElementById('first_name').value.trim();
    const middle_initial = document.getElementById('middle_initial').value.trim();
    const last_name      = document.getElementById('last_name').value.trim();
    const full_name      = middle_initial ? `${first_name} ${middle_initial}. ${last_name}` : `${first_name} ${last_name}`;
    const username       = document.getElementById('username').value.trim().toLowerCase();
    const role           = document.getElementById('role').value;
    const barangay       = document.getElementById('barangay').value;
    const address        = `${barangay}, Bacnotan, La Union`;
    const sex            = document.getElementById('sex').value;
    const dob            = document.getElementById('dob').value;
    const age            = calculateAge(dob);
    const contact_number = document.getElementById('contact_number').value.trim();
    const password       = document.getElementById('password').value;
    const confirm        = document.getElementById('confirm_password').value;

    const errorBox   = document.getElementById('authError');
    const successBox = document.getElementById('authSuccess');
    const btnText    = document.getElementById('registerBtnText');
    const spinner    = document.getElementById('registerSpinner');
    const btn        = document.getElementById('registerBtn');

    errorBox.style.display = 'none';
    successBox.style.display = 'none';

    // --- CLIENT-SIDE VALIDATIONS ---
    if (!username || username.length < 3) {
        errorBox.textContent = 'Username must be at least 3 characters.';
        errorBox.style.display = 'block';
        return;
    }
    const usernameRegex = /^[a-zA-Z0-9_\-]+$/;
    if (!usernameRegex.test(username)) {
        errorBox.textContent = 'Username can only contain letters, numbers, hyphens, and underscores.';
        errorBox.style.display = 'block';
        return;
    }
    if (!dob) {
        errorBox.textContent = 'Please enter your Date of Birth.';
        errorBox.style.display = 'block';
        return;
    }
    if (age < 1 || age > 120) {
        errorBox.textContent = 'Please enter a valid Date of Birth resulting in an age between 1 and 120.';
        errorBox.style.display = 'block';
        return;
    }
    if (password !== confirm) {
        errorBox.textContent = 'Passwords do not match.';
        errorBox.style.display = 'block';
        return;
    }
    if (password.length < 6) {
        errorBox.textContent = 'Password must be at least 6 characters.';
        errorBox.style.display = 'block';
        return;
    }

    btnText.style.display = 'none';
    spinner.style.display = 'inline';
    btn.disabled = true;

    try {
        const response = await fetch(`${API_BASE_URL}/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                full_name, username, password, role, address, sex, age, dob, barangay, contact_number
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Registration failed. Please try again.');
        }

        if (role === 'staff') {
            successBox.textContent = 'Account created! Since you registered as MAO Staff, your account is pending Admin approval. You may log in as a Farmer in the meantime. Redirecting...';
        } else {
            successBox.textContent = 'Account created successfully! Redirecting to login page...';
        }
        successBox.style.display = 'block';
        
        setTimeout(() => { window.location.href = 'login.html'; }, 2000);

    } catch (err) {
        errorBox.textContent = err.message;
        errorBox.style.display = 'block';
    } finally {
        btnText.style.display = 'inline';
        spinner.style.display = 'none';
        btn.disabled = false;
    }
});
