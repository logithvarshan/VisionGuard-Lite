
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
 * Formats seconds into human-readable duration
 */
function formatHumanDuration(seconds) {
    if (seconds === null || seconds === undefined || isNaN(seconds) || seconds < 0) {
        return "0h 0m";
    }

    const totalSeconds = Math.floor(seconds);

    if (totalSeconds < 60) {
        return `${totalSeconds}s`;
    }

    const hrs = Math.floor(totalSeconds / 3600);
    const mins = Math.floor((totalSeconds % 3600) / 60);

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
 * Shows lightweight toast notifications
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
 * Safely reads JSON responses from the server
 */
async function readJsonResponse(response) {
    const contentType = response.headers.get("content-type") || "";

    if (!contentType.includes("application/json")) {
        throw new Error("The server returned an unexpected response.");
    }

    return await response.json();
}

/**
 * Start Monitoring Handler
 */
async function startMonitoring() {
    if (!btnStart || !btnStop) return;

    btnStart.disabled = true;

    try {
        const response = await fetch("/api/start", { method: "POST" });
        const data = await readJsonResponse(response);

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
        showToast(err.message || "Network error communicating with server.", "error");
        btnStart.disabled = false;
    }
}

/**
 * Stop Monitoring Handler
 */
async function stopMonitoring() {
    if (!btnStart || !btnStop) return;

    btnStop.disabled = true;

    try {
        const response = await fetch("/api/stop", { method: "POST" });
        const data = await readJsonResponse(response);

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
        showToast(err.message || "Network error communicating with server.", "error");
        btnStop.disabled = false;
    }
}

/**
 * Break Action Handlers
 */
async function takeBreak() {
    try {
        const response = await fetch("/api/break/take", { method: "POST" });
        const data = await readJsonResponse(response);

        if (!response.ok || !data.success) {
            throw new Error(data.message || "Unable to start break.");
        }

        showToast("Break started. Enjoy your rest!", "success");
        fetchStatus();
    } catch (err) {
        showToast(err.message || "Error starting break.", "error");
    }
}

async function snoozeBreak(minutes = 5) {
    try {
        const response = await fetch("/api/break/snooze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ minutes })
        });

        const data = await readJsonResponse(response);

        if (!response.ok || !data.success) {
            throw new Error(data.message || "Unable to snooze reminder.");
        }

        showToast(`Break reminder snoozed for ${minutes} minutes.`, "info");
        fetchStatus();
    } catch (err) {
        showToast(err.message || "Error snoozing break.", "error");
    }
}

async function dismissBreak() {
    try {
        const response = await fetch("/api/break/dismiss", { method: "POST" });
        const data = await readJsonResponse(response);

        if (!response.ok || !data.success) {
            throw new Error(data.message || "Unable to dismiss reminder.");
        }

        showToast("Break reminder dismissed. Focus cycle reset.", "info");
        fetchStatus();
    } catch (err) {
        showToast(err.message || "Error dismissing break.", "error");
    }
}

/**
 * Polling functions
 */
async function fetchStatus() {
    try {
        const response = await fetch("/api/status");

        if (!response.ok) return;

        const data = await readJsonResponse(response);

        if (data.success && data.telemetry) {
            updateTelemetryUI(data.telemetry);
        }
    } catch (err) {
        // Skip temporary network errors.
    }
}

async function fetchEvents() {
    try {
        const response = await fetch("/api/events?limit=8");

        if (!response.ok) return;

        const data = await readJsonResponse(response);

        if (data.success && Array.isArray(data.events)) {
            renderEventsTable(data.events);
        }
    } catch (err) {
        // Skip temporary network errors.
    }
}

async function fetchSessions() {
    try {
        const response = await fetch("/api/sessions?limit=6");

        if (!response.ok) return;

        const data = await readJsonResponse(response);

        if (data.success && Array.isArray(data.sessions)) {
            renderSessionsTable(data.sessions);
        }
    } catch (err) {
        // Skip temporary network errors.
    }
}

async function fetchAnalytics() {
    try {
        const response = await fetch("/api/analytics");

        if (!response.ok) return;

        const data = await readJsonResponse(response);

        if (data.success && data.analytics) {
            renderAnalytics(data.analytics);
        }
    } catch (err) {
        // Skip temporary network errors.
    }
}

/**
 * Updates UI controls and metric cards
 */
