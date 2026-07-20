import os
import uuid
import sys
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pymongo import MongoClient

try:
    from backend.trust_score import recalculate_score, run_score_engine_all_users
    from backend.timeline import get_employee_timeline
    from backend.ai_assistant import generate_ai_explanation
except ImportError:
    from trust_score import recalculate_score, run_score_engine_all_users
    from timeline import get_employee_timeline
    from ai_assistant import generate_ai_explanation

app = Flask(__name__)
# Enable CORS for frontend client port matching (usually 5173 for Vite)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Configure Rate Limiter
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["100 per minute"]
)

# Configuration settings
MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/garudaai")
DEV_MODE = os.environ.get("DEV_MODE", "true").lower() == "true"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Load configuration from .env if present
if os.path.exists(".env"):
    with open(".env", "r") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                key, val = line.strip().split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key == "MONGODB_URI":
                    MONGODB_URI = val
                elif key == "DEV_MODE":
                    DEV_MODE = val.lower() == "true"
                elif key == "GEMINI_API_KEY":
                    GEMINI_API_KEY = val

# Connect to Database via wrapper
try:
    from backend.db_client import get_db
except ImportError:
    from db_client import get_db

db = get_db(MONGODB_URI)

# Initialize Firebase Admin SDK if active
firebase_initialized = False
if not DEV_MODE:
    try:
        import firebase_admin
        from firebase_admin import auth, credentials
        
        # Check if initialized already
        if not firebase_admin._apps:
            cred = credentials.Certificate({
                "type": "service_account",
                "project_id": os.environ.get("FIREBASE_PROJECT_ID"),
                "private_key": os.environ.get("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n"),
                "client_email": os.environ.get("FIREBASE_CLIENT_EMAIL")
            })
            firebase_admin.initialize_app(cred)
        firebase_initialized = True
        print("Firebase Admin Admin SDK initialized.")
    except Exception as e:
        print("Warning: Firebase configuration failed. Enforcing DEV_MODE=true. Error:", e)
        DEV_MODE = True

# Authentication Decorator Middleware
def require_auth(f):
    @wraps(f)
    def decorated_func(*args, **kwargs):
        if DEV_MODE:
            # Developer mode bypasses authentication check
            return f(*args, **kwargs)
            
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid authorization header. Expected Bearer Token."}), 401
            
        token = auth_header.split("Bearer ")[1]
        try:
            decoded_token = auth.verify_id_token(token)
            request.user = decoded_token
        except Exception as e:
            return jsonify({"error": f"Unauthorized: {str(e)}"}), 401
            
        return f(*args, **kwargs)
    return decorated_func


# --- REST API ROUTES ---

@app.route("/api/health", methods=["GET"])
def health_check():
    """Service Health status checker."""
    db_status = "Connected"
    try:
        db.employees.find_one()
    except Exception:
        db_status = "Disconnected"
        
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "database": db_status,
        "mode": "Developer (Bypass Auth)" if DEV_MODE else "Production (Auth Active)",
        "gemini_api": "Configured" if GEMINI_API_KEY else "Fallback Mode"
    })

@app.route("/api/employees", methods=["GET"])
@require_auth
def get_employees():
    """Returns all employee profiles sorted by Behavior Trust Score ascending (riskiest first)."""
    try:
        employees = list(db.employees.find({}, {"_id": 0}))
        # Sort riskiest employees first
        employees.sort(key=lambda x: x.get("current_score", 100.0))
        return jsonify(employees)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/employees/<employee_id>/timeline", methods=["GET"])
@require_auth
def get_timeline(employee_id):
    """Assembles chronological timeline for a specific employee."""
    try:
        timeline = get_employee_timeline(db, employee_id)
        return jsonify(timeline)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/employees/<employee_id>/trust-score/history", methods=["GET"])
