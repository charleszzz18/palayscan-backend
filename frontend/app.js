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
    const infectedArea = data.infected_area_pct !== undefined ? parseFloat(data.infected_area_pct).toFixed(1) : Math.max(0, (100 - parseFloat(healthScore))).toFixed(1);
    
    const primaryDisease = data.primary_disease || (data.confirmed_diseases && data.confirmed_diseases[0]) || (data.visual_matches && data.visual_matches[0] && data.visual_matches[0].name) || (data.diseases && data.diseases[0]) || "Healthy";
    const primaryDiseaseTL = data.primary_disease_tl || primaryDisease;
    const severityLabel = data.severity_label || (data.is_healthy ? "Healthy" : "Mild / Early Stage");
    const whyDetected = data.why_detected || "The AI system detected distinctive discoloration and lesion patterns on the leaf blade.";
    const diseaseSymptom = data.disease_symptom || "Necrotic lesion spots observed on the leaf surface.";
    const isHealthy = data.is_healthy || primaryDisease === "Healthy";
    const hotspots = data.lesion_hotspots || [];
    const previewRawSrc = sessionStorage.getItem('previewImageSrc') || '';

    // 4.1 Compile Rice Health percentage radial card
    let resultHTML = `<h3>Analysis Report</h3>
        <div class="score-container">
            <div class="score-circle ${healthScore > 50 ? 'healthy' : 'unhealthy'}" style="--score-percent: ${healthScore}; --score-color: ${healthScore > 50 ? 'var(--primary)' : 'var(--danger)'}">
                <span class="score-value">${healthScore}%</span>
                <span class="score-label">Rice Health Score</span>
            </div>
        </div>`;

    // 4.2 Primary Diagnosis Card (Clean, Non-dizzying presentation)
    resultHTML += `
        <div class="primary-diagnosis-card ${isHealthy ? 'healthy' : 'unhealthy'}">
            <div class="diag-card-header">
                <div class="diag-title-wrap">
                    <span style="font-size:0.8rem; font-weight:700; color:${isHealthy ? '#15803d' : '#ef4444'}; text-transform:uppercase; letter-spacing:0.5px;">
                        ${isHealthy ? '✅ Crop Health Status' : '⚠️ Primary Disease Identified'}
                    </span>
                    <h4>${primaryDisease}</h4>
                    <span class="diag-local-name">${primaryDiseaseTL}</span>
                </div>
                <span class="diag-badge ${
                    isHealthy ? 'severity-healthy' :
                    severityLabel.toLowerCase().includes('mild') ? 'severity-mild' :
                    severityLabel.toLowerCase().includes('moderate') ? 'severity-moderate' : 'severity-severe'
                }">${severityLabel}</span>
            </div>

            <div class="diag-why-box">
                <p style="margin:0 0 6px 0;"><strong>🔍 Why this was detected:</strong> ${whyDetected}</p>
                <p style="margin:0; font-size:0.88rem; color:#64748b;"><strong>Typical Symptoms:</strong> ${diseaseSymptom}</p>
            </div>

            <div class="diag-card-footer">
                ${isHealthy ? '' : (
                    primaryDisease.toLowerCase().includes('rust')
                        ? `<button class="info-btn disabled" disabled style="background:#64748b; color:#fff; cursor:not-allowed; opacity:0.85;">Update Coming Soon</button>`
                        : `<button class="info-btn" onclick="window.location.href='disease-info.html?disease=${encodeURIComponent(primaryDisease)}'">Detailed Treatment Guide &rarr;</button>`
                )}
            </div>

            ${(data.visual_matches && data.visual_matches.length > 1) ? `
            <details class="secondary-differential-box">
                <summary>🔬 Secondary AI Model Considerations (${data.visual_matches.length - 1} other)</summary>
                <p style="margin:8px 0 4px 0; font-size:0.85rem; color:#64748b;">The AI evaluated other possibilities with low probability:</p>
                <ul style="margin:4px 0 0 0; padding-left:18px;">
                    ${data.visual_matches.slice(1).map(m => `
                        <li><strong>${m.name}</strong>: ${(parseFloat(m.similarity) * 100).toFixed(0)}% probability</li>
                    `).join('')}
                </ul>
            </details>` : ''}
        </div>`;

    // 4.3 Diagnostic Area highlighting with Interactive Hotspots & Hover/Tap Inspector
    if (data.highlighted_image) {
        resultHTML += `
            <div class="highlighted-image-container">
                <div class="diag-header-row">
                    <div>
                        <h4>Diagnostic Visualization</h4>
                        <p class="diag-subtitle">${isHealthy ? 'Scanned image shows no severe pathogen damage.' : 'Hover or tap over the red highlights to inspect why this spot was flagged.'}</p>
                    </div>
                    <div class="image-toggle-controls">
                        <button type="button" id="btnShowMask" class="layer-toggle-btn active">🔴 Red Highlight</button>
                        <button type="button" id="btnShowOriginal" class="layer-toggle-btn">🍃 Original Leaf</button>
                    </div>
                </div>

                <div class="interactive-scan-wrapper" id="scanViewer">
                    <img id="activeScanImg" src="${data.highlighted_image}" alt="Scanned Rice Leaf" class="highlight-img" />

                    ${(!isHealthy && hotspots.length > 0) ? `
                    <div class="hotspots-layer" id="hotspotsLayer">
                        ${hotspots.map(h => `
                            <div class="lesion-hotspot-pin"
                                 style="left: ${h.x}%; top: ${h.y}%;"
                                 data-id="${h.id}"
                                 data-x="${h.x}"
                                 data-y="${h.y}"
                                 title="Inspect lesion #${h.id}">
                                <span class="pin-ring"></span>
                                <span class="pin-dot"></span>
                            </div>
                        `).join('')}
                    </div>` : ''}

                    <!-- Interactive Popover Card -->
                    <div id="lesionInspectionPopover" class="lesion-popover" style="display: none;">
                        <div class="popover-header">
                            <span class="popover-tag">🔬 Lesion Inspector</span>
                            <button class="popover-close-btn" id="closePopoverBtn" type="button">&times;</button>
                        </div>
                        <div class="popover-body">
                            <h5 class="popover-disease">${primaryDisease}</h5>
                            <p class="popover-why"><strong>Why this spot:</strong> ${whyDetected}</p>
                            <div class="popover-specs">
                                <div><strong>Key Signs:</strong> ${diseaseSymptom}</div>
                                <span class="popover-damage">Affected leaf area: ${infectedArea}%</span>
                            </div>
                        </div>
                        <div class="popover-footer">
                            <a href="disease-info.html?disease=${encodeURIComponent(primaryDisease)}" class="popover-link-btn">View Treatment Guide &rarr;</a>
                        </div>
                    </div>
                </div>
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

    // --- 4.5 BIND INTERACTIVE LESION INSPECTION EVENTS ---
    initInteractiveInspection(data, previewRawSrc);

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

// --- 7. INTERACTIVE LESION INSPECTION LOGIC ---
function initInteractiveInspection(data, previewRawSrc) {
    const activeScanImg = document.getElementById("activeScanImg");
    const btnShowMask = document.getElementById("btnShowMask");
    const btnShowOriginal = document.getElementById("btnShowOriginal");
    const hotspotsLayer = document.getElementById("hotspotsLayer");
    const popover = document.getElementById("lesionInspectionPopover");
    const closePopoverBtn = document.getElementById("closePopoverBtn");
    const scanViewer = document.getElementById("scanViewer");

    if (!scanViewer) return;

    // 1. Layer switcher toggle (Red Mask vs Original Leaf)
    if (btnShowMask && btnShowOriginal && activeScanImg) {
        btnShowMask.addEventListener("click", () => {
            activeScanImg.src = data.highlighted_image;
            btnShowMask.classList.add("active");
            btnShowOriginal.classList.remove("active");
            if (hotspotsLayer) hotspotsLayer.style.display = "block";
        });

        btnShowOriginal.addEventListener("click", () => {
            const rawSrc = previewRawSrc || data.highlighted_image;
            activeScanImg.src = rawSrc;
            btnShowOriginal.classList.add("active");
            btnShowMask.classList.remove("active");
            if (hotspotsLayer) hotspotsLayer.style.display = "none";
            if (popover) popover.style.display = "none";
        });
    }

    // 2. Popover close
    if (closePopoverBtn && popover) {
        closePopoverBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            popover.style.display = "none";
            document.querySelectorAll(".lesion-hotspot-pin").forEach(p => p.classList.remove("active"));
        });
    }

    // 3. Hotspot pin inspection (Desktop hover + Mobile touch)
    const pins = document.querySelectorAll(".lesion-hotspot-pin");
    function showPopoverAt(xPct, yPct) {
        if (!popover) return;
        popover.style.display = "block";
        
        // Smart bounds positioning
        if (xPct > 55) {
            popover.style.left = "auto";
            popover.style.right = Math.max(4, 100 - xPct + 3) + "%";
        } else {
            popover.style.right = "auto";
            popover.style.left = Math.max(4, xPct + 3) + "%";
        }

        if (yPct > 55) {
            popover.style.top = "auto";
            popover.style.bottom = Math.max(4, 100 - yPct + 3) + "%";
        } else {
            popover.style.bottom = "auto";
            popover.style.top = Math.max(4, yPct + 3) + "%";
        }
    }

    pins.forEach(pin => {
        const x = parseFloat(pin.dataset.x);
        const y = parseFloat(pin.dataset.y);

        pin.addEventListener("mouseenter", () => {
            showPopoverAt(x, y);
            pins.forEach(p => p.classList.remove("active"));
            pin.classList.add("active");
        });

        pin.addEventListener("click", (e) => {
            e.stopPropagation();
            showPopoverAt(x, y);
            pins.forEach(p => p.classList.remove("active"));
            pin.classList.add("active");
        });
    });

    // Auto open the first lesion pin briefly as a visual hint for farmers
    if (pins.length > 0) {
        setTimeout(() => {
            const firstPin = pins[0];
            const x = parseFloat(firstPin.dataset.x);
            const y = parseFloat(firstPin.dataset.y);
            showPopoverAt(x, y);
            firstPin.classList.add("active");
        }, 600);
    }

    // Tap anywhere on image viewer to close if clicking outside pin and popover
    scanViewer.addEventListener("click", (e) => {
        if (popover && !popover.contains(e.target) && !e.target.closest(".lesion-hotspot-pin")) {
            popover.style.display = "none";
            pins.forEach(p => p.classList.remove("active"));
        }
    });
}

