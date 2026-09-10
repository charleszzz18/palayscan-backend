// =========================================================================
// PALAYSCAN - DISEASE DETAILS & RECOVERY VISUALIZATION (disease-info.js)
// =========================================================================
// This script displays the details of a specific disease (symptoms, severity)
// and handles:
// 1. Simulating an "AI Healed & Optimized" recovery view using our backend model.
// 2. Retrieving treatment advice from the MariaDB database via the backend API.

// --- AUTHENTICATION SHIELD (SECURITY) ---
const _token = localStorage.getItem('palayscan_token');
const _user  = JSON.parse(localStorage.getItem('palayscan_user') || 'null');
if (!_token || !_user) {
    window.location.href = 'login.html';
}

// --- 1. LOCAL DISEASE KNOWLEDGE BASE (Tagalog Translations) ---
const diseaseInfo = {
    "Blast": {
        description: "Ang Blast ay sanhi ng fungus. Ito ay isa sa mga pinaka mapanirang sakit ng palay, na nakakaapekto sa mga dahon gamit ang hugis-brilyanteng sugat.",
        image: "images/healthy.png",
        imageAlt: "Blast Disease",
        symptoms: [
            "Mga sugat na hugis brilyante sa mga dahon",
            "Grey centers na may brown na gilid sa mga sugat"
        ],
        severity: "Mataas - Maaaring magdulot ng hanggang 30% na pagkawala ng ani"
    },
    "Brown Spot": {
        description: "Ang Brown Spot ay sanhi ng fungus. Lumilitaw ito bilang maliit, bilog hanggang sa hugis-itlog, kayumanggi na mga sugat sa mga dahon.",
        image: "images/healthy.png",
        imageAlt: "Brown Spot Disease",
        symptoms: [
            "Maliit na bilog hanggang sa hugis-itlog na kayumanggi na mga sugat sa mga dahon",
            "Mga sugat na may kulay-abo hanggang mapuputing mga sentro habang sila ay tumatanda"
        ],
        severity: "Katamtaman hanggang Mataas - Pinakamapinsala sa mga kondisyon na kulang sa sustansya"
    },
    "Blight": {
        description: "Ang Blight ay sanhi ng bacteria. Ang mga sintomas ay nagsisimula bilang mga sugat na nabasa sa mga gilid ng dahon.",
        image: "images/bacterial_leaf_blight.png",
        imageAlt: "Blight Disease",
        symptoms: [
            "Mga sugat na nababad sa tubig sa gilid ng dahon",
            "Mga sugat na nagiging dilaw hanggang puti",
            "Pagkulot ng mga dulo ng dahon"
        ],
        severity: "Mataas - Maaaring bawasan ang ani ng 20-50% sa mga malalang impeksiyo"
    },
    "Leaf Strip": {
        description: "Ang Leaf Strip ay sanhi ng bacteria na lumilikha ng mga maninipis na guhit-guhit na sugat sa dahon.",
        image: "images/healthy.png",
        imageAlt: "Leaf Strip Disease",
        symptoms: [
            "Maninipis at transparent na guhit sa dahon",
            "Mga guhit na nagiging brown paglipas ng panahon"
        ],
        severity: "Katamtaman - Nababawasan ang photosynthetic area ng halaman"
    }
};

// --- 2. URL PARAMETER PARSER ---
// Extracts query parameters (like "?disease=Blast") from the address bar
function getUrlParam(param) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(param);
}