@require_auth
def get_trust_history(employee_id):
    """Fetches chronological trust score historical snapshots."""
    try:
        history = list(db.trust_scores.find({"employee_id": employee_id}, {"_id": 0}).sort("timestamp", 1))
        # Format timestamps to strings
        for h in history:
            if isinstance(h["timestamp"], datetime):
                h["timestamp"] = h["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
        return jsonify(history)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/alerts", methods=["GET"])
@require_auth
def get_alerts():
    """Returns active alerts. Filterable by severity."""
    severity = request.args.get("severity")
    query = {}
    if severity:
        query["severity"] = severity
        
    try:
        alerts = list(db.alerts.find(query, {"_id": 0}).sort("timestamp", -1))
        for a in alerts:
            if isinstance(a["timestamp"], datetime):
                a["timestamp"] = a["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
        return jsonify(alerts)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/alerts/<alert_id>/explanation", methods=["GET"])
@require_auth
def get_alert_explanation(alert_id):
    """Returns Gemini AI generated analysis narrative and incident playbook."""
    try:
        explanation = generate_ai_explanation(db, alert_id)
        return jsonify({"alert_id": alert_id, "explanation": explanation})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/simulate", methods=["POST"])
@require_auth
@limiter.limit("5 per minute")
def simulate_attack():
    """
    Simulates a live attack injection.
    Writes malicious events to MongoDB, recalculates scores, and creates an alert.
    """
    data = request.json or {}
    scenario = data.get("scenario")
    emp_id = data.get("employee_id")
    
    if not scenario or not emp_id:
        return jsonify({"error": "Missing parameters 'scenario' and 'employee_id'"}), 400
        
    employee = db.employees.find_one({"employee_id": emp_id})
    if not employee:
        return jsonify({"error": f"Employee {emp_id} not found"}), 404
        
    # Reset existing threat logs for employee to ensure a clean demo run
    db.events.delete_many({
        "employee_id": emp_id,
        "event_id": {"$regex": "^SIM-"}
    })
    db.alerts.delete_many({
        "employee_id": emp_id,
        "alert_id": {"$regex": "^SIM-ALERT-"}
    })
    
    # Re-sync baseline score
    recalculate_score(db, emp_id)

    timestamp = datetime.now()
    injected_events = []
    
    # Formulate Scenarios
    if scenario == "usb_theft":
        # 1. Midnight Login
        injected_events.append({
            "event_id": f"SIM-logon-{uuid.uuid4().hex[:10]}",
            "employee_id": emp_id,
            "timestamp": timestamp - timedelta(minutes=45),
            "type": "logon",
            "details": {
                "device_id": f"DEV-{emp_id[3:]}-USBX",
                "login_type": "Remote",
                "is_after_hours": True,
                "location": "Moscow, RU",
                "is_known_device": False
            }
        })
        # 2. File Access (Confidential schematics)
        for i in range(4):
            injected_events.append({
                "event_id": f"SIM-file-{uuid.uuid4().hex[:10]}",
                "employee_id": emp_id,
                "timestamp": timestamp - timedelta(minutes=40 - i),
                "type": "file",
                "details": {
                    "file_name": f"core_patent_design_schema_v{i}.cad",
                    "file_sensitivity": "Restricted",
                    "action": "Read",
                    "file_size_mb": 120.0
                }
            })
        # 3. USB Ingest
        injected_events.append({
            "event_id": f"SIM-device-{uuid.uuid4().hex[:10]}",
            "employee_id": emp_id,
            "timestamp": timestamp - timedelta(minutes=30),
            "type": "device",
            "details": {
                "device_type": "USB Drive",
                "action": "Connect",
                "data_transferred_mb": 4800.0
            }
        })
        alert_desc = "Out-of-hours unknown device authentication followed by exfiltration of patent CAD schemas (4.8 GB) to USB device."
        alert_type = "USB Theft"
        severity = "Critical"

    elif scenario == "mass_download":
        # 30 files read in 5 minutes
        for i in range(30):
            injected_events.append({
                "event_id": f"SIM-file-{uuid.uuid4().hex[:10]}",
                "employee_id": emp_id,
                "timestamp": timestamp - timedelta(seconds=(30 - i) * 10),
                "type": "file",
                "details": {
                    "file_name": f"customer_billing_ledger_page{i}.xlsx",
                    "file_sensitivity": "Restricted",
                    "action": "Read",
                    "file_size_mb": 15.0
                }
            })
        alert_desc = "Spike in document read actions: harvested 30 highly restricted customer ledgers inside a 5 minute period."
        alert_type = "Mass File Download"
        severity = "High"

    elif scenario == "impossible_travel":
        # SF Login
        injected_events.append({
            "event_id": f"SIM-logon-sf-{uuid.uuid4().hex[:6]}",
            "employee_id": emp_id,
            "timestamp": timestamp - timedelta(minutes=25),
            "type": "logon",
            "details": {
                "device_id": f"DEV-{emp_id[3:]}-101",
                "login_type": "Interactive",
                "is_after_hours": False,
                "location": "San Francisco",
                "is_known_device": True
            }
        })
        # London Login (15 mins later)
        injected_events.append({
            "event_id": f"SIM-logon-ldn-{uuid.uuid4().hex[:6]}",
            "employee_id": emp_id,
            "timestamp": timestamp - timedelta(minutes=10),
            "type": "logon",
            "details": {
                "device_id": f"DEV-{emp_id[3:]}-999",
                "login_type": "Remote",
                "is_after_hours": False,
                "location": "London, UK",
                "is_known_device": False
            }
        })
        # Email dump
        injected_events.append({
            "event_id": f"SIM-email-{uuid.uuid4().hex[:10]}",
            "employee_id": emp_id,
            "timestamp": timestamp - timedelta(minutes=5),
            "type": "email",
            "details": {
                "recipient_domain": "competing-defence-firm.com",
                "has_attachment": True,
                "attachment_size_mb": 850.0
            }
        })
        alert_desc = "Impossible travel logins flagged: San Francisco and London within 15 minutes. Followed by 850 MB attachment exfiltrated to competitor domain."
        alert_type = "Impossible Travel"
        severity = "Critical"

    elif scenario == "privilege_escalation":
        # Unapproved Escalation
        injected_events.append({
            "event_id": f"SIM-priv-{uuid.uuid4().hex[:10]}",
            "employee_id": emp_id,
            "timestamp": timestamp - timedelta(minutes=15),
            "type": "privilege",
            "details": {
                "previous_access_level": "User",
                "new_access_level": "Administrator",
                "approved_by": "SYSTEM_AUTO",
                "justification_provided": "Urgent dev-server emergency recovery"
            }
        })
        # Restricted read
        injected_events.append({
            "event_id": f"SIM-file-{uuid.uuid4().hex[:10]}",
            "employee_id": emp_id,
            "timestamp": timestamp - timedelta(minutes=10),
            "type": "file",
            "details": {
                "file_name": f"mergers_acquisitions_confidential_negotiations.pdf",
                "file_sensitivity": "Restricted",
                "action": "Read",
                "file_size_mb": 40.0
            }
        })
        alert_desc = "Unauthorized privilege escalation from User to Admin by script, followed immediately by restricted Merger document review."
        alert_type = "Privilege Escalation"
        severity = "High"

    else:
        return jsonify({"error": f"Scenario {scenario} not supported."}), 400

    # Write events to database
    db.events.insert_many(injected_events)
    
    # Recalculate score and save history
    new_score = recalculate_score(db, emp_id)
    
    # Inject Alert
    alert_id = f"SIM-ALERT-{emp_id}-{scenario.upper()}"
    alert_doc = {
        "alert_id": alert_id,
        "employee_id": emp_id,
        "timestamp": timestamp,
        "type": alert_type,
        "severity": severity,
        "description": alert_desc,
        "status": "Open",
        "ai_explanation": None
    }
    db.alerts.insert_one(alert_doc)
    
    # Record simulation log
    db.simulations.insert_one({
        "scenario_name": scenario,
        "run_timestamp": timestamp,
        "injected_event_count": len(injected_events)
    })
    
    return jsonify({
        "message": "Simulation injected successfully",
        "employee_id": emp_id,
        "new_score": new_score,
        "alert_id": alert_id,
        "events_injected": len(injected_events)
    })

@app.route("/api/reset", methods=["POST"])
@require_auth
def reset_demo():
    """Wipes all simulated logs/alerts, recovers baseline data state, and re-calculates all scores."""
    try:
        # Wipe SIM records
        db.events.delete_many({"event_id": {"$regex": "^SIM-"}})
        db.alerts.delete_many({"alert_id": {"$regex": "^SIM-ALERT-"}})
        db.trust_scores.delete_many({})
        db.simulations.delete_many({})
        
        # Reset alert AI caches
        db.alerts.update_many({}, {"$set": {"ai_explanation": None}})
        
        # Recompute all standard employee scores
        run_score_engine_all_users(db)
        
        return jsonify({"message": "Demo database successfully reset to standard baseline state."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/chat", methods=["POST"])
@require_auth
@limiter.limit("10 per minute")
def security_chat():
    """
    AI Security Chat query handling.
    If Gemini API is active, interprets the prompt to filter/answer queries.
    Otherwise, applies intelligent keyword parsing (fallback engine).
    """
    data = request.json or {}
    message = data.get("message", "").strip()
    
    if not message:
        return jsonify({"error": "Message parameter is required"}), 400

    # Fallback keyword engine logic
    def run_fallback_chat(msg):
        msg_lower = msg.lower()
        
        if "under" in msg_lower or "below" in msg_lower or "less than" in msg_lower:
            # Extract number
            score_limit = 40
            for word in msg_lower.split():
                try:
                    score_limit = int(word)
                    break
                except ValueError:
                    pass
            employees = list(db.employees.find({"current_score": {"$lt": score_limit}}, {"_id": 0}))
            emp_list = "\n".join([f"- **{e['full_name']}** ({e['employee_id']}) in {e['department']}: Score **{e['current_score']}**" for e in employees])
            
            response_text = f"I found {len(employees)} employees with behavior trust scores below **{score_limit}**:\n\n{emp_list or 'No employees matching this criteria.'}\n\n*This response was generated using local keyword parsing.*"
            return response_text
            
        elif "privileged" in msg_lower or "admin" in msg_lower:
            employees = list(db.employees.find({"is_privileged_user": True}, {"_id": 0}))
            emp_list = "\n".join([f"- **{e['full_name']}** ({e['employee_id']}) - Role: {e['role']} (Score: {e['current_score']})" for e in employees[:10]])
            response_text = f"Here are some privileged user profiles (showing top 10 of {len(employees)} total):\n\n{emp_list}\n\n*This response was generated using local keyword parsing.*"
            return response_text
            
        elif "department" in msg_lower or "dept" in msg_lower:
            found_dept = None
            for dept in ["engineering", "finance", "sales", "hr"]:
                if dept in msg_lower:
                    found_dept = dept.capitalize()
                    if dept == "hr":
                        found_dept = "HR"
                    break
                    
            if found_dept:
                employees = list(db.employees.find({"department": found_dept}, {"_id": 0}))
                emp_list = "\n".join([f"- **{e['full_name']}** ({e['employee_id']}) - {e['role']} (Score: {e['current_score']})" for e in employees[:10]])
                return f"Employees in the **{found_dept}** department (showing top 10 of {len(employees)}):\n\n{emp_list}\n\n*This response was generated using local keyword parsing.*"

        # General helper reply
        return (
            "Hello, I am GarudaAI's interactive assistant. I can query our security database. Try asking:\n"
            "- 'Show employees below score 50'\n"
            "- 'List privileged administrators'\n"
            "- 'Show employees in the Finance department'\n\n"
            "*This response was generated using local keyword parsing.*"
        )

    # If Gemini is configured and active
    if GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            # Fetch summary list of employees and alerts for quick inline lookup
            employees_sample = list(db.employees.find({}, {"_id": 0, "employee_id": 1, "full_name": 1, "department": 1, "current_score": 1}))
            alerts_sample = list(db.alerts.find({}, {"_id": 0, "alert_id": 1, "employee_id": 1, "type": 1, "severity": 1, "status": 1}))
            
            prompt = f"""
You are the GarudaAI Security Assistant chat module. You answer security questions about the network and our employees.

DATABASE SUMMARY CONTEXT:
- Employees: {employees_sample[:30]} ... (plus more profiles in db)
- Alerts: {alerts_sample[:15]}

The analyst asks: "{message}"

Use the provided database context to construct your answer. If the question requires filtering employees or listing specific data, you can answer by detailing who matches. Provide a professional, concise, security-oriented response in markdown format.
"""
            response = model.generate_content(prompt)
            return jsonify({"response": response.text})
            
        except Exception as e:
            print(f"Warning: Chat Gemini call failed, running keyword fallback: {e}")
            return jsonify({"response": run_fallback_chat(message)})
            
    else:
        return jsonify({"response": run_fallback_chat(message)})


# Start Server
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
