import os
from datetime import datetime
try:
    from backend.trust_score import evaluate_event_deduction
except ImportError:
    from trust_score import evaluate_event_deduction

def get_event_severity(deductions):
    if not deductions:
        return "Low"
    max_ded = sum(d[1] for d in deductions)
    if max_ded >= 15:
        return "Critical"
    elif max_ded >= 8:
        return "High"
    elif max_ded >= 4:
        return "Medium"
    else:
        return "Low"

def format_event_description(etype, details, is_anomaly):
    if etype == "logon":
        loc = details.get("location", "Unknown Location")
        dev = details.get("device_id", "Unknown Device")
        if is_anomaly:
            reasons = []
            if details.get("is_after_hours"):
                reasons.append("after-hours")
            if not details.get("is_known_device"):
                reasons.append("unknown device")
            return f"Suspicious login from {loc} ({', '.join(reasons)}) using {dev}"
        return f"Routine login from {loc} using {dev}"

    elif etype == "file":
        name = details.get("file_name", "unknown_file")
        size = details.get("file_size_mb", 0.0)
        sens = details.get("file_sensitivity", "Public")
        action = details.get("action", "Read")
        if is_anomaly:
            return f"Unauthorized access: {action} {sens} file '{name}' ({size} MB)"
        return f"Accessed file '{name}' ({size} MB)"

    elif etype == "device":
        act = details.get("action", "Action")
        size = details.get("data_transferred_mb", 0.0)
        if is_anomaly:
            return f"Suspicious USB transfer: {act} with massive payload ({size} MB)"
        return f"USB device connected/operated ({size} MB)"

    elif etype == "http":
        cat = details.get("url_category", "General")
        dom = details.get("domain", "unknown.com")
        if is_anomaly:
            return f"High-risk web access: Visited {dom} (Category: {cat})"
        return f"Browsed web: {dom} (Category: {cat})"

    elif etype == "email":
        domain = details.get("recipient_domain", "external.com")
        has_att = details.get("has_attachment")
        size = details.get("attachment_size_mb", 0.0)
        att_str = f" with attachment ({size} MB)" if has_att else ""
        if is_anomaly:
            return f"Potential data leak: Email sent to {domain}{att_str}"
        return f"Email sent to {domain}{att_str}"

    elif etype == "privilege":
        prev = details.get("previous_access_level", "User")
        new = details.get("new_access_level", "Admin")
        by = details.get("approved_by", "SYSTEM")
        if is_anomaly:
            return f"CRITICAL: Unauthorized privilege escalation from {prev} to {new} (Approved by: {by})"
        return f"Role escalation from {prev} to {new} (Approved by: {by})"
        
    return f"Security activity: {etype.capitalize()}"

def get_employee_timeline(db, employee_id):
    """
    Returns a sorted, collapsed, and grouped list of timeline entries for the investigator dashboard.
    """
    raw_events = list(db.events.find({"employee_id": employee_id}).sort("timestamp", 1))
    
    timeline = []
    current_group = []
    
    for event in raw_events:
        etype = event["type"]
        ts = event["timestamp"]
        details = event.get("details", {})
        
        # Check if event is anomalous
        deductions = evaluate_event_deduction(event)
        is_anomaly = len(deductions) > 0
        
        if is_anomaly:
            # Flush any pending routine group before adding this anomaly
            if current_group:
                timeline.append(flush_routine_group(current_group))
                current_group = []
                
            timeline.append({
                "event_id": event["event_id"],
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "type": etype,
                "description": format_event_description(etype, details, is_anomaly=True),
                "severity": get_event_severity(deductions),
                "is_anomaly": True,
                "collapsed": False,
                "count": 1
            })
        else:
            # Check if we can group this routine event with previous ones
            if current_group:
                prev_event = current_group[-1]
                prev_date = prev_event["timestamp"].date()
                curr_date = ts.date()
                
                # Group if same type on the same calendar day
                if prev_event["type"] == etype and prev_date == curr_date:
                    current_group.append(event)
                else:
                    timeline.append(flush_routine_group(current_group))
                    current_group = [event]
            else:
                current_group = [event]
                
    # Flush any remaining group
    if current_group:
        timeline.append(flush_routine_group(current_group))
        
    # Re-sort chronologically by timestamp (flush_routine_group uses the latest timestamp in the group)
    timeline.sort(key=lambda x: x["timestamp"])
    return timeline

def flush_routine_group(group):
    """
    Compresses a group of consecutive routine events into a single timeline summary card.
    """
    last_event = group[-1]
    etype = last_event["type"]
    count = len(group)
    
    if count == 1:
        return {
            "event_id": last_event["event_id"],
            "timestamp": last_event["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
            "type": etype,
            "description": format_event_description(etype, last_event.get("details", {}), is_anomaly=False),
            "severity": "Low",
            "is_anomaly": False,
            "collapsed": False,
            "count": 1
        }
        
    # Multi-event summary
    categories = set()
    for e in group:
        details = e.get("details", {})
        if etype == "http":
            categories.add(details.get("url_category", "General"))
        elif etype == "file":
            categories.add(details.get("action", "Access"))
        elif etype == "logon":
            categories.add(details.get("location", "Office"))
            
    cat_str = f" ({', '.join(categories)})" if categories else ""
    
    description = f"{count} routine {etype} operations{cat_str}"
    if etype == "logon":
        description = f"{count} routine logons from {', '.join(categories)}"
    elif etype == "file":
        description = f"{count} routine file operations"
    elif etype == "http":
        description = f"{count} standard web search/browse sessions"
    elif etype == "email":
        description = f"{count} standard emails sent"

    return {
        "event_id": last_event["event_id"],
        "timestamp": last_event["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
        "type": etype,
        "description": description,
        "severity": "Low",
        "is_anomaly": False,
        "collapsed": True,
        "count": count
    }