// --- 3. PAGE INITIALIZATION ON DOM LOAD ---
document.addEventListener('DOMContentLoaded', () => {
    const diseaseName = getUrlParam('disease'); // Read selected disease from URL
    
    if (diseaseName && diseaseInfo[diseaseName]) {
        document.getElementById('diseaseName').textContent = diseaseName; // Set Page Title
        const confirmSec = document.getElementById('confirmSection');
        if (confirmSec) confirmSec.style.display = 'block';
        const disease = diseaseInfo[diseaseName]; // Extract disease data block
        
        // Severity CSS mapping helper
        const getSeverityClass = (severity) => {
            if (severity.toLowerCase().includes('mataas')) return 'severity-high'; // Red style
            if (severity.toLowerCase().includes('katamtaman')) return 'severity-medium'; // Orange style
            return 'severity-low'; // Green style
        };

        // Gather scan images stored in browser memory (sessionStorage)
        const analysisData = JSON.parse(sessionStorage.getItem('analysisData'));
        const infectedImage = analysisData ? analysisData.highlighted_image : sessionStorage.getItem('previewImageSrc');
        const rawImage = sessionStorage.getItem('previewImageSrc');

        // Dynamically inject the UI details block
        document.getElementById('diseaseContent').innerHTML = `
            <div class="disease-detail-grid">
                <div class="info-card">
                    <h4>📝 Overview</h4>
                    <p style="font-size: 1.1rem; line-height: 1.6; color: #000;">${disease.description}</p>
                    <div class="severity-badge ${getSeverityClass(disease.severity)}">Severity: ${disease.severity.split(' - ')[0]}</div>
                    <p style="margin-top: 20px; font-size: 0.95rem; opacity: 0.6; font-style: italic;">${disease.severity.split(' - ')[1] || ''}</p>
                </div>
                <div class="info-card">
                    <h4>🔍 Common Symptoms</h4>
                    <ul class="symptoms-list">
                        ${disease.symptoms.map(symptom => `<li>${symptom}</li>`).join('')}
                    </ul>
                </div>
            </div>`;
            
        document.getElementById('beforeImageContainer').innerHTML = `
            <div class="info-card" style="height: 100%; display: flex; flex-direction: column;">
                <h4>🦠 Current Condition</h4>
                <p style="margin-bottom: 24px; opacity: 0.7;">This is the leaf you submitted for analysis.</p>
                <div style="position: relative; max-width: 600px; margin: auto auto 0 auto; width: 100%;">
                    <span class="outcome-badge" style="background: var(--danger); left: 15px;">Before (Infected)</span>
                    <img src="${infectedImage}" class="disease-image-premium">
                </div>
            </div>
        `;

        document.getElementById('harvestProjection').innerHTML = `
            <div class="info-card" style="height: 100%; display: flex; flex-direction: column;">
                <h4>🌾 Harvest Projection</h4>
                <p style="margin-bottom: 24px; opacity: 0.7;">Compare your leaf with the healthy projection.</p>
                <div style="position: relative; max-width: 600px; margin: auto auto 0 auto; width: 100%;">
                    <span id="healedBadge" class="outcome-badge" style="background: var(--primary); right: 15px;">Healed & Optimized</span>
                    <img id="outcomeImage" src="${rawImage}" class="disease-image-premium healthy-recovery-filter">
                </div>
            </div>`;

        // Apply AI recovery simulation using the original uploaded image
        const userImageBase64 = sessionStorage.getItem('previewImageSrc');
        if (userImageBase64) { 
            applyAIHealing(userImageBase64); 
        }

        // Attach listener to load recommended treatment advice from the database
        document.getElementById('selectDiseaseBtn').addEventListener('click', () => { 
            showRecommendedActions(diseaseName); 
        });
    } else {
        const confirmSec = document.getElementById('confirmSection');
        if (confirmSec) confirmSec.style.display = 'none';
        const recActions = document.getElementById('recommendedActions');
        if (recActions) recActions.style.display = 'none';

        if (diseaseName && diseaseName.toLowerCase().includes('rust')) {
            document.getElementById('diseaseName').textContent = diseaseName;
            document.getElementById('diseaseContent').innerHTML = `
                <div class="error-message" style="text-align: center; padding: 60px;">
                    <h3 style="margin-bottom: 12px; color: #1e293b;">Rust Disease Update Coming Soon</h3>
                    <p style="color: #64748b; max-width: 500px; margin: 0 auto; line-height: 1.6;">We are currently gathering more training samples and verified treatment guidelines for Rust. Detailed symptoms, overview, and harvest projection will be available in the next update.</p>
                </div>`;
        } else {
            document.getElementById('diseaseContent').innerHTML = `<div class="error-message"><p>Disease information not found.</p></div>`;
        }
    }
});

// Helper: Synchronously convert a base64 Data URL to a Blob
function dataURLtoBlob(dataurl) {
    const arr = dataurl.split(',');
    const mime = arr[0].match(/:(.*?);/)[1];
    const bstr = atob(arr[1]);
    let n = bstr.length;
    const u8arr = new Uint8Array(n);
    while (n--) {
        u8arr[n] = bstr.charCodeAt(n);
    }
    return new Blob([u8arr], { type: mime });
}

