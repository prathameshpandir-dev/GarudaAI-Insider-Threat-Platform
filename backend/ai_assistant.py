import os
import sys
from datetime import datetime
from pymongo import MongoClient

try:
    from backend.timeline import get_employee_timeline
except ImportError:
    from timeline import get_employee_timeline

# Attempt to configure Gemini generative AI
gemini_available = False
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# If not in env, check .env file manually
if not GEMINI_API_KEY and os.path.exists(".env"):
    with open(".env", "r") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                key, val = line.strip().split("=", 1)
                if key.strip() == "GEMINI_API_KEY":
                    GEMINI_API_KEY = val.strip().strip('"').strip("'")

if GEMINI_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_available = True
        print("Gemini API configured successfully.")
    except Exception as e:
        print("Warning: Failed to import or configure google-generativeai:", e)
else:
    print("Warning: GEMINI_API_KEY not found in environment. Using rule-based fallback for AI Assistant.")

def get_rule_based_fallback(employee, alert):
    """
    Constructs a detailed, structured, rule-based explanation of the incident
    in case the Gemini API is unavailable or unconfigured.
    """
    name = employee.get("full_name", "Unknown Employee")
    role = employee.get("role", "Staff")
    dept = employee.get("department", "General")
    score = employee.get("current_score", 100)
    alert_type = alert.get("type", "Anomaly")
    desc = alert.get("description", "")
    
    narrative = f"Investigation details for {name} ({role} in {dept}) concerning Alert: **{alert_type}**.\n\n"
    
    if alert_type == "USB Theft":
        narrative += (
            "### Incident Narrative\n"
            f"Employee {name} executed a remote login outside of standard working hours from an unrecognized terminal. "
            "Shortly thereafter, the user accessed restricted files containing proprietary intellectual property or HR data, "
            "and transferred a massive payload (exceeding 4.0 GB) to a connected USB external storage device.\n\n"
            "### Suspicious Indicators\n"
            "- **After-Hours Auth**: Authenticated during off-hours window.\n"
            "- **Unknown Device Access**: Logged in from a device not registered to their profile.\n"
            "- **Massive Data Exfiltration**: Copied files to USB containing restricted classifications.\n\n"
            "### Business Impact\n"
            "- High risk of intellectual property leakage or trade secret compromise to external entities.\n"
            "- Potential GDPR/regulatory breach depending on file content.\n\n"
            "### Mitigation Playbook\n"
            "1. **Access Revocation**: Immediately freeze user credentials and disable active login sessions.\n"
            "2. **Physical Asset Control**: Recall assigned laptops/devices for physical forensic audit.\n"
            "3. **Incident Response**: Notify legal and HR teams of active data-transfer investigation."
        )
    elif alert_type == "Mass File Download":
        narrative += (
            "### Incident Narrative\n"
            f"Employee {name} performed a high volume of file read requests within a tight chronological window. "
            "The activity patterns indicate bulk harvesting of restricted spreadsheets and financial audit records.\n\n"
            "### Suspicious Indicators\n"
            "- **Bulk Read Spikes**: Excessive document queries (40+ instances in 60 minutes).\n"
            "- **Sensitive File Targeting**: Specifically targeted Restricted financial directories.\n\n"
            "### Business Impact\n"
            "- Exposure of corporate financials, roadmap strategies, or audit vulnerabilities.\n\n"
            "### Mitigation Playbook\n"
            "1. **Restructure Directory Access**: Suspend read permissions for the affected directory.\n"
            "2. **Manager Follow-Up**: Initiate administrative inquiry to verify business need for bulk downloads."
        )
    elif alert_type == "Impossible Travel":
        narrative += (
            "### Incident Narrative\n"
            f"Two authentications were recorded for {name} from locations separated by thousands of miles "
            "within an impossible travel duration (30 minutes between San Francisco and London). Following the second login, "
            "a large database backup file was downloaded and exfiltrated via email to an external competitor domain.\n\n"
            "### Suspicious Indicators\n"
            "- **Impossible Travel Anomaly**: Multi-location logs verify physical location mismatch.\n"
            "- **Compromised Credentials**: High probability of credential harvesting or session hijacking.\n"
            "- **Exfiltration**: Database dump transferred to an unverified external email domain.\n\n"
            "### Business Impact\n"
            "- High probability of compromised customer databases.\n\n"
            "### Mitigation Playbook\n"
            "1. **Session Termination**: Instantly invalidate all active session tokens.\n"
            "2. **Mandatory MFA Reset**: Enforce hardware multi-factor authentication reset.\n"
            "3. **Mail Gateway Block**: Block outbound mails to the target competitor domain."
        )
    elif alert_type == "Privilege Escalation":
        narrative += (
            "### Incident Narrative\n"
            f"The account for {name} experienced a privilege escalation from Standard User to Administrator. "
            "This change was approved by a automated service script without normal ticket routing, after which "
            "the user accessed sensitive mergers & acquisitions planning files.\n\n"
            "### Suspicious Indicators\n"
            "- **Unauthorized Level Shift**: Elevated from standard role without standard workflows.\n"
            "- **Targeted Directory Browsing**: Inspected acquisition strategies immediately post-escalation.\n\n"
            "### Business Impact\n"
            "- Infiltration of executive strategic blueprints and compliance vulnerabilities.\n\n"
            "### Mitigation Playbook\n"
            "1. **Demote Privileges**: Reset user permissions to baseline standard profile.\n"
            "2. **Audit Service Credentials**: Inspect logs of the system account that authorized the change."
        )
    else:
        narrative += (
            "### Incident Narrative\n"
            f"Behavior trust engine flagged anomalous sequence of logs for {name}. "
            f"The events show a score drop to {score}/100, indicating deviations from normal baseline operations.\n\n"
            "### Suspicious Indicators\n"
            f"- **Behavior Score Shift**: Sudden drop to {score}.\n"
            f"- **System Log Details**: {desc}\n\n"
            "### Business Impact\n"
            "- Potential unauthorized data access or staff burnout/risk profiles.\n\n"
            "### Mitigation Playbook\n"
            "1. **Monitor Profile**: Enable strict real-time auditing on this profile.\n"
            "2. **Verify Activity**: Contact employee's manager to confirm routine credentials usage."
        )
        
    return narrative

