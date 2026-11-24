/**
 * VisionGuard Lite - Dashboard Client Controller
 * Pure vanilla JavaScript: Zero external dependencies.
 */

let statusPollingInterval = null;
let eventsPollingInterval = null;
let analyticsPollingInterval = null;

// DOM Elements
const btnStart = document.getElementById("btn-start");
const btnStop = document.getElementById("btn-stop");
const cameraPill = document.getElementById("camera-pill");
const cameraStatusText = document.getElementById("camera-status-text");
const mainStatusBadge = document.getElementById("main-status-badge");
const streamOverlayBadge = document.getElementById("stream-overlay-badge");
const statusHint = document.getElementById("status-hint");
const stateTimer = document.getElementById("state-timer");
const statFaces = document.getElementById("stat-faces");
const statSession = document.getElementById("stat-session");
const statPresentTime = document.getElementById("stat-present-time");
const statAbsentTime = document.getElementById("stat-absent-time");

// Break Reminder Elements
const breakBanner = document.getElementById("break-banner");
const breakBannerTitle = document.getElementById("break-banner-title");
const breakBannerDesc = document.getElementById("break-banner-desc");
const breakStateTag = document.getElementById("break-state-tag");
const workTimerText = document.getElementById("work-timer-text");
const workProgressFill = document.getElementById("work-progress-fill");

// Analytics & History Elements
const analyticTotalMonitored = document.getElementById("analytic-total-monitored");
const analyticTimePresent = document.getElementById("analytic-time-present");
const analyticTimeAbsent = document.getElementById("analytic-time-absent");
const analyticFocusRatio = document.getElementById("analytic-focus-ratio");
const hourlyChart = document.getElementById("hourly-chart");
const sessionsTbody = document.getElementById("sessions-tbody");
const eventsTbody = document.getElementById("events-tbody");
const linkExportEvents = document.getElementById("link-export-events");

/**
 * Formats seconds into HH:MM:SS or MM:SS
 */
function formatSeconds(totalSeconds, includeHours = false) {
    if (!totalSeconds || isNaN(totalSeconds) || totalSeconds < 0) {
        return includeHours ? "00:00:00" : "00:00";
    }
    const sec = Math.floor(totalSeconds % 60);
    const min = Math.floor((totalSeconds / 60) % 60);
    const hrs = Math.floor(totalSeconds / 3600);

    const pad = (n) => String(n).padStart(2, "0");

    if (includeHours || hrs > 0) {
        return `${pad(hrs)}:${pad(min)}:${pad(sec)}`;
    }
    return `${pad(min)}:${pad(sec)}`;
}

/**
 * Formats seconds into human-readable "Xh Ym"
 */
function formatHumanDuration(seconds) {
    if (!seconds || isNaN(seconds) || seconds < 0) return "0h 0m";
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    return `${hrs}h ${mins}m`;
}

/**
 * Returns today's date in YYYY-MM-DD
 */
function getTodayDateString() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/**
 * Shows lightweight non-blocking toast notifications
 */
function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transition = "opacity 0.3s ease-out";
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

/**
 * Start Monitoring Handler
 */
async function startMonitoring() {
    btnStart.disabled = true;
    try {
        const response = await fetch("/api/start", { method: "POST" });
        const data = await response.json();

        if (response.ok && data.success) {
            showToast("Monitoring initialized successfully.", "success");
            btnStop.disabled = false;
            const streamImg = document.getElementById("video-stream");
            if (streamImg) {
                streamImg.src = `/video_feed?t=${Date.now()}`;
            }
            updateTelemetryUI(data.telemetry);
            fetchEvents();
            fetchSessions();
            fetchAnalytics();
        } else {
            showToast(data.message || "Failed to start monitoring.", "error");
            btnStart.disabled = false;
        }
    } catch (err) {
        showToast("Network error communicating with server.", "error");
        btnStart.disabled = false;
    }
}

/**
 * Stop Monitoring Handler
 */