// --- 4. AI IMAGE HEALING LOGIC ---
// Sends the farmer's raw leaf image to the Flask backend (/ai-heal route)
// to simulate and generate an optimized green, healthy version of their crop.
async function applyAIHealing(base64Image) {
    const outcomeImg = document.getElementById('outcomeImage');
    const badge = document.getElementById('healedBadge');
    if (!outcomeImg || !badge) return;

    try {
        badge.textContent = "Processing...";
        
        // Convert the base64 data URL into a binary file (Blob)
        let blob;
        if (base64Image.startsWith('data:')) {
            blob = dataURLtoBlob(base64Image);
        } else {
            const fetchResponse = await fetch(base64Image);
            blob = await fetchResponse.blob();
        }
        
        // Pack the blob into FormData for standard file uploading
        const formData = new FormData();
        formData.append('image', blob, 'rice.jpg');

        // Post the file to the backend server dynamically
        const response = await fetch(`${API_BASE_URL}/ai-heal`, { 
            method: 'POST', 
            headers: {
                'Authorization': `Bearer ${_token}`
            },
            body: formData 
        });

        if (response.ok) {
            const data = await response.json();
            outcomeImg.src = data.healed_image; // Set the simulated healthy image source
            outcomeImg.classList.remove('healthy-recovery-filter'); // Remove fallback filter
            badge.textContent = "Healed & Optimized";
        } else {
            console.error("AI Healing failed with status:", response.status);
            badge.textContent = "Preview Mode";
        }
    } catch (err) {
        console.error("AI Healing failed:", err);
        badge.textContent = "Preview Mode";
    }
}

// --- 5. DATABASE TREATMENT ADVICE FETCHER ---
// Queries the Flask backend (`/disease-advice`) to retrieve the list
// of custom treatment guidelines stored in the MariaDB `disease_advice` table.
async function showRecommendedActions(diseaseName) {
    try {
        const container = document.getElementById('recommendedActions');
        const listDiv = document.getElementById('actionsList');
        
        container.style.display = 'block'; // Make advice block visible
        listDiv.innerHTML = `<div style="text-align: center; padding: 40px;"><div class="loading-spinner"></div><p>Kinukuha ang mga hakbang...</p></div>`;

        // Request recommendations from Flask
        const response = await fetch(`${API_BASE_URL}/disease-advice?disease=${encodeURIComponent(diseaseName)}`);
        const data = await response.json();

        if (data.advice && data.advice.length > 0) {
            // Populate container with styled Tagalog advice cards
            listDiv.innerHTML = `
                <div class="premium-advice-header">
                    <h3>Mga Hakbang sa Paggamot</h3>
                    <p>Sundin para sa ${diseaseName}</p>
                </div>
                <div class="action-steps">
                    ${data.advice.map((tip, index) => `
                        <div class="action-step-card">
                            <div class="step-number">${index + 1}</div>
                            <p>${tip}</p>
                        </div>
                    `).join('')}
                </div>`;
            
            // Smoothly scroll down to recommendations
            container.scrollIntoView({ behavior: 'smooth' });
        } else {
            listDiv.innerHTML = `
                <div class="premium-advice-header">
                    <h3>Mga Hakbang sa Paggamot</h3>
                    <p>Sundin para sa ${diseaseName}</p>
                </div>
                <div class="action-steps">
                    <div class="action-step-card">
                        <div class="step-number">1</div>
                        <p>Kumonsulta sa inyong lokal na Agriculture Officer para sa tamang gamot at gabay laban sa ${diseaseName}.</p>
                    </div>
                </div>`;
            container.scrollIntoView({ behavior: 'smooth' });
        }
    } catch (error) {
        console.error("Failed to load disease advice:", error);
        listDiv.innerHTML = `
            <div style="text-align:center; padding: 20px;">
                <p style="color:#d9534f; margin-bottom: 10px;">Hindi makuha ang mga hakbang. Pakisubukang muli.</p>
                <button onclick="showRecommendedActions('${diseaseName}')" class="secondary-btn" style="padding: 8px 16px; border-radius: 6px; cursor: pointer;">Subukan Muli</button>
            </div>`;
    }
}