# GarudaAI Database Schema Design

This document details the MongoDB database schema design, including collections, field definitions, indices, and mapping lists.

---

## Unified Collection Strategy

To satisfy high performance for chronological timeline queries, we store all security events (Logon, File, Device, HTTP, Email, and Privilege Escalation logs) in a single unified collection: `events`.

A `type` discriminator field is used to distinguish the origin of the event, avoiding expensive joins or union aggregates on the database level.

---

## Schema Collection Specifications

### 1. `employees` Collection
Each document holds the profile metadata and current pre-calculated behavior trust score for an employee.

```json
{
  "_id": "ObjectId",
  "employee_id": "String (Unique, Indexed)",
  "full_name": "String",
  "department": "String",
  "role": "String",
  "seniority_level": "String",
  "is_privileged_user": "Boolean",
  "hire_date": "Date / String (YYYY-MM-DD)",
  "manager_id": "String (Nullable)",
  "office_location": "String",
  "current_score": "Double (Range 0 - 100, default 100)"
}
```

### 2. `events` Collection (Unified Logs)
A polymorphic log storage storing logon, file, USB device, web browsing, email, and privilege events.

```json
{
  "_id": "ObjectId",
  "event_id": "String (Unique)",
  "employee_id": "String (Indexed)",
  "timestamp": "Date (Indexed)",
  "type": "String (Discriminator: 'logon' | 'file' | 'device' | 'http' | 'email' | 'privilege')",
  
  // Type-specific properties (only exist if type matches)
  "details": {
    // If type == "logon"
    "device_id": "String",
    "login_type": "String",
    "is_after_hours": "Boolean",
    "location": "String",
    "is_known_device": "Boolean",
    
    // If type == "file"
    "file_name": "String",
    "file_sensitivity": "String",
    "action": "String",
    "file_size_mb": "Double",
    
    // If type == "device"
    "device_type": "String",
    "action": "String",
    "data_transferred_mb": "Double",
    
    // If type == "http"
    "url_category": "String",
    "domain": "String",
    
    // If type == "email"
    "recipient_domain": "String",
    "has_attachment": "Boolean",
    "attachment_size_mb": "Double",
    
    // If type == "privilege"
    "previous_access_level": "String",
    "new_access_level": "String",
    "approved_by": "String",
    "justification_provided": "String"
  }
}
```

### 3. `trust_scores` Collection (Historical snapshots)
Used to render line charts and sparklines representing trust progression over time.

```json
{
  "_id": "ObjectId",
  "employee_id": "String (Indexed)",
  "timestamp": "Date",
  "score": "Double (Range 0 - 100)",
  "reason": "String (e.g., 'Initial import', 'After-hours login', 'Daily decay')"
}
```

### 4. `alerts` Collection
Tracks identified threat occurrences.

```json
{
  "_id": "ObjectId",
  "alert_id": "String (Unique)",
  "employee_id": "String (Indexed)",
  "timestamp": "Date",
  "type": "String (e.g., 'USB Theft', 'Impossible Travel')",
  "severity": "String ('Low' | 'Medium' | 'High' | 'Critical')",
  "description": "String",
  "status": "String ('Open' | 'Investigating' | 'Resolved')",
  "ai_explanation": "String (Nullable, holds cached Gemini output)"
}
```

### 5. `simulations` Collection
Tracks simulation executions and resets.

```json
{
  "_id": "ObjectId",
  "scenario_name": "String",
  "run_timestamp": "Date",
  "injected_event_count": "Integer"
}
```

---

## Indexing Plan

We apply the following indices on MongoDB collections:

1. **`employees`**:
   - Unique Index: `{"employee_id": 1}`
   - Index: `{"current_score": 1}` (for filtering "employees below Trust Score 40" efficiently)

2. **`events`**:
   - Compound Index: `{"employee_id": 1, "timestamp": 1}` (critical for Timeline rendering and sequential score updates)
   - Index: `{"timestamp": -1}` (for general logs view)

3. **`trust_scores`**:
   - Compound Index: `{"employee_id": 1, "timestamp": 1}` (for retrieving historical line trends)

4. **`alerts`**:
   - Index: `{"timestamp": -1}`
   - Index: `{"severity": 1}`

---

## CSV to MongoDB Field Mapping List