function updateTelemetryUI(t) {
    if (!t) return;

    if (btnStart && btnStop) {
        if (t.monitoring) {
            btnStart.disabled = true;
            btnStop.disabled = false;
        } else {
            btnStart.disabled = false;
            btnStop.disabled = true;
        }
    }

    if (cameraPill && cameraStatusText) {
        if (t.camera_active) {
            cameraPill.className = "status-pill pill-active";
            cameraStatusText.textContent = "Camera Live";
        } else {
            cameraPill.className = "status-pill pill-stopped";
            cameraStatusText.textContent = "Camera Off";
        }
    }

    const status = t.status || "STOPPED";

    const statusClasses = {
        PRESENT: "badge-present",
        ABSENT: "badge-absent",
        INITIALIZING: "badge-initializing",
        STOPPED: "badge-stopped"
    };

    const badgeClass = statusClasses[status] || "badge-stopped";

    if (mainStatusBadge) {
        mainStatusBadge.className = `hero-badge ${badgeClass}`;
        mainStatusBadge.textContent = status;
    }

    if (streamOverlayBadge) {
        streamOverlayBadge.className = `stream-badge ${badgeClass}`;
        streamOverlayBadge.textContent = status;
    }

    if (statusHint) {
        if (status === "PRESENT") {
            statusHint.textContent = "User face detected within workspace boundary.";
        } else if (status === "ABSENT") {
            statusHint.textContent = "No face detected in workspace for > 3.0s.";
        } else if (status === "INITIALIZING") {
            statusHint.textContent = "Calibrating workspace and checking presence grace period...";
        } else {
            statusHint.textContent = "Monitoring is currently stopped. Click 'Start Monitoring' to begin.";
        }
    }

    if (stateTimer) {
        stateTimer.textContent = `In State: ${formatSeconds(t.current_state_duration_seconds)}`;
    }

    if (statFaces) statFaces.textContent = t.faces_detected || 0;

    if (statSession) {
        statSession.textContent = formatSeconds(t.session_duration_seconds, true);
    }

    if (statPresentTime) {
        statPresentTime.textContent = formatSeconds(t.total_present_seconds);
    }

    if (statAbsentTime) {
        statAbsentTime.textContent = formatSeconds(t.total_absent_seconds);
    }

    if (t.break_reminder) {
        updateBreakUI(t.break_reminder);
    }
}

/**
 * Updates Break Reminder UI
 */
function updateBreakUI(b) {
    if (!b) return;

    if (breakStateTag) {
        breakStateTag.textContent = b.state || "IDLE";
    }

    const curSec = Number(b.current_work_seconds) || 0;
    const targetSec = Number(b.work_interval_seconds) || 2700;
    const pct = Math.min(100, Math.max(0, Math.round((curSec / targetSec) * 100)));

    if (workProgressFill) {
        workProgressFill.style.width = `${pct}%`;
    }

    if (workTimerText) {
        workTimerText.textContent = `${formatSeconds(curSec)} / ${formatSeconds(targetSec)}`;
    }

    if (breakBanner) {
        if (b.reminder_active) {
            breakBanner.classList.remove("hidden");

            if (breakBannerTitle) {
                breakBannerTitle.textContent = "Time for a Healthy Break!";
            }

            if (breakBannerDesc) {
                const mins = Math.max(1, Math.round(curSec / 60));
                breakBannerDesc.textContent =
                    `You've been focused and working for ${mins} minutes. Take a 5-minute break to rest your eyes and stretch.`;
            }
        } else if (b.state === "ON_BREAK") {
            breakBanner.classList.remove("hidden");

            if (breakBannerTitle) {
                breakBannerTitle.textContent =
                    `Break in Progress: ${formatSeconds(b.remaining_break_seconds)} remaining`;
            }

            if (breakBannerDesc) {
                breakBannerDesc.textContent =
                    "Step away from the screen, hydrate, and stretch. Focus tracking will resume when your break completes.";
            }
        } else {
            breakBanner.classList.add("hidden");
        }
    }
}

/**
 * Renders Daily Analytics and 24-hour chart
 */
function renderAnalytics(a) {
    if (!a) return;

    if (analyticTotalMonitored) {
        analyticTotalMonitored.textContent =
            formatHumanDuration(a.total_monitored_seconds);
    }

    if (analyticTimePresent) {
        analyticTimePresent.textContent =
            formatHumanDuration(a.total_present_seconds);
    }

    if (analyticTimeAbsent) {
        analyticTimeAbsent.textContent =
            formatHumanDuration(a.total_absent_seconds);
    }

    if (analyticFocusRatio) {
        analyticFocusRatio.textContent =
            `${Number(a.focus_ratio_percent) || 0}%`;
    }

    if (Array.isArray(a.hourly_activity) && hourlyChart) {
        hourlyChart.replaceChildren();

        a.hourly_activity.forEach((sec, hour) => {
            const safeSeconds = Math.max(0, Number(sec) || 0);
            const minutes = safeSeconds / 60;
            const heightPct = Math.min(100, Math.max(3, (minutes / 60) * 100));

            const wrapper = document.createElement("div");
            wrapper.className = "chart-bar-wrapper";
            wrapper.dataset.tooltip =
                `${String(hour).padStart(2, "0")}:00 - ${minutes.toFixed(1)}m present`;

            const bar = document.createElement("div");
            bar.className = "chart-bar";
            bar.style.height = `${heightPct}%`;

            wrapper.appendChild(bar);
            hourlyChart.appendChild(wrapper);
        });
    }
}