async function stopMonitoring() {
    btnStop.disabled = true;
    try {
        const response = await fetch("/api/stop", { method: "POST" });
        const data = await response.json();

        if (response.ok && data.success) {
            showToast("Monitoring stopped. Camera hardware released.", "info");
            btnStart.disabled = false;
            const streamImg = document.getElementById("video-stream");
            if (streamImg) {
                streamImg.src = `/video_feed?t=${Date.now()}`;
            }
            updateTelemetryUI(data.telemetry);
            fetchEvents();
            fetchSessions();
            fetchAnalytics();
        } else {
            showToast(data.message || "Failed to stop monitoring.", "error");
            btnStop.disabled = false;
        }
    } catch (err) {
        showToast("Network error communicating with server.", "error");
        btnStop.disabled = false;
    }
}

/**
 * Break Action Handlers
 */
async function takeBreak() {
    try {
        const response = await fetch("/api/break/take", { method: "POST" });
        const data = await response.json();
        if (data.success) {
            showToast("Break started. Enjoy your rest!", "success");
            fetchStatus();
        }
    } catch (err) {
        showToast("Error starting break.", "error");
    }
}

async function snoozeBreak(minutes = 5) {
    try {
        const response = await fetch("/api/break/snooze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ minutes })
        });
        const data = await response.json();
        if (data.success) {
            showToast(`Break reminder snoozed for ${minutes} minutes.`, "info");
            fetchStatus();
        }
    } catch (err) {
        showToast("Error snoozing break.", "error");
    }
}

async function dismissBreak() {
    try {
        const response = await fetch("/api/break/dismiss", { method: "POST" });
        const data = await response.json();
        if (data.success) {
            showToast("Break reminder dismissed. Focus cycle reset.", "info");
            fetchStatus();
        }
    } catch (err) {
        showToast("Error dismissing break.", "error");
    }
}

/**
 * Polls /api/status and updates DOM telemetry
 */
async function fetchStatus() {
    try {
        const response = await fetch("/api/status");
        if (!response.ok) return;
        const data = await response.json();
        if (data.success && data.telemetry) {
            updateTelemetryUI(data.telemetry);
        }
    } catch (err) {
        // Silently skip transient drops
    }
}

/**
 * Polls /api/events and renders CSV event log
 */
async function fetchEvents() {
    try {
        const response = await fetch("/api/events?limit=8");
        if (!response.ok) return;
        const data = await response.json();
        if (data.success && Array.isArray(data.events)) {
            renderEventsTable(data.events);
        }
    } catch (err) {
        // Silently skip transient drops
    }
}

/**
 * Polls /api/sessions and renders recent sessions table
 */
async function fetchSessions() {
    try {
        const response = await fetch("/api/sessions?limit=6");
        if (!response.ok) return;
        const data = await response.json();
        if (data.success && Array.isArray(data.sessions)) {
            renderSessionsTable(data.sessions);
        }
    } catch (err) {
        // Silently skip transient drops
    }
}

/**
 * Polls /api/analytics and updates daily metrics and 24-hr CSS chart
 */
async function fetchAnalytics() {
    try {
        const response = await fetch("/api/analytics");
        if (!response.ok) return;
        const data = await response.json();
        if (data.success && data.analytics) {
            renderAnalytics(data.analytics);
        }
    } catch (err) {
        // Silently skip transient drops
    }
}

/**
 * Updates UI controls and metric cards with fresh telemetry
 */
