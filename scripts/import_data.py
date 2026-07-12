import os
import csv
import sys
from datetime import datetime
from pymongo import UpdateOne

# Add root folder to sys.path so we can import backend packages
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from backend.db_client import get_db
except ImportError:
    # Fallback if pythonpath starts inside backend
    sys.path.append(os.path.dirname(__file__))
    from db_client import get_db

# Load env variables manually from .env if present
MONGODB_URI = "mongodb://localhost:27017/sentinelai"
if os.path.exists(".env"):
    with open(".env", "r") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                key, val = line.strip().split("=", 1)
                if key.strip() == "MONGODB_URI":
                    MONGODB_URI = val.strip().strip('"').strip("'")

# Connect to Database via wrapper
db = get_db(MONGODB_URI)

# Helper to parse boolean values
def parse_bool(val):
    return val.strip().lower() in ("true", "1", "yes")

# Helper to parse datetime values
def parse_date(val):
    try:
        return datetime.strptime(val.strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime(val.strip(), "%Y-%m-%d")
        except ValueError:
            return None

# Helper to parse floats
def parse_float(val):
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0

def setup_indexes():
    """Ensure indexes from our design are active."""
    print("Setting up database indexes...")
    db.employees.create_index("employee_id", unique=True)
    db.employees.create_index("current_score")
    db.events.create_index([("employee_id", 1), ("timestamp", 1)])
    db.events.create_index("timestamp")
    db.events.create_index("event_id", unique=True)
    db.trust_scores.create_index([("employee_id", 1), ("timestamp", 1)])
    db.alerts.create_index("alert_id", unique=True)
    db.alerts.create_index("timestamp")
    print("Indexes established successfully.")

def import_employees(reset=False):
    if reset:
        print("Resetting employees collection...")
        db.employees.delete_many({})
    
    csv_path = "dataset/employees.csv"
    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found.")
        return 0

    operations = []
    count = 0
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            emp_id = row["employee_id"]
            emp_doc = {
                "employee_id": emp_id,
                "full_name": row["full_name"],
                "department": row["department"],
                "role": row["role"],
                "seniority_level": row["seniority_level"],
                "is_privileged_user": parse_bool(row["is_privileged_user"]),
                "hire_date": row["hire_date"],
                "manager_id": row["manager_id"] if row["manager_id"] else None,
                "office_location": row["office_location"],
                "current_score": 100.0
            }
            operations.append(UpdateOne(
                {"employee_id": emp_id},
                {"$setOnInsert" if not reset else "$set": emp_doc},
                upsert=True
            ))
            count += 1
            
    if operations:
        db.employees.bulk_write(operations)
    return count

def import_events(filename, event_type, reset=False):
    csv_path = f"dataset/{filename}"
    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found.")
        return 0

    operations = []
    count = 0
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            event_id = row["event_id"]
            timestamp = parse_date(row["timestamp"])
            emp_id = row["employee_id"]
            
            details = {}
            if event_type == "logon":
                details = {
                    "device_id": row["device_id"],
                    "login_type": row["login_type"],
                    "is_after_hours": parse_bool(row["is_after_hours"]),
                    "location": row["location"],
                    "is_known_device": parse_bool(row["is_known_device"])
                }
            elif event_type == "file":
                details = {
                    "file_name": row["file_name"],
                    "file_sensitivity": row["file_sensitivity"],
                    "action": row["action"],
                    "file_size_mb": parse_float(row["file_size_mb"])
                }
            elif event_type == "device":
                details = {
                    "device_type": row["device_type"],
                    "action": row["action"],
                    "data_transferred_mb": parse_float(row["data_transferred_mb"])
                }
            elif event_type == "http":
                details = {
                    "url_category": row["url_category"],
                    "domain": row["domain"]
                }
            elif event_type == "email":
                details = {
                    "recipient_domain": row["recipient_domain"],
                    "has_attachment": parse_bool(row["has_attachment"]),
                    "attachment_size_mb": parse_float(row["attachment_size_mb"])
                }
            elif event_type == "privilege":
                details = {
                    "previous_access_level": row["previous_access_level"],
                    "new_access_level": row["new_access_level"],
                    "approved_by": row["approved_by"],
                    "justification_provided": row["justification_provided"]
                }

            event_doc = {
                "event_id": event_id,
                "employee_id": emp_id,
                "timestamp": timestamp,
                "type": event_type,
                "details": details
            }
            
            operations.append(UpdateOne(
                {"event_id": event_id},
                {"$setOnInsert" if not reset else "$set": event_doc},
                upsert=True
            ))
            count += 1
            
            if len(operations) >= 2000:
                db.events.bulk_write(operations)
                operations = []

    if operations:
        db.events.bulk_write(operations)
    return count

def import_ground_truth(reset=False):
    if reset:
        db.alerts.delete_many({})
    
    csv_path = "dataset/ground_truth_labels.csv"
    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found.")
        return 0

    count = 0
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if parse_bool(row["is_insider_threat"]):
                emp_id = row["employee_id"]
                threat_pattern = row["threat_pattern"]
                notes = row["notes"]
                
                alert_id = f"ALERT-{emp_id}-{threat_pattern.replace(' ', '_')}"
                alert_doc = {
                    "alert_id": alert_id,
                    "employee_id": emp_id,
                    "timestamp": datetime.now(),
                    "type": threat_pattern,
                    "severity": "Critical" if threat_pattern in ["USB Theft", "Mass File Download", "Impossible Travel"] else "High",
                    "description": notes,
                    "status": "Open",
                    "ai_explanation": None
                }
                db.alerts.update_one(
                    {"alert_id": alert_id},
                    {"$setOnInsert" if not reset else "$set": alert_doc},
                    upsert=True
                )
                count += 1
    return count

def main():
    reset = "--reset" in sys.argv
    if reset:
        print("Wiping existing events and trust score history...")
        db.events.delete_many({})
        db.trust_scores.delete_many({})
        db.simulations.delete_many({})
    
    setup_indexes()

    print("\nStarting Ingestion Pipeline...")
    
    # Import Employees
    emp_count = import_employees(reset)
    print(f"Loaded {emp_count} employees.")

    # Import Activities
    logon_count = import_events("logon_activity.csv", "logon", reset)
    print(f"Loaded {logon_count} logon activity events.")

    file_count = import_events("file_access.csv", "file", reset)
    print(f"Loaded {file_count} file access events.")

    device_count = import_events("device_usage.csv", "device", reset)
    print(f"Loaded {device_count} device usage events.")

    http_count = import_events("http_activity.csv", "http", reset)
    print(f"Loaded {http_count} HTTP navigation events.")

    email_count = import_events("email_activity.csv", "email", reset)
    print(f"Loaded {email_count} email activity events.")

    priv_count = import_events("privilege_escalation.csv", "privilege", reset)
    print(f"Loaded {priv_count} privilege escalations.")

    # Import Alerts from Ground Truth labels
    alert_count = import_ground_truth(reset)
    print(f"Loaded {alert_count} ground-truth security alerts.")

    print("\nData Import Completed successfully.")
    
    # Verify DB counts
    print("--- Database Summary Check ---")
    print(f"Employees in DB: {db.employees.count_documents({})}")
    print(f"Events in DB: {db.events.count_documents({})}")
    print(f"Alerts in DB: {db.alerts.count_documents({})}")

if __name__ == "__main__":
    main()