/**
 * Renders Session History table safely
 */
function renderSessionsTable(sessions) {
    if (!sessionsTbody) return;

    sessionsTbody.replaceChildren();

    if (!sessions || sessions.length === 0) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");

        cell.colSpan = 6;
        cell.className = "empty-state";
        cell.textContent = "No sessions recorded yet.";

        row.appendChild(cell);
        sessionsTbody.appendChild(row);
        return;
    }

    sessions.forEach(s => {
        const row = document.createElement("tr");

        const dur = s.duration_seconds
            ? formatSeconds(parseFloat(s.duration_seconds))
            : "-";

        const pres = s.present_seconds
            ? formatSeconds(parseFloat(s.present_seconds))
            : "-";

        let badgeClass = "event-absent";

        if (s.status === "COMPLETED") {
            badgeClass = "event-present";
        } else if (s.status === "STOPPED_EARLY") {
            badgeClass = "event-initializing";
        }

        const values = [
            s.session_id || "-",
            s.start_time || "-",
            s.end_time || "-",
            dur,
            pres
        ];

        values.forEach(value => {
            const cell = document.createElement("td");
            cell.style.fontFamily = "monospace";
            cell.textContent = String(value);
            row.appendChild(cell);
        });

        const statusCell = document.createElement("td");
        const badge = document.createElement("span");

        statusCell.style.fontFamily = "inherit";
        badge.className = `event-badge ${badgeClass}`;
        badge.textContent = s.status || "COMPLETED";

        statusCell.appendChild(badge);
        row.appendChild(statusCell);

        sessionsTbody.appendChild(row);
    });
}

/**
 * Renders CSV transition events safely
 */
function renderEventsTable(events) {
    if (!eventsTbody) return;

    eventsTbody.replaceChildren();

    if (!events || events.length === 0) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");

        cell.colSpan = 4;
        cell.className = "empty-state";
        cell.textContent = "No events recorded yet.";

        row.appendChild(cell);
        eventsTbody.appendChild(row);
        return;
    }

    events.forEach(e => {
        const row = document.createElement("tr");

        const timestampCell = document.createElement("td");
        timestampCell.style.fontFamily = "monospace";
        timestampCell.textContent = e.timestamp || "-";

        const typeCell = document.createElement("td");
        const badge = document.createElement("span");

        const isPresent = e.event_type === "PRESENT";
        badge.className = `event-badge ${isPresent ? "event-present" : "event-absent"}`;
        badge.textContent = e.event_type || "UNKNOWN";

        typeCell.appendChild(badge);

        const durationCell = document.createElement("td");
        durationCell.style.fontFamily = "monospace";
        durationCell.textContent = e.duration_seconds
            ? `${parseFloat(e.duration_seconds).toFixed(1)}s`
            : "-";

        const detailsCell = document.createElement("td");
        detailsCell.textContent = e.details || "-";

        row.append(
            timestampCell,
            typeCell,
            durationCell,
            detailsCell
        );

        eventsTbody.appendChild(row);
    });
}

/**
 * Exports CSV events filtered by selected date
 */
function exportEventsCsv() {
    const picker = document.getElementById("export-date-picker");
    const dateVal = picker ? picker.value : "";

    if (dateVal) {
        window.location.href =
            `/api/export/events?date=${encodeURIComponent(dateVal)}`;
    } else {
        window.location.href = "/api/export/events";
    }
}

/**
 * Exports session history filtered by selected date
 */
function exportSessionsCsv() {
    const picker = document.getElementById("export-date-picker");
    const dateVal = picker ? picker.value : "";

    if (dateVal) {
        window.location.href =
            `/api/export/sessions?date=${encodeURIComponent(dateVal)}`;
    } else {
        window.location.href = "/api/export/sessions";
    }
}

/**
 * Initializes dashboard
 */
document.addEventListener("DOMContentLoaded", () => {
    const picker = document.getElementById("export-date-picker");

    if (picker) {
        picker.value = getTodayDateString();
    }

    fetchStatus();
    fetchEvents();
    fetchSessions();
    fetchAnalytics();

    statusPollingInterval = setInterval(fetchStatus, 1000);
    eventsPollingInterval = setInterval(fetchEvents, 2500);
    analyticsPollingInterval = setInterval(() => {
        fetchAnalytics();
        fetchSessions();
    }, 5000);
});
