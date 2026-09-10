// =========================================================================
// PALAYSCAN - MAIN ANALYZER CONTROL SYSTEM (app.js)
// =========================================================================
// This script orchestrates the entire image uploading, analysis, and results
// visualization pipeline. It is responsible for:
// 1. Validating authentication (Auth Guard) to secure the page.
// 2. Initializing file inputs, drag-and-drop triggers, and preview renders.
// 3. Gathering ambient metadata: GPS-based weather reports (Open-Meteo API).
// 4. Transporting base64 image packages to the Python Flask server (/upload).
// 5. Generating interactive reports and download layouts (html2pdf PDF exporter).
// 6. Connecting farmers to Municipal Agriculture Office experts via Facebook Messenger.

// --- 1. AUTHENTICATION SHIELD (SECURITY) ---
// If the user's browser does not hold an authentication token (they haven't logged in),
// redirect them instantly back to the login screen.
const _token = localStorage.getItem('palayscan_token');
const _user  = JSON.parse(localStorage.getItem('palayscan_user') || 'null');
if (!_token || !_user) {
    window.location.href = 'login.html';
}

// Helper: Generates standard authorization headers to attach to fetch requests.
// This is critical so the Flask server's token-based middleware (@require_auth) validates the request.
function getAuthHeaders() {
    return { 'Authorization': `Bearer ${_token}` };
}

// Log out helper function. Wipes cached credentials and returns user to login view.
function palayscanLogout() {
    fetch(`${API_BASE_URL}/logout`, { method: 'POST', headers: getAuthHeaders() });
    localStorage.removeItem('palayscan_token');
    localStorage.removeItem('palayscan_user');
    sessionStorage.removeItem('analysisData');
    sessionStorage.removeItem('previewImageSrc');
    window.location.href = 'login.html';
}

// --- 2. MAIN APPLICATION WORKFLOWS & STATE RESTORATION ---
document.addEventListener('DOMContentLoaded', () => {
    
    // --- 2.1 Dynamic Header Actions Render ---
    // If the logged-in user is an admin, render the "⚙️ Admin Panel" button next to "Logout"
    const headerActions = document.getElementById("headerActions");
    if (headerActions && _user) {
        let html = '';
        if (_user.role === 'admin') {
            html += `<a href="admin.html" class="header-action-btn admin-btn" style="text-decoration:none; display:flex; align-items:center; gap:6px; padding:8px 16px; background:#1e293b; color:white; font-size:0.85rem; font-weight:600; border-radius:12px; border:none; cursor:pointer; transition:var(--transition);">⚙️ Admin Panel</a>`;
        }
        html += `<button onclick="palayscanLogout()" class="header-action-btn logout-btn" style="display:flex; align-items:center; gap:6px; padding:8px 16px; background:rgba(239,68,68,0.1); color:#ef4444; border:1px solid rgba(239,68,68,0.2); font-size:0.85rem; font-weight:600; border-radius:12px; cursor:pointer; transition:var(--transition);">🚪 Logout</button>`;
        headerActions.innerHTML = html;
    }

    // --- 2.2 Select DOM elements ---
    const uploadArea = document.getElementById("uploadArea");
    const uploadPreview = document.getElementById("uploadPreview");
    const imageUpload = document.getElementById("imageUpload");
    const previewImage = document.getElementById("previewImage");
    const changeImageBtn = document.getElementById("changeImageBtn");

    // --- 2.3 Interactive Click handler ---
    // Clicking anywhere in the big dashed box triggers the hidden file input picker.
    uploadArea.addEventListener("click", (e) => {
        if (!e.target.closest('button') && !e.target.closest('label')) {
            imageUpload.click();
        }
    });

    // --- 2.4 File Selection & Instant Analysis Execution ---
    imageUpload.addEventListener("change", function () {
        if (this.files && this.files[0]) {
            sessionStorage.removeItem('analysisData'); // Clear previous scan results
            document.getElementById("results").innerHTML = ""; // Clear results display container
            
            const reader = new FileReader();
            reader.onload = function (e) {
                previewImage.src = e.target.result; // Render selected image as preview
                uploadArea.style.display = "none";  // Hide upload box
                uploadPreview.style.display = "block"; // Show preview screen
                
                // Immediately start the analysis process upon uploading
                analyzeImage(null);
            };
            reader.readAsDataURL(this.files[0]); // Read the image as base64 data URL
        }
    });

    // --- 2.5 Reset Flow ---
    // Resets the scanner UI back to its initial state to test another leaf image.
    changeImageBtn.addEventListener("click", function () {
        uploadArea.style.display = "block";
        uploadPreview.style.display = "none";
        imageUpload.value = "";
        sessionStorage.removeItem('analysisData');
        sessionStorage.removeItem('previewImageSrc');
        document.getElementById("results").innerHTML = "";
        document.getElementById("results").style.display = "none";
    });

    // --- 2.6 State Restoration (For Back Button / Refresh Persistence) ---
    // Loads and recovers previous scan states from browser memory so they aren't lost when navigating back from details pages.
    const savedData = sessionStorage.getItem('analysisData');
    const savedImage = sessionStorage.getItem('previewImageSrc');
    if (savedData && savedImage) {
        previewImage.src = savedImage;
        uploadArea.style.display = "none";
        uploadPreview.style.display = "block";
        const resultsDiv = document.getElementById("results");
        resultsDiv.style.display = "block";
        setTimeout(() => { renderResults(JSON.parse(savedData)); }, 100);
    }
});

// --- 3. LIVE COORDINATES & ENVIRONMENTAL TEMPERATURE RETRIEVAL ---
// Pulls live GPS details and requests temperature metrics from Open-Meteo API.
// Helper: Client-side downscaling of large smartphone photos before network upload
function compressImage(file, maxDimension = 1200, quality = 0.85) {
    return new Promise((resolve) => {
        if (!file || !file.type.startsWith('image/')) {
            return resolve(file);
        }
        const reader = new FileReader();
        reader.onload = (e) => {
            const img = new Image();
            img.onload = () => {
                let { width, height } = img;
                if (width <= maxDimension && height <= maxDimension) {
                    return resolve(file); // Already small
                }
                if (width > height) {
                    height = Math.round((height * maxDimension) / width);
                    width = maxDimension;
                } else {
                    width = Math.round((width * maxDimension) / height);
                    height = maxDimension;
                }
                const canvas = document.createElement('canvas');
                canvas.width = width;
                canvas.height = height;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0, width, height);
                canvas.toBlob((blob) => {
                    resolve(blob || file);
                }, 'image/jpeg', quality);
            };
            img.onerror = () => resolve(file);
            img.src = e.target.result;
        };
        reader.onerror = () => resolve(file);
        reader.readAsDataURL(file);
    });
}

// Environmental details are vital as disease spread is heavily dependent on weather (humidity & heat).
async function analyzeImage(e) {
    if (e) e.preventDefault();
    const fileInput = document.getElementById("imageUpload");
    const file = fileInput.files[0];
    const resultsDiv = document.getElementById("results");

    if (!file) {
        alert("Please select an image first!");
        return;
    }

    resultsDiv.style.display = "block";
    resultsDiv.innerHTML = `<div class="loading-status"><div class="loading-spinner"></div><p>Optimizing image and checking weather...</p></div>`;

    let weatherVal = "hot"; // Default fallback
    const warningBox = document.getElementById("weatherWarningBox");
    if (warningBox) warningBox.style.display = "none";

    // GPS Prompter
    const getPosition = () => new Promise((resolve, reject) => {
        if (!navigator.geolocation) reject("No GPS support");
        navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 6000 });
    });

    try {
        // Fetch GPS and Weather
        const position = await getPosition();
        const response = await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${position.coords.latitude}&longitude=${position.coords.longitude}&current=temperature_2m,relative_humidity_2m`);
        const weatherData = await response.json();

        const temp = weatherData.current.temperature_2m;
        const humidity = weatherData.current.relative_humidity_2m;

        weatherVal = temp >= 25 ? "hot" : "cold"; // Categorize based on 25°C boundary

        // Environmental advisory warnings based on current local weather
        if (warningBox) {
            let warningMsg = "";
            if (humidity > 80 && temp > 25) {
                warningMsg = `⚠️ <strong>Early Warning (Live: ${temp}°C, ${humidity}% Humidity):</strong> Prime conditions for <strong>Rice Blast</strong> or <strong>Bacterial Leaf Blight</strong>.`;
            } else if (temp < 20) {
                warningMsg = `⚠️ <strong>Early Warning (Live: ${temp}°C):</strong> Low temperatures detected. Watch out for cold-stress.`;
            }
            if (warningMsg !== "") {
                warningBox.innerHTML = warningMsg;
                warningBox.style.display = "block";
            }
        }
    } catch (err) {
        console.warn("Could not fetch GPS/Weather automatically, defaulting to Hot.", err);
    }

    try {
        // Show status while optimizing and sending
        resultsDiv.innerHTML = `<div class="loading-status"><div class="loading-spinner"></div><p>Analyzing rice leaf...</p></div>`;

        // Downscale image client-side to ensure fast mobile upload and prevent network timeout
        const uploadBlob = await compressImage(file, 1200, 0.85);

        // Assemble form data package (Image file + Weather context)
        const formData = new FormData();
        formData.append("image", uploadBlob, "leaf.jpg");
        formData.append("weather", weatherVal);

        // 90-second timeout to allow Render's free server to wake up from sleep if needed
        const controller = new AbortController();
        const timeoutId  = setTimeout(() => controller.abort(), 90000);

        // Send payload to backend Flask engine
        const response = await fetch(`${API_BASE_URL}/upload`, {
            method: "POST",
            headers: getAuthHeaders(),
            body: formData,
            signal: controller.signal,
        });
        clearTimeout(timeoutId);

        if (response.status === 401) {
            alert("Your session has expired. Please log in again.");
            palayscanLogout();
            return;
        }

        if (!response.ok) {
            const errJson = await response.json().catch(() => ({}));
            throw new Error(errJson.error || `Server returned error (${response.status})`);
        }
        
        const data = await response.json();
        
        // Intercept Phase 1 Validation Errors
        if (data.is_valid === false) {
            resultsDiv.innerHTML = `
                <div class="error-message" style="background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.2); padding: 20px; border-radius: 12px; text-align: center; color: #b45309;">
                    <h3 style="margin-top: 0;">⚠️ Image Validation Failed</h3>
                    <p style="margin-bottom: 15px;">${data.message}</p>
                    <div style="background: white; padding: 15px; border-radius: 8px; text-align: left; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
                        <h4 style="margin: 0 0 10px 0; color: #333;">📸 How to capture the rice leaf properly:</h4>
                        <ul style="margin: 0; padding-left: 20px; color: #555; font-size: 0.9rem; line-height: 1.5;">
                            <li>Focus on a single, clear rice leaf.</li>
                            <li>Ensure the leaf occupies most of the photo.</li>
                            <li><strong>Avoid plain backgrounds</strong> (like white paper, dark soil, or completely brown/black surfaces).</li>
                            <li>A natural field background or holding the leaf against natural light works best!</li>
                        </ul>
                    </div>
                </div>`;
            return;
        }

        // Cache findings locally safely so Safari 5MB QuotaExceededError never breaks the UI
        try {
            sessionStorage.setItem('analysisData', JSON.stringify(data));
            // Only store preview if under 500KB to stay safely within browser quota
            const previewEl = document.getElementById("previewImage");
            const previewSrc = (previewEl && previewEl.src.length < 500000) ? previewEl.src : (data.highlighted_image || '');
            if (previewSrc && previewSrc.length < 500000) {
                sessionStorage.setItem('previewImageSrc', previewSrc);
            }
        } catch (storageErr) {
            console.warn("Storage quota reached, proceeding without session cache:", storageErr);
        }

        renderResults(data);
    } catch (error) {
        if (error.name === 'AbortError') {
            resultsDiv.innerHTML = `<div class="error-message"><p>⏱️ Server request timed out.</p><p>Please try submitting the image again in a few seconds!</p></div>`;
        } else {
            resultsDiv.innerHTML = `<div class="error-message"><p>❌ Error analyzing image</p><p>${error.message || 'Check server connection.'}</p></div>`;
        }
        console.error("Error:", error);
    }
}

// --- 4. RENDER RESULTS INTERFACE ---
// Compiles JSON findings returned by the server into a dynamic, beautiful Glassmorphism report dashboard.
function renderResults(data) {
    console.log("Analysis Data Received:", data);
    const healthScore = (data.health_score * 100).toFixed(1); // Translate 0-1 range to 0-100% scale

    // 4.1 Compile Rice Health percentage radial card
    let resultHTML = `<h3>Analysis Report</h3>
        <div class="score-container">
            <div class="score-circle ${healthScore > 50 ? 'healthy' : 'unhealthy'}" style="--score-percent: ${healthScore}; --score-color: ${healthScore > 50 ? 'var(--primary)' : 'var(--danger)'}">
                <span class="score-value">${healthScore}%</span>
                <span class="score-label">Rice Health Score</span>
            </div>
        </div>`;

    // 4.2 List detected anomalies/diseases and similarity margins
    if (data.visual_matches && data.visual_matches.length > 0) {
        // Populate diseases using MobileNetV2 similarity rankings
        resultHTML += `<div class="visual-matches"><h4>Possible Diseases Detected</h4><ul>
            ${data.visual_matches.map(match => `
                <li>
                    <div class="match-info">
                        <span>${match.name}</span>
                        <div class="similarity-score">
                            <div class="similarity-bar-bg">
                                <div class="similarity-bar" style="width: ${parseFloat(match.similarity) * 100}%"></div>
                            </div>
                            <span>${(parseFloat(match.similarity) * 100).toFixed(0)}% match</span>
                        </div>
                    </div>
                    ${match.name.toLowerCase().includes('rust') ? `<button class="info-btn disabled" disabled style="background:#64748b; color:#fff; cursor:not-allowed; opacity:0.85;">Update Coming Soon</button>` : `<button class="info-btn" onclick="window.location.href='disease-info.html?disease=${encodeURIComponent(match.name)}'">Learn More</button>`}
                </li>
            `).join('')}</ul></div>`;
    } else if (data.diseases && data.diseases.length > 0) {
        // Fallback for color/texture-only heuristic matches
        resultHTML += `<div class="visual-matches"><h4>Possible Diseases Detected</h4><ul>
            ${data.diseases.map(disease => `
                <li>
                    <div class="match-info">
                        <span>${disease}</span>
                        <p style="font-size: 0.8rem; opacity: 0.7;">Detected via visual pattern analysis</p>
                    </div>
                    ${disease.toLowerCase().includes('rust') ? `<button class="info-btn disabled" disabled style="background:#64748b; color:#fff; cursor:not-allowed; opacity:0.85;">Update Coming Soon</button>` : `<button class="info-btn" onclick="window.location.href='disease-info.html?disease=${encodeURIComponent(disease)}'">Learn More</button>`}
                </li>
            `).join('')}</ul></div>`;
    }

    // 4.3 Diagnostic Area highlighting (Visual representation)
    if (data.highlighted_image) {
        resultHTML += `<div class="highlighted-image-container">
            <h4>Diagnostic Visualization</h4>
            <p>Infected areas are highlighted in red for your review.</p>
            <div class="highlight-img-wrapper"><img src="${data.highlighted_image}" alt="Highlights" class="highlight-img"></div>
        </div>`;
    }

    // 4.4 Render bottom control buttons
    resultHTML += `
        <div class="action-footer" style="display: flex; gap: 10px; flex-wrap: wrap; align-items:center;">
            <span style="font-size:0.8rem;color:#666;">👤 ${_user.full_name} &nbsp;|&nbsp; Scan #${data.scan_id || '—'}</span>
            <button id="askExpertBtn" class="secondary-btn" style="flex: 1; min-width: 120px; padding: 10px; background: #fff3e0; color: #e65100; border: 1px solid #ffe0b2; border-radius: 8px; cursor: pointer; font-weight: 600; transition: 0.2s;">👨‍🌾 Ask Expert on Messenger</button>
            <button id="downloadChartBtn" class="analyze-btn" style="flex: 1; min-width: 200px;">Download Full Report</button>
            <button onclick="palayscanLogout()" style="padding:10px 16px;border:1px solid #ddd;border-radius:8px;cursor:pointer;background:#fff;color:#666;font-size:0.85rem;">🚪 Logout</button>
        </div>`;

    document.getElementById("results").innerHTML = resultHTML;
    document.getElementById("results").scrollIntoView({ behavior: 'smooth' });

    // --- 5. PDF REPORT GENERATOR ---
    // Converts the hidden formal template into an A4 PDF booklet.
    document.getElementById("downloadChartBtn").addEventListener("click", () => {
        const element = document.getElementById("pdfReportTemplate");

        if (typeof html2pdf === 'undefined' || !element) {
            window.print(); // Print fallback
            return;
        }

        // --- Populate the formal template ---
        const now = new Date();
        document.getElementById("repScanId").innerText = data.scan_id ? `#${data.scan_id}` : "Pending";
        document.getElementById("repUserId").innerText = _user.full_name || "Unknown User";
        document.getElementById("repDate").innerText = now.toLocaleString();
        document.getElementById("repLocation").innerText = "Location Services Active";
        
        document.getElementById("repScoreValue").innerText = `${healthScore}%`;
        
        let primaryDisease = "Healthy";
        let confidence = "100";
        if (data.visual_matches && data.visual_matches.length > 0) {
            primaryDisease = data.visual_matches[0].name;
            confidence = (parseFloat(data.visual_matches[0].similarity) * 100).toFixed(0);
        } else if (data.diseases && data.diseases.length > 0) {
            primaryDisease = data.diseases[0];
            confidence = "90"; // Heuristic fallback
        }
        
        document.getElementById("repAssessment").innerText = healthScore > 50 ? "Satisfactory field conditions." : "Attention needed. Disease indicators present.";
        document.getElementById("repDiseaseName").innerText = primaryDisease;
        document.getElementById("repConfidenceVal").innerText = `${confidence}%`;
        document.getElementById("repConfFill").style.width = `${confidence}%`;
        document.getElementById("repConfText").innerText = `${confidence}% match confidence based on visual characteristics.`;
        
        document.getElementById("repProfileText").innerText = primaryDisease === "Healthy" 
            ? "No significant disease profiles matched. Plant shows normal growth patterns." 
            : `Visual characteristics strongly match known profiles for ${primaryDisease}.`;
            
        document.getElementById("repVisId").innerText = Date.now().toString(36).toUpperCase();
        document.getElementById("repHighlightImg").src = data.highlighted_image || sessionStorage.getItem('previewImageSrc');
        
        document.getElementById("repRec1").innerText = healthScore > 50 ? "Continue regular watering and fertilization schedule." : `Isolate affected areas immediately to prevent ${primaryDisease} spread.`;
        document.getElementById("repRec2").innerText = healthScore > 50 ? "Monitor crop weekly for any sudden changes." : `Apply recommended treatments for ${primaryDisease} within 48 hours.`;
        
        document.getElementById("repSystemId").innerText = `REP-${data.scan_id || Math.floor(Math.random()*10000)}`;

        const opt = {
            margin: [0, 0], // Margins handled by CSS padding
            filename: `Palayscan_Official_Report_${data.scan_id || 'scan'}.pdf`,
            image: { type: 'jpeg', quality: 0.98 },
            html2canvas: {
                scale: 2, // High DPI rendering
                useCORS: true,
                letterRendering: true,
                scrollY: 0
            },
            jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
        };

        // Make template visible to the renderer
        element.classList.add('active-pdf');

        setTimeout(() => {
            html2pdf().set(opt).from(element).save().then(() => {
                element.classList.remove('active-pdf');
            }).catch(err => {
                console.error("PDF Error:", err);
                element.classList.remove('active-pdf');
                window.print();
            });
        }, 500);
    });

    // --- 6. MESSENGER INTEGRATION (EXPERT-IN-THE-LOOP) ---
    // Helps farmers directly message their diagnostic scan data to the Municipal Agriculture Office page.
    document.getElementById("askExpertBtn").addEventListener("click", () => {
        let detected = "an unknown issue";
        if (data.confirmed_diseases && data.confirmed_diseases.length > 0) detected = data.confirmed_diseases.join(", ");
        else if (data.visual_matches && data.visual_matches.length > 0) detected = data.visual_matches.map(m => m.name).join(", ");
        else if (data.diseases && data.diseases.length > 0) detected = data.diseases.join(", ");

        const message = `Magandang araw po! Ako po si ${_user.full_name}, isang magsasaka na gumagamit ng PALAYSCAN. Batay po sa scan ng app, ang aking palay ay may posibleng sakit na ${detected} (Scan ID: #${data.scan_id || 'N/A'}). Maaari po bang humingi ng payo o kumpirmasyon mula sa inyo?`;

        // Direct Messenger link for predefined Municipal Agriculture Office recipient with text payload pre-loaded
        const messengerLink = `https://m.me/PalayscanBacnotan?text=${encodeURIComponent(message)}`;
        window.open(messengerLink, '_blank');
    });
}
