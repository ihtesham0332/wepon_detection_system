/* -------------------------------------------------------------
   SENTRY VISION - COMPREHENSIVE FRONTEND LOGIC (SSE & AUDIO SYNTH)
   ------------------------------------------------------------- */

// State Management
let eventSource = null;
let audioEnabled = true;
let isStreaming = false;
let flashTimeout = null;
let currentSettingsTimeout = null;

// UI Elements
const elStatusDot = document.getElementById('status-dot');
const elStatusText = document.getElementById('status-text');
const elModelBadge = document.getElementById('model-badge-text');
const elFpsCounter = document.getElementById('fps-counter');

const elVideoFeed = document.getElementById('video-feed');
const elVideoPlaceholder = document.getElementById('video-placeholder');
const elSirenFlash = document.getElementById('siren-flash');

const elBtnWebcam = document.getElementById('btn-webcam');
const elBtnDefaultVideo = document.getElementById('btn-default-video');
const elBtnStopStream = document.getElementById('btn-stop-stream');
const elBtnToggleSound = document.getElementById('btn-toggle-sound');
const elSoundIcon = document.getElementById('sound-icon');

const elUploadInput = document.getElementById('video-upload-input');
const elBtnTriggerUpload = document.getElementById('btn-trigger-upload');
const elUploadProgressContainer = document.getElementById('upload-progress-container');
const elUploadProgressFill = document.getElementById('upload-progress-fill');
const elUploadProgressPercent = document.getElementById('upload-progress-percent');

const elAlertsStream = document.getElementById('alerts-stream');
const elConsoleEmpty = document.getElementById('console-empty');
const elBtnClearConsole = document.getElementById('btn-clear-console');

const elHistoryGallery = document.getElementById('history-gallery');
const elGalleryEmpty = document.getElementById('gallery-empty');
const elBtnRefreshHistory = document.getElementById('btn-refresh-history');

// Modal Elements
const elLightboxModal = document.getElementById('lightbox-modal');
const elModalCloseBackdrop = document.getElementById('modal-close-backdrop');
const elBtnCloseModal = document.getElementById('btn-close-modal');
const elModalImg = document.getElementById('modal-img');
const elModalTitle = document.getElementById('modal-title');
const elModalTimestamp = document.getElementById('modal-timestamp');
const elModalDesc = document.getElementById('modal-desc');

// Settings Modal Elements
const elSettingsModal = document.getElementById('settings-modal');
const elBtnTriggerSettings = document.getElementById('btn-trigger-settings');
const elBtnCloseSettings = document.getElementById('btn-close-settings');
const elSettingsCloseBackdrop = document.getElementById('settings-close-backdrop');

// Sliders
const elConfPerson = document.getElementById('conf_person');
const elValConfPerson = document.getElementById('val_conf_person');
const elConfBag = document.getElementById('conf_bag');
const elValConfBag = document.getElementById('val_conf_bag');
const elConfGun = document.getElementById('conf_gun');
const elValConfGun = document.getElementById('val_conf_gun');
const elProximity = document.getElementById('proximity');
const elValProximity = document.getElementById('val_proximity');

// --- WEB AUDIO API ALARM SYNTHESIZER ---
class AlarmSiren {
    constructor() {
        this.ctx = null;
        this.oscillator1 = null;
        this.oscillator2 = null;
        this.gainNode = null;
        this.isPlaying = false;
    }

    init() {
        if (this.ctx) return;
        // Instantiate browser Audio Context
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        this.ctx = new AudioContextClass();
    }

    start() {
        if (!audioEnabled) return;
        this.init();
        if (this.isPlaying) return;

        // Resume context if suspended (browser security policy)
        if (this.ctx.state === 'suspended') {
            this.ctx.resume();
        }

        // Create Nodes
        this.oscillator1 = this.ctx.createOscillator();
        this.oscillator2 = this.ctx.createOscillator();
        this.gainNode = this.ctx.createGain();

        // Configure oscillators for an alarming sound (dual detuned saw/square wave)
        this.oscillator1.type = 'sawtooth';
        this.oscillator2.type = 'square';
        
        // Modulate frequency over time (Siren effect: alternating pitch)
        const now = this.ctx.currentTime;
        this.oscillator1.frequency.setValueAtTime(600, now);
        this.oscillator2.frequency.setValueAtTime(605, now);
        
        // Pitch swing modulation
        let timeIdx = 0;
        this.intervalId = setInterval(() => {
            if (!this.isPlaying) return;
            const t = this.ctx.currentTime;
            // Alternates pitches up and down rapidly
            const pitch = (timeIdx % 2 === 0) ? 950 : 600;
            this.oscillator1.frequency.exponentialRampToValueAtTime(pitch, t + 0.25);
            this.oscillator2.frequency.exponentialRampToValueAtTime(pitch + 5, t + 0.25);
            timeIdx++;
        }, 300);

        // Volume control
        this.gainNode.gain.setValueAtTime(0.08, now); // safe volume

        // Connections
        this.oscillator1.connect(this.gainNode);
        this.oscillator2.connect(this.gainNode);
        this.gainNode.connect(this.ctx.destination);

        // Start playing
        this.oscillator1.start(now);
        this.oscillator2.start(now);
        this.isPlaying = true;
    }

    stop() {
        if (!this.isPlaying) return;
        clearInterval(this.intervalId);
        
        try {
            this.oscillator1.stop();
            this.oscillator2.stop();
            this.oscillator1.disconnect();
            this.oscillator2.disconnect();
            this.gainNode.disconnect();
        } catch (e) {
            // Ignore if already stopped
        }

        this.isPlaying = false;
    }
}

const sirenPlayer = new AlarmSiren();

// --- STREAM STATE SYNC ON LOAD ---
async function checkSystemStatus() {
    try {
        const response = await fetch('/api/status');
        const state = await response.json();
        
        // Update model and sliders
        elModelBadge.textContent = state.coco_model ? `Active: ${state.coco_model}` : "COCO Loading...";
        
        elConfPerson.value = state.current_thresholds.conf_person;
        elValConfPerson.textContent = `${Math.round(state.current_thresholds.conf_person * 100)}%`;
        
        elConfBag.value = state.current_thresholds.conf_bag;
        elValConfBag.textContent = `${Math.round(state.current_thresholds.conf_bag * 100)}%`;
        
        elConfGun.value = state.current_thresholds.conf_gun;
        elValConfGun.textContent = `${Math.round(state.current_thresholds.conf_gun * 100)}%`;
        
        elProximity.value = state.current_thresholds.proximity_px;
        elValProximity.textContent = `${state.current_thresholds.proximity_px}px`;

        if (state.running) {
            setStreamingUI(true);
            connectAlertsSSE();
        } else {
            setStreamingUI(false);
        }
    } catch (e) {
        console.error("Failed to connect with App Server:", e);
    }
}

// --- VIDEO STREAM CONTROL FUNCTIONS ---
function setStreamingUI(streaming) {
    isStreaming = streaming;
    if (streaming) {
        if (elStatusDot) elStatusDot.className = "status-dot online";
        if (elStatusText) {
            elStatusText.textContent = "MONITORING ACTIVE";
            elStatusText.style.color = "var(--text-main)";
        }
        
        // Hide processed video download button when starting a new stream
        const elDownloadBtn = document.getElementById('btn-download-processed');
        if (elDownloadBtn) elDownloadBtn.classList.add('hidden');
        
        // Show video feed image, hide placeholder
        if (elVideoFeed) {
            elVideoFeed.src = "/video_feed?t=" + new Date().getTime();
            elVideoFeed.classList.remove('hidden');
        }
        if (elVideoPlaceholder) elVideoPlaceholder.classList.add('hidden');
        
        if (elBtnWebcam) elBtnWebcam.disabled = true;
        if (elBtnDefaultVideo) elBtnDefaultVideo.disabled = true;
        if (elBtnTriggerUpload) elBtnTriggerUpload.disabled = true;
        if (elBtnStopStream) elBtnStopStream.disabled = false;
    } else {
        if (elStatusDot) elStatusDot.className = "status-dot offline";
        if (elStatusText) {
            elStatusText.textContent = "OFFLINE";
            elStatusText.style.color = "var(--text-main)";
        }
        if (elFpsCounter) elFpsCounter.textContent = "0.0";
        
        // Hide video feed image, show placeholder
        if (elVideoFeed) {
            elVideoFeed.src = "";
            elVideoFeed.classList.add('hidden');
        }
        if (elVideoPlaceholder) elVideoPlaceholder.classList.remove('hidden');
        
        if (elBtnWebcam) elBtnWebcam.disabled = false;
        if (elBtnDefaultVideo) elBtnDefaultVideo.disabled = false;
        if (elBtnTriggerUpload) elBtnTriggerUpload.disabled = false;
        if (elBtnStopStream) elBtnStopStream.disabled = true;
        
        sirenPlayer.stop();
        if (elSirenFlash) elSirenFlash.classList.remove('active');
    }
}

async function controlStream(action, payload = {}) {
    try {
        const body = { action, ...payload };
        const response = await fetch('/api/control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const result = await response.json();
        
        if (result.status === 'success') {
            if (action.startsWith('start_')) {
                setStreamingUI(true);
                connectAlertsSSE();
            } else {
                setStreamingUI(false);
                disconnectAlertsSSE();
            }
            addLogItem({
                type: 'INFO',
                timestamp: new Date().toLocaleTimeString(),
                message: result.message,
                details: "Source control updated by user action."
            });
            refreshHistory();
        } else {
            alert("Error: " + result.message);
        }
    } catch (e) {
        console.error("Control API communication failed:", e);
    }
}

// --- SSE SYSTEM THREAT LOG CONTROLLER ---
function connectAlertsSSE() {
    if (eventSource) return;
    
    eventSource = new EventSource('/alerts_feed');
    
    eventSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        
        if (data.type === 'PING') return;
        
        if (data.type === 'STREAM_ENDED') {
            setStreamingUI(false);
            disconnectAlertsSSE();
            
            // Show download button if download_url is present
            const elDownloadBtn = document.getElementById('btn-download-processed');
            if (elDownloadBtn && data.download_url) {
                elDownloadBtn.href = data.download_url;
                elDownloadBtn.classList.remove('hidden');
            }
            
            addLogItem({
                type: 'INFO',
                timestamp: new Date().toLocaleTimeString(),
                message: data.message || 'Video processing ended',
                details: data.details || 'You can now download the processed video.'
            });
            return;
        }

        if (data.type === 'SYSTEM') {
            if (data.active_model && elModelBadge) {
                elModelBadge.textContent = `Active: ${data.active_model}`;
            }
            return;
        }

        // Live stats update
        if (data.fps && elFpsCounter) {
            elFpsCounter.textContent = data.fps.toFixed(1);
        }

        // Output log element to screen
        addLogItem(data);
        
        // Alarm triggering
        if (data.type === 'CRITICAL') {
            triggerVisualAlarm();
            sirenPlayer.start();
        } else if (data.type === 'HIGH') {
            triggerVisualAlarm(false); // Orange warning border
            sirenPlayer.stop(); // Gun in scene, but not held by person -> no siren
        } else {
            // Normal logs -> stop sirens and clean overlays
            clearAlarmOverlays();
        }
    };
    
    eventSource.onerror = function() {
        console.warn("Lost SSE alert stream. Attempting reconnection...");
        disconnectAlertsSSE();
        // Retry connection shortly
        setTimeout(() => {
            if (isStreaming) connectAlertsSSE();
        }, 3000);
    };
}

