"""
VisionGuard Lite - Flask Web Application
Entry point for local workspace monitoring dashboard.
Runs strictly on 127.0.0.1:5000.
"""
import logging
from flask import Flask, Response, jsonify, render_template, request

import config
from core.service import MonitoringService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VisionGuard.App")

app = Flask(__name__)
service = MonitoringService.get_instance()


@app.route("/")
def index():
    """Renders the main monitoring dashboard."""
    return render_template("index.html")


@app.route("/video_feed")
def video_feed():
    """
    MJPEG video stream endpoint.
    Streams annotated 320x240 frames or placeholder when stopped.
    """
    response = Response(
        service.generate_mjpeg_stream(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )
    # Prevent browser caching of the multipart stream
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/api/start", methods=["POST"])
def api_start():
    """Initializes the camera and starts workspace monitoring."""
    success, message = service.start_monitoring()
    status_code = 200 if success else 500
    return jsonify({
        "success": success,
        "message": message,
        "telemetry": service.get_telemetry()
    }), status_code


@app.route("/api/stop", methods=["POST"])
def api_stop():
    """Stops workspace monitoring and cleanly releases the camera."""
    success, message = service.stop_monitoring()
    return jsonify({
        "success": success,
        "message": message,
        "telemetry": service.get_telemetry()
    }), 200


@app.route("/api/status", methods=["GET"])
def api_status():
    """Returns current monitoring telemetry, state durations, and camera status."""
    return jsonify({
        "success": True,
        "telemetry": service.get_telemetry()
    }), 200


@app.route("/api/events", methods=["GET"])
def api_events():
    """Returns the most recent presence/absence transition events from the CSV log."""
    limit = request.args.get("limit", default=10, type=int)
    # Clamp limit to prevent excessive memory usage
    limit = max(1, min(limit, 50))
    events = service.get_recent_events(limit=limit)
    return jsonify({
        "success": True,
        "count": len(events),
        "events": events
    }), 200


@app.route("/api/break/take", methods=["POST"])
def api_break_take():
    """User takes a break. Enters countdown mode."""
    status = service.take_break()
    return jsonify({
        "success": True,
        "message": "Break started.",
        "break_status": status
    }), 200


@app.route("/api/break/dismiss", methods=["POST"])
def api_break_dismiss():
    """User dismisses break reminder. Resets work interval."""
    status = service.dismiss_break()
    return jsonify({
        "success": True,
        "message": "Break reminder dismissed. Work cycle reset.",
        "break_status": status
    }), 200


@app.route("/api/break/snooze", methods=["POST"])
def api_break_snooze():
    """User snoozes break reminder for configured duration."""
    req_json = request.get_json(silent=True) or {}
    minutes = req_json.get("minutes", config.BREAK_SNOOZE_MINUTES)
    try:
        minutes = float(minutes)
    except (ValueError, TypeError):
        minutes = float(config.BREAK_SNOOZE_MINUTES)

    status = service.snooze_break(minutes=minutes)
    return jsonify({
        "success": True,
        "message": f"Break reminder snoozed for {minutes} minutes.",
        "break_status": status
    }), 200


@app.route("/api/analytics", methods=["GET"])
def api_analytics():
    """Returns daily presence statistics and hourly activity for the given date (default: today)."""
    date_str = request.args.get("date")
    try:
        data = service.get_daily_analytics(target_date=date_str)
        return jsonify({
            "success": True,
            "analytics": data
        }), 200
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400


@app.route("/api/sessions", methods=["GET"])
def api_sessions():
    """Returns recent monitoring sessions from CSV."""
    limit = request.args.get("limit", default=10, type=int)
    limit = max(1, min(limit, 50))
    sessions = service.get_recent_sessions(limit=limit)
    return jsonify({
        "success": True,
        "count": len(sessions),
        "sessions": sessions
    }), 200


@app.route("/api/export/events", methods=["GET"])
def export_events():
    """Exports events CSV, optionally filtered by date (YYYY-MM-DD)."""
    import csv
    import io
    import os
    from datetime import datetime

    date_filter = request.args.get("date")

    if date_filter:
        try:
            parsed_date = datetime.strptime(date_filter, "%Y-%m-%d")
            if parsed_date.strftime("%Y-%m-%d") != date_filter:
                raise ValueError
        except ValueError:
            return jsonify({
                "success": False,
                "error": "Invalid date. Expected a real date in YYYY-MM-DD format."
            }), 400

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["timestamp", "event_type", "duration_seconds", "details"])

    if os.path.exists(config.EVENT_LOG_FILE):
        with open(config.EVENT_LOG_FILE, mode="r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                timestamp = row.get("timestamp", "")

                if date_filter and not timestamp.startswith(date_filter):
                    continue

                writer.writerow([
                    row.get("timestamp", ""),
                    row.get("event_type", ""),
                    row.get("duration_seconds", ""),
                    row.get("details", "")
                ])

    filename = (
        f"presence_events_{date_filter.replace('-', '')}.csv"
        if date_filter else "presence_events_all.csv"
    )

    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@app.route("/api/export/sessions", methods=["GET"])
def export_sessions():
    """Exports session history CSV, optionally filtered by session start date."""
    import csv
    import io
    import os
    from datetime import datetime

    date_filter = request.args.get("date")

    if date_filter:
        try:
            parsed_date = datetime.strptime(date_filter, "%Y-%m-%d")
            if parsed_date.strftime("%Y-%m-%d") != date_filter:
                raise ValueError
        except ValueError:
            return jsonify({
                "success": False,
                "error": "Invalid date. Expected a real date in YYYY-MM-DD format."
            }), 400

    if not os.path.exists(config.SESSION_LOG_FILE):
        content = (
            "session_id,start_time,end_time,duration_seconds,"
            "present_seconds,absent_seconds,status\n"
        )
    elif not date_filter:
        with open(config.SESSION_LOG_FILE, mode="r", encoding="utf-8") as f:
            content = f.read()
    else:
        output = io.StringIO(newline="")

        with open(config.SESSION_LOG_FILE, mode="r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)

            if reader.fieldnames:
                writer = csv.DictWriter(
                    output,
                    fieldnames=reader.fieldnames,
                    extrasaction="ignore"
                )
                writer.writeheader()

                for row in reader:
                    start_time = row.get("start_time", "")
                    if start_time.startswith(date_filter):
                        writer.writerow(row)
            else:
                output.write(
                    "session_id,start_time,end_time,duration_seconds,"
                    "present_seconds,absent_seconds,status\n"
                )

        content = output.getvalue()

    filename = (
        f"sessions_history_{date_filter.replace('-', '')}.csv"
        if date_filter else "sessions_history.csv"
    )

    response = Response(content, mimetype="text/csv")
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response



if __name__ == "__main__":

    logger.info("Starting VisionGuard Lite Web Server on http://%s:%s", config.SERVER_HOST, config.SERVER_PORT)
    app.run(
        host=config.SERVER_HOST,
        port=config.SERVER_PORT,
        debug=config.SERVER_DEBUG,
        threaded=True
    )