def generate_ai_explanation(db, alert_id):
    """
    Generates a security incident narrative and containment playbook.
    Checks cache first, calls Gemini API if active, or falls back to rule-based generation.
    """
    alert = db.alerts.find_one({"alert_id": alert_id})
    if not alert:
        return "Error: Alert not found in database."
        
    # 1. Cache hit check
    if alert.get("ai_explanation"):
        return alert["ai_explanation"]
        
    # 2. Get contextual data
    emp_id = alert["employee_id"]
    employee = db.employees.find_one({"employee_id": emp_id})
    if not employee:
        return "Error: Associated employee profile not found."
        
    # Get recent timeline events
    timeline = get_employee_timeline(db, emp_id)
    timeline_summary = "\n".join([
        f"[{t['timestamp']}] Type: {t['type']} | Severity: {t['severity']} | Description: {t['description']}"
        for t in timeline[-25:] # Fetch the latest 25 timeline items for prompt density
    ])

    if not gemini_available:
        # Fallback to rule-based explanation
        explanation = get_rule_based_fallback(employee, alert)
        db.alerts.update_one({"alert_id": alert_id}, {"$set": {"ai_explanation": explanation}})
        return explanation

    # 3. Call Gemini generative model
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""
You are GarudaAI, an elite AI Cyber Security Incident Response Investigator. 
Analyze the following security alert and employee profile behavior timeline to write an investigation report.

EMPLOYEE METADATA:
- Name: {employee.get('full_name')}
- Role: {employee.get('role')}
- Department: {employee.get('department')}
- Seniority: {employee.get('seniority_level')}
- Privileged User: {employee.get('is_privileged_user')}
- Current Behavior Trust Score: {employee.get('current_score')}/100

SECURITY ALERT METADATA:
- Alert Type: {alert.get('type')}
- Severity: {alert.get('severity')}
- Initial Trigger Description: {alert.get('description')}

CHRONOLOGICAL EVENT LOGS:
{timeline_summary}

Please write a comprehensive incident report in markdown. Your report must contain the following four specific sections:
1. ### Incident Narrative
Provide a cohesive, professional narrative explaining exactly what happened in a chronological story. Explain how the threat pattern unfolded based on the event logs.
2. ### Suspicious Indicators
In bullet points, highlight the exact activities that are suspicious, including the off-hours times, file sensitivity levels, external domains, or data volumes involved.
3. ### Business Impact
Explain the business risk, data leakage concerns, regulatory impacts, or financial threats of this compromise.
4. ### Mitigation Playbook
Detail 3 to 4 immediate, actionable mitigation steps for the security operations center (SOC) (e.g. revoking auth, blocking domains, auditing devices).

Keep the explanation grounded strictly in the provided event logs. Do not fabricate file names, email domains, or locations not present in the logs.
"""
        response = model.generate_content(prompt)
        explanation = response.text
        
        # Save to cache
        db.alerts.update_one({"alert_id": alert_id}, {"$set": {"ai_explanation": explanation}})
        return explanation
        
    except Exception as e:
        print(f"Warning: Gemini API call failed, falling back to rule-based: {e}")
        explanation = get_rule_based_fallback(employee, alert)
        # We don't cache database writes on temporary API errors, or we can cache to prevent spamming
        db.alerts.update_one({"alert_id": alert_id}, {"$set": {"ai_explanation": explanation}})
        return explanation