function disconnectAlertsSSE() {
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
}

function triggerVisualAlarm(critical = true) {
    if (flashTimeout) clearTimeout(flashTimeout);
    
    if (elSirenFlash) elSirenFlash.classList.add('active');
    
    if (critical) {
        if (elSirenFlash) elSirenFlash.style.animationName = 'flash-border';
        if (elStatusDot) elStatusDot.className = "status-dot online";
        if (elStatusText) {
            elStatusText.textContent = "CRITICAL THREAT DETECTED";
            elStatusText.style.color = "var(--accent-red)";
        }
    } else {
        // High alert
        if (elSirenFlash) elSirenFlash.style.animationName = 'flash-border'; // Fallback to pulse
        if (elStatusDot) elStatusDot.className = "status-dot online";
        if (elStatusText) {
            elStatusText.textContent = "WARNING: WEAPON IN SCENE";
            elStatusText.style.color = "var(--accent-orange)";
        }
    }
    
    // Auto-cooldown to clear visual flash if no gun frame follows for 1.5 seconds
    flashTimeout = setTimeout(() => {
        clearAlarmOverlays();
    }, 1500);
}

function clearAlarmOverlays() {
    if (elSirenFlash) elSirenFlash.classList.remove('active');
    sirenPlayer.stop();
    if (isStreaming) {
        if (elStatusText) {
            elStatusText.textContent = "MONITORING ACTIVE";
            elStatusText.style.color = "var(--text-main)";
        }
        if (elStatusDot) elStatusDot.className = "status-dot online";
    }
}

// Add log item to the dashboard right side console
function addLogItem(data) {
    if (!elAlertsStream) return; // Silent return if we are not on the dashboard page
    
    if (elConsoleEmpty) elConsoleEmpty.classList.add('hidden');
    
    const item = document.createElement('div');
    const badgeClass = data.type.toLowerCase();
    item.className = `alert-item alert-${badgeClass}`;
    
    let thumbnailHtml = "";
    if (data.snapshot) {
        thumbnailHtml = `
            <div class="alert-thumbnail-container" onclick="openLightbox('${data.snapshot}', '${data.type}', '${data.timestamp}', '${data.details}')">
                <img src="${data.snapshot}" alt="Snapshot" class="alert-thumbnail">
                <div class="alert-thumbnail-overlay">
                    <span class="material-symbols-outlined">zoom_in</span>
                </div>
            </div>
        `;
    }

    item.innerHTML = `
        <div class="alert-item-header">
            <span class="alert-badge">${data.type}</span>
            <span class="alert-time">${data.timestamp}</span>
        </div>
        <div class="alert-msg">${data.message}</div>
        <div class="alert-details">${data.details}</div>
        ${thumbnailHtml}
    `;
    
    elAlertsStream.insertBefore(item, elAlertsStream.firstChild);
    
    // Limit log length to avoid performance degradation
    if (elAlertsStream.children.length > 50) {
        elAlertsStream.removeChild(elAlertsStream.lastChild);
    }
}

// --- DYNAMIC SETTINGS FORM HANDLING ---
function handleSettingsSliderChange() {
    const valPerson = parseFloat(elConfPerson.value);
    const valBag = parseFloat(elConfBag.value);
    const valGun = parseFloat(elConfGun.value);
    const valProx = parseInt(elProximity.value);
    
    elValConfPerson.textContent = `${Math.round(valPerson * 100)}%`;
    elValConfBag.textContent = `${Math.round(valBag * 100)}%`;
    elValConfGun.textContent = `${Math.round(valGun * 100)}%`;
    elValProximity.textContent = `${valProx}px`;
    
    // Debounce the setting push requests to the backend API to prevent slider lag
    if (currentSettingsTimeout) clearTimeout(currentSettingsTimeout);
    currentSettingsTimeout = setTimeout(() => {
        fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                conf_person: valPerson,
                conf_bag: valBag,
                conf_gun: valGun,
                proximity: valProx
            })
        })
        .then(response => response.json())
        .then(result => {
            if (result.status === 'success') {
                addLogItem({
                    type: 'INFO',
                    timestamp: new Date().toLocaleTimeString(),
                    message: 'Engine parameters updated',
                    details: `Person: ${Math.round(valPerson * 100)}%, Bag: ${Math.round(valBag * 100)}%, Gun: ${Math.round(valGun * 100)}%, Proximity: ${valProx}px`
                });
            }
        })
        .catch(err => console.error('Error updating settings:', err));
    }, 250);
}