function updateTelemetryUI(t) {
    if (!t) return;

    // Button states
    if (t.monitoring) {
        btnStart.disabled = true;
        btnStop.disabled = false;
    } else {
        btnStart.disabled = false;
        btnStop.disabled = true;
    }

    // Camera Active Pill
    if (t.camera_active) {
        cameraPill.className = "status-pill pill-active";
        cameraStatusText.textContent = "Camera Live";
    } else {
        cameraPill.className = "status-pill pill-stopped";
        cameraStatusText.textContent = "Camera Off";
    }

    // Status Badge & Stream Overlay
    const status = t.status || "STOPPED";
    const statusClasses = {
        "PRESENT": "badge-present",
        "ABSENT": "badge-absent",
        "INITIALIZING": "badge-initializing",
        "STOPPED": "badge-stopped"
    };
    const badgeClass = statusClasses[status] || "badge-stopped";

    mainStatusBadge.className = `hero-badge ${badgeClass}`;
    mainStatusBadge.textContent = status;

    streamOverlayBadge.className = `stream-badge ${badgeClass}`;
    streamOverlayBadge.textContent = status;

    // Status Hints
    if (status === "PRESENT") {
        statusHint.textContent = "User face detected within workspace boundary.";
    } else if (status === "ABSENT") {
        statusHint.textContent = "No face detected in workspace for > 3.0s.";
    } else if (status === "INITIALIZING") {
        statusHint.textContent = "Calibrating workspace and checking presence grace period...";
    } else {
        statusHint.textContent = "Monitoring is currently stopped. Click 'Start Monitoring' to begin.";
    }

    // Metrics
    stateTimer.textContent = `In State: ${formatSeconds(t.current_state_duration_seconds)}`;
    statFaces.textContent = t.faces_detected || 0;
    statSession.textContent = formatSeconds(t.session_duration_seconds, true);
    statPresentTime.textContent = formatSeconds(t.total_present_seconds);
    statAbsentTime.textContent = formatSeconds(t.total_absent_seconds);

    // Break Reminder UI
    if (t.break_reminder) {
        updateBreakUI(t.break_reminder);
    }
}

/**
 * Updates Break Reminder Banner & Progress Bar
 */
function updateBreakUI(b) {
    breakStateTag.textContent = b.state;

    // Progress Bar
    const curSec = b.current_work_seconds || 0;
    const targetSec = b.work_interval_seconds || 2700;
    const pct = Math.min(100, Math.round((curSec / targetSec) * 100));
    workProgressFill.style.width = `${pct}%`;
    workTimerText.textContent = `${formatSeconds(curSec)} / ${formatSeconds(targetSec)}`;

    // Banner visibility
    if (b.reminder_active) {
        breakBanner.classList.remove("hidden");
        breakBannerTitle.textContent = "Time for a Healthy Break!";
        const mins = Math.max(1, Math.round(curSec / 60));
        breakBannerDesc.textContent = `You've been focused and working for ${mins} minutes. Take a 5-minute break to rest your eyes and stretch.`;
    } else if (b.state === "ON_BREAK") {
        breakBanner.classList.remove("hidden");
        breakBannerTitle.textContent = `Break in Progress: ${formatSeconds(b.remaining_break_seconds)} remaining`;
        breakBannerDesc.textContent = "Step away from the screen, hydrate, and stretch. Focus tracking will resume when your break completes.";
    } else {
        breakBanner.classList.add("hidden");
    }
}

/**
 * Renders Daily Analytics metrics and 24-hour pure CSS chart
 */
function renderAnalytics(a) {
    if (!a) return;

    analyticTotalMonitored.textContent = formatHumanDuration(a.total_monitored_seconds);
    analyticTimePresent.textContent = formatHumanDuration(a.total_present_seconds);
    analyticTimeAbsent.textContent = formatHumanDuration(a.total_absent_seconds);
    analyticFocusRatio.textContent = `${a.focus_ratio_percent}%`;

    // Render 24-hour bar chart
    if (Array.isArray(a.hourly_activity) && hourlyChart) {
        let html = "";
        a.hourly_activity.forEach((sec, hour) => {
            const minutes = sec / 60.0;
            // Max height is 60 minutes in an hour
            const heightPct = Math.min(100, Math.max(3, (minutes / 60.0) * 100));
            const padH = String(hour).padStart(2, "0");
            const tooltip = `${padH}:00 - ${minutes.toFixed(1)}m present`;

            html += `
                <div class="chart-bar-wrapper" data-tooltip="${tooltip}">
                    <div class="chart-bar" style="height: ${heightPct}%;"></div>
                </div>
            `;
        });
        hourlyChart.innerHTML = html;
    }
}