| Source File | CSV Column | Target Collection | Target Mongo Field | Type Conversion |
|---|---|---|---|---|
| `employees.csv` | `employee_id` | `employees` | `employee_id` | String |
| `employees.csv` | `full_name` | `employees` | `full_name` | String |
| `employees.csv` | `department` | `employees` | `department` | String |
| `employees.csv` | `role` | `employees` | `role` | String |
| `employees.csv` | `seniority_level`| `employees` | `seniority_level` | String |
| `employees.csv` | `is_privileged_user`| `employees` | `is_privileged_user` | Boolean (Parsed from CSV 'True'/'False') |
| `employees.csv` | `hire_date` | `employees` | `hire_date` | Date string |
| `employees.csv` | `manager_id` | `employees` | `manager_id` | String / Null |
| `employees.csv` | `office_location` | `employees` | `office_location` | String |
| `logon_activity.csv` | `event_id` | `events` | `event_id` | String |
| `logon_activity.csv` | `employee_id` | `events` | `employee_id` | String |
| `logon_activity.csv` | `timestamp` | `events` | `timestamp` | Date (Parsed from YYYY-MM-DD HH:MM:SS) |
| `logon_activity.csv` | `device_id` | `events` | `details.device_id` | String |
| `logon_activity.csv` | `login_type` | `events` | `details.login_type` | String |
| `logon_activity.csv` | `is_after_hours`| `events` | `details.is_after_hours`| Boolean (Parsed from CSV 'True'/'False') |
| `logon_activity.csv` | `location` | `events` | `details.location` | String |
| `logon_activity.csv` | `is_known_device`| `events` | `details.is_known_device`| Boolean (Parsed from CSV 'True'/'False') |
| `file_access.csv` | `event_id` | `events` | `event_id` | String |
| `file_access.csv` | `employee_id` | `events` | `employee_id` | String |
| `file_access.csv` | `timestamp` | `events` | `timestamp` | Date |
| `file_access.csv` | `file_name` | `events` | `details.file_name` | String |
| `file_access.csv` | `file_sensitivity`| `events` | `details.file_sensitivity`| String |
| `file_access.csv` | `action` | `events` | `details.action` | String |
| `file_access.csv` | `file_size_mb` | `events` | `details.file_size_mb` | Double (Parsed from Float) |
| `device_usage.csv` | `event_id` | `events` | `event_id` | String |
| `device_usage.csv` | `employee_id` | `events` | `employee_id` | String |
| `device_usage.csv` | `timestamp` | `events` | `timestamp` | Date |
| `device_usage.csv` | `device_type` | `events` | `details.device_type` | String |
| `device_usage.csv` | `action` | `events` | `details.action` | String |
| `device_usage.csv` | `data_transferred_mb`| `events` | `details.data_transferred_mb`| Double (Parsed from Float) |
| `http_activity.csv` | `event_id` | `events` | `event_id` | String |
| `http_activity.csv` | `employee_id` | `events` | `employee_id` | String |
| `http_activity.csv` | `timestamp` | `events` | `timestamp` | Date |
| `http_activity.csv` | `url_category` | `events` | `details.url_category`| String |
| `http_activity.csv` | `domain` | `events` | `details.domain` | String |
| `email_activity.csv`| `event_id` | `events` | `event_id` | String |
| `email_activity.csv`| `employee_id` | `events` | `employee_id` | String |
| `email_activity.csv`| `timestamp` | `events` | `timestamp` | Date |
| `email_activity.csv`| `recipient_domain`| `events` | `details.recipient_domain`| String |
| `email_activity.csv`| `has_attachment`| `events` | `details.has_attachment`| Boolean (Parsed from CSV 'True'/'False') |
| `email_activity.csv`| `attachment_size_mb`| `events` | `details.attachment_size_mb`| Double (Parsed from Float) |
| `privilege_escalation.csv`| `event_id` | `events` | `event_id` | String |
| `privilege_escalation.csv`| `employee_id` | `events` | `employee_id` | String |
| `privilege_escalation.csv`| `timestamp` | `events` | `timestamp` | Date |
| `privilege_escalation.csv`| `previous_access_level`| `events` | `details.previous_access_level`| String |
| `privilege_escalation.csv`| `new_access_level`| `events` | `details.new_access_level`| String |
| `privilege_escalation.csv`| `approved_by` | `events` | `details.approved_by`| String |
| `privilege_escalation.csv`| `justification_provided`| `events` | `details.justification_provided`| String |