// --- FILE UPLOADS HANDLING ---
function handleVideoUpload() {
    const file = elUploadInput.files[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append('file', file);
    
    // Show Progress Bar
    elUploadProgressContainer.classList.remove('hidden');
    elUploadProgressFill.style.width = '0%';
    elUploadProgressPercent.textContent = '0%';
    elBtnTriggerUpload.disabled = true;
    
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload', true);
    
    xhr.upload.onprogress = function(e) {
        if (e.lengthComputable) {
            const percent = Math.round((e.loaded / e.total) * 100);
            elUploadProgressFill.style.width = percent + '%';
            elUploadProgressPercent.textContent = percent + '%';
        }
    };
    
    xhr.onload = function() {
        elUploadProgressContainer.classList.add('hidden');
        elBtnTriggerUpload.disabled = false;
        
        if (xhr.status === 200) {
            const res = JSON.parse(xhr.responseText);
            addLogItem({
                type: 'INFO',
                timestamp: new Date().toLocaleTimeString(),
                message: "File uploaded successfully",
                details: `Saved as ${res.filename}`
            });
            
            // Auto start playing the uploaded file
            controlStream('start_file', { type: 'custom', filename: res.filename });
        } else {
            alert("Upload failed. Error response from server.");
        }
    };
    
    xhr.onerror = function() {
        elUploadProgressContainer.classList.add('hidden');
        elBtnTriggerUpload.disabled = false;
        alert("Network communication error occurred during upload.");
    };
    
    xhr.send(formData);
}

// --- SNAPSHOT HISTORY ARCHIVE LOADERS ---
async function refreshHistory() {
    if (!elHistoryGallery) return; // Silent return if not present
    try {
        const response = await fetch('/api/history');
        const data = await response.json();
        
        if (data.status === 'success' && data.history.length > 0) {
            if (elGalleryEmpty) elGalleryEmpty.classList.add('hidden');
            elHistoryGallery.innerHTML = "";
            
            const isPageGrid = elHistoryGallery.classList.contains('history-page-grid');
            
            data.history.forEach(item => {
                const card = document.createElement('div');
                card.className = isPageGrid ? "history-card history-page-card" : "history-card";
                card.onclick = () => openLightbox(item.snapshot, item.type, item.timestamp, item.message);
                
                const badgeClass = item.type === 'CRITICAL' ? 'badge-critical' : 'badge-high';
                
                card.innerHTML = `
                    <div class="history-card-img-wrapper">
                        <img src="${item.snapshot}" alt="Threat Snapshot" class="history-card-img">
                        <span class="history-badge ${badgeClass}">${item.type}</span>
                    </div>
                    <div class="history-card-meta">
                        <span class="history-card-time">${item.timestamp}</span>
                        <span class="history-card-desc">${item.message}</span>
                    </div>
                `;
                elHistoryGallery.appendChild(card);
            });
        } else {
            if (elGalleryEmpty) elGalleryEmpty.classList.remove('hidden');
            elHistoryGallery.innerHTML = `<div class="gallery-empty-state"><p>No critical event snapshots archived yet.</p></div>`;
        }
    } catch (e) {
        console.error("Failed to load snapshot gallery:", e);
    }
}

// --- LIGHTBOX MODAL TRIGGER ---
function openLightbox(imgSrc, type, timestamp, desc) {
    elModalImg.src = imgSrc;
    elModalTitle.textContent = `${type} THREAT EVENT`;
    elModalTitle.className = type === 'CRITICAL' ? 'text-red-glow' : 'color-orange';
    elModalTimestamp.textContent = `Timestamp: ${timestamp}`;
    elModalDesc.textContent = desc;
    
    elLightboxModal.classList.remove('hidden');
}

function closeLightbox() {
    elLightboxModal.classList.add('hidden');
    elModalImg.src = "";
}

function openSettings() {
    if (elSettingsModal) elSettingsModal.classList.remove('hidden');
}

function closeSettings() {
    if (elSettingsModal) elSettingsModal.classList.add('hidden');
}

// --- EVENT BINDINGS ---
window.addEventListener('load', () => {
    // Initial server checking
    checkSystemStatus();
    refreshHistory();
    
    // Sliders
    if (elConfPerson) elConfPerson.addEventListener('input', handleSettingsSliderChange);
    if (elConfBag) elConfBag.addEventListener('input', handleSettingsSliderChange);
    if (elConfGun) elConfGun.addEventListener('input', handleSettingsSliderChange);
    if (elProximity) elProximity.addEventListener('input', handleSettingsSliderChange);
    
    // Video Controls
    if (elBtnWebcam) elBtnWebcam.addEventListener('click', () => controlStream('start_webcam'));
    if (elBtnDefaultVideo) {
        elBtnDefaultVideo.addEventListener('click', () => controlStream('start_file', { type: 'default' }));
    }
    if (elBtnStopStream) elBtnStopStream.addEventListener('click', () => controlStream('stop'));
    
    // Toggle Sound Button
    if (elBtnToggleSound) {
        elBtnToggleSound.addEventListener('click', () => {
            audioEnabled = !audioEnabled;
            if (audioEnabled) {
                if (elSoundIcon) elSoundIcon.textContent = "volume_up";
                elBtnToggleSound.classList.remove('btn-secondary');
                elBtnToggleSound.classList.add('btn-primary');
                // Play a silent chirp to initialize audio context on click
                sirenPlayer.init();
            } else {
                if (elSoundIcon) elSoundIcon.textContent = "volume_off";
                elBtnToggleSound.classList.remove('btn-primary');
                elBtnToggleSound.classList.add('btn-secondary');
                sirenPlayer.stop();
            }
        });
    }

    // File uploads
    if (elBtnTriggerUpload) elBtnTriggerUpload.addEventListener('click', () => elUploadInput.click());
    if (elUploadInput) elUploadInput.addEventListener('change', handleVideoUpload);
    
    // Console controls
    if (elBtnClearConsole) {
        elBtnClearConsole.addEventListener('click', () => {
            if (elAlertsStream) elAlertsStream.innerHTML = "";
            if (elConsoleEmpty) elConsoleEmpty.classList.remove('hidden');
        });
    }
    
    // History controls
    if (elBtnRefreshHistory) elBtnRefreshHistory.addEventListener('click', refreshHistory);
    
    // Lightbox Modal
    if (elBtnCloseModal) elBtnCloseModal.addEventListener('click', closeLightbox);
    if (elModalCloseBackdrop) elModalCloseBackdrop.addEventListener('click', closeLightbox);
    
    // Settings Modal
    if (elBtnTriggerSettings) elBtnTriggerSettings.addEventListener('click', openSettings);
    if (elBtnCloseSettings) elBtnCloseSettings.addEventListener('click', closeSettings);
    if (elSettingsCloseBackdrop) elSettingsCloseBackdrop.addEventListener('click', closeSettings);
    
    // Close modals on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeLightbox();
            closeSettings();
        }
    });
});