/**
 * Renders Session History table rows
 */
function renderSessionsTable(sessions) {
    if (!sessions || sessions.length === 0) {
        sessionsTbody.innerHTML = `<tr><td colspan="6" class="empty-state">No sessions recorded yet.</td></tr>`;
        return;
    }

    let html = "";
    sessions.forEach(s => {
        const dur = s.duration_seconds ? formatSeconds(parseFloat(s.duration_seconds)) : "-";
        const pres = s.present_seconds ? formatSeconds(parseFloat(s.present_seconds)) : "-";
        let badgeClass = "event-absent";
        if (s.status === "COMPLETED") {
            badgeClass = "event-present";
        } else if (s.status === "STOPPED_EARLY") {
            badgeClass = "event-initializing";
        }

        html += `
            <tr>
                <td style="font-family: monospace; font-size: 0.76rem;">${s.session_id || "-"}</td>
                <td style="font-family: monospace;">${s.start_time || "-"}</td>
                <td style="font-family: monospace;">${s.end_time || "-"}</td>
                <td style="font-family: monospace;">${dur}</td>
                <td style="font-family: monospace;" class="stat-success">${pres}</td>
                <td><span class="event-badge ${badgeClass}">${s.status || "COMPLETED"}</span></td>
            </tr>
        `;
    });
    sessionsTbody.innerHTML = html;
}

/**
 * Renders CSV transition events table rows
 */
function renderEventsTable(events) {
    if (!events || events.length === 0) {
        eventsTbody.innerHTML = `<tr><td colspan="4" class="empty-state">No events recorded yet.</td></tr>`;
        return;
    }

    let html = "";
    events.forEach(e => {
        const isPresent = e.event_type === "PRESENT";
        const badgeClass = isPresent ? "event-present" : "event-absent";
        const durationFormatted = e.duration_seconds ? `${parseFloat(e.duration_seconds).toFixed(1)}s` : "-";

        html += `
            <tr>
                <td style="font-family: monospace;">${e.timestamp || "-"}</td>
                <td><span class="event-badge ${badgeClass}">${e.event_type}</span></td>
                <td style="font-family: monospace;">${durationFormatted}</td>
                <td>${e.details || "-"}</td>
            </tr>
        `;
    });
    eventsTbody.innerHTML = html;
}

/**
 * Exports CSV events filtered by selected date picker value
 */
function exportEventsCsv() {
    const picker = document.getElementById("export-date-picker");
    const dateVal = picker ? picker.value : "";
    if (dateVal) {
        window.location.href = `/api/export/events?date=${encodeURIComponent(dateVal)}`;
    } else {
        window.location.href = "/api/export/events";
    }
}

/**
 * Updates analytics date tag with localized date string
 */
function updateAnalyticsDateTag() {
    const analyticsDateTag = document.getElementById("analytics-date-tag");
    if (analyticsDateTag) {
        const today = new Date();
        analyticsDateTag.textContent = today.toLocaleDateString(undefined, {
            weekday: "short",
            month: "short",
            day: "numeric",
            year: "numeric"
        });
    }
}

// Initialize Polling & Export Controls on Page Load
window.addEventListener("DOMContentLoaded", () => {
    // Initialize date picker and localized tag
    const todayStr = getTodayDateString();
    const exportDatePicker = document.getElementById("export-date-picker");
    if (exportDatePicker) {
        exportDatePicker.value = todayStr;
    }
    if (linkExportEvents) {
        linkExportEvents.href = `/api/export/events?date=${todayStr}`;
    }
    updateAnalyticsDateTag();

    fetchStatus();
    fetchEvents();
    fetchSessions();
    fetchAnalytics();

    // Lightweight polling intervals: 1000ms status, 2500ms events, 5000ms analytics & sessions
    statusPollingInterval = setInterval(fetchStatus, 1000);
    eventsPollingInterval = setInterval(fetchEvents, 2500);
    analyticsPollingInterval = setInterval(() => {
        fetchSessions();
        fetchAnalytics();
    }, 5000);
});
