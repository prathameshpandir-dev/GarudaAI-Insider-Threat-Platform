import os
import sys
from datetime import datetime, timedelta
from pymongo import MongoClient

# Configuration Dictionary for Risk Deductions
DEDUCTION_CONFIG = {
    "after_hours_login": 3.0,
    "unknown_device_login": 5.0,
    "usb_connect": 4.0,
    "unauthorized_privilege_escalation": 15.0,
    "confidential_file_access": 4.0,
    "restricted_file_access": 8.0,
    "large_file_transfer": 8.0,        # > 100MB
    "massive_data_transfer": 20.0,     # > 1000MB (USB / Email)
    "external_email_attachment": 6.0,
    "unusual_domain_visit": 5.0        # cloud exfiltration, personal email
}

RECOVERY_RATE_PER_DAY = 1.0 # Score recovers by 1.0 point per day of zero anomalies

def evaluate_event_deduction(event):
    """
    Evaluates a single event and returns a list of (deduction_name, score_deduction) tuples.
    """
    deductions = []
    etype = event.get("type")
    details = event.get("details", {})

    if etype == "logon":
        if details.get("is_after_hours"):
            deductions.append(("after_hours_login", DEDUCTION_CONFIG["after_hours_login"]))
        if not details.get("is_known_device"):
            deductions.append(("unknown_device_login", DEDUCTION_CONFIG["unknown_device_login"]))

    elif etype == "file":
        sens = details.get("file_sensitivity")
        size = details.get("file_size_mb", 0.0)
        
        if sens == "Confidential":
            deductions.append(("confidential_file_access", DEDUCTION_CONFIG["confidential_file_access"]))
        elif sens == "Restricted":
            deductions.append(("restricted_file_access", DEDUCTION_CONFIG["restricted_file_access"]))
            
        if size > 1000.0:
            deductions.append(("massive_data_transfer", DEDUCTION_CONFIG["massive_data_transfer"]))
        elif size > 100.0:
            deductions.append(("large_file_transfer", DEDUCTION_CONFIG["large_file_transfer"]))

    elif etype == "device":
        action = details.get("action")
        size = details.get("data_transferred_mb", 0.0)
        
        if action == "Connect":
            deductions.append(("usb_connect", DEDUCTION_CONFIG["usb_connect"]))
        if size > 1000.0:
            deductions.append(("massive_data_transfer", DEDUCTION_CONFIG["massive_data_transfer"]))
        elif size > 100.0:
            deductions.append(("large_file_transfer", DEDUCTION_CONFIG["large_file_transfer"]))

    elif etype == "email":
        domain = details.get("recipient_domain")
        has_att = details.get("has_attachment")
        size = details.get("attachment_size_mb", 0.0)
        
        if domain not in ["company.com", "partnercorp.com", "clientnet.org"]:
            deductions.append(("unusual_domain_visit", DEDUCTION_CONFIG["unusual_domain_visit"]))
        if has_att:
            deductions.append(("external_email_attachment", DEDUCTION_CONFIG["external_email_attachment"]))
            if size > 1000.0:
                deductions.append(("massive_data_transfer", DEDUCTION_CONFIG["massive_data_transfer"]))
            elif size > 100.0:
                deductions.append(("large_file_transfer", DEDUCTION_CONFIG["large_file_transfer"]))

    elif etype == "http":
        cat = details.get("url_category")
        domain = details.get("domain")
        if cat in ["Cloud Storage", "Webmail"] and domain in ["mega.io", "gmail.com", "yahoo.com"]:
            deductions.append(("unusual_domain_visit", DEDUCTION_CONFIG["unusual_domain_visit"]))

    elif etype == "privilege":
        approved_by = details.get("approved_by")
        if approved_by == "SYSTEM_AUTO":
            deductions.append(("unauthorized_privilege_escalation", DEDUCTION_CONFIG["unauthorized_privilege_escalation"]))

    return deductions

def recalculate_score(db, employee_id):
    """
    Chronologically evaluates an employee's events to compute current trust score and logs the history.
    """
    # Fetch all events chronologically
    events = list(db.events.find({"employee_id": employee_id}).sort("timestamp", 1))
    
    score = 100.0
    history = []
    
    # Store baseline initial score
    start_time = datetime(2026, 4, 13, 0, 0, 0)
    if events:
        start_time = events[0]["timestamp"] - timedelta(days=1)
        
    history.append({
        "employee_id": employee_id,
        "timestamp": start_time,
        "score": 100.0,
        "reason": "Initial Baseline"
    })
    
    last_date = start_time.date()
    
    for event in events:
        event_time = event["timestamp"]
        event_date = event_time.date()
        
        # 1. Apply daily recovery for clean days in the gap
        if event_date > last_date:
            days_diff = (event_date - last_date).days
            if days_diff > 1:
                # Add recovery points for the clean days between last_date and event_date
                clean_days = days_diff - 1
                score = min(100.0, score + (clean_days * RECOVERY_RATE_PER_DAY))
                # Add a recovery record in history
                history.append({
                    "employee_id": employee_id,
                    "timestamp": datetime.combine(event_date - timedelta(days=1), datetime.min.time()),
                    "score": score,
                    "reason": f"Recovery (+{clean_days} pts for clean behavior)"
                })
        
        # 2. Evaluate deductions for the current event
        deductions = evaluate_event_deduction(event)
        
        if deductions:
            total_deduction = sum(d[1] for d in deductions)
            score = max(0.0, score - total_deduction)
            reasons = ", ".join([f"{d[0]} (-{d[1]})" for d in deductions])
            
            history.append({
                "employee_id": employee_id,
                "timestamp": event_time,
                "score": score,
                "reason": reasons
            })
            
        last_date = event_date

    # Apply recovery from the last event date to the present (e.g. July 12, 2026)
    today = datetime(2026, 7, 12).date()
    if last_date < today:
        days_diff = (today - last_date).days
        if days_diff > 0:
            score = min(100.0, score + (days_diff * RECOVERY_RATE_PER_DAY))
            history.append({
                "employee_id": employee_id,
                "timestamp": datetime.combine(today, datetime.min.time()),
                "score": score,
                "reason": f"Recovery (+{days_diff} pts to current date)"
            })
            
    # Save score to employee document
    db.employees.update_one(
        {"employee_id": employee_id},
        {"$set": {"current_score": round(score, 2)}}
    )
    
    # Refresh trust score history
    db.trust_scores.delete_many({"employee_id": employee_id})
    db.trust_scores.insert_many(history)
    
    return round(score, 2)

def run_score_engine_all_users(db):
    """
    Utility to recalculate trust scores for all employees in the system.
    """
    employees = db.employees.find({}, {"employee_id": 1})
    count = 0
    for emp in employees:
        recalculate_score(db, emp["employee_id"])
        count += 1
    print(f"Recalculated scores and history snapshots for {count} employees.")
