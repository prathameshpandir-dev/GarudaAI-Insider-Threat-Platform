import os
import json
import sys
from datetime import datetime
from pymongo import MongoClient

def parse_date_robust(val):
    """
    Robustly parses string timestamps of various ISO and SQL formats into datetime objects.
    """
    if isinstance(val, datetime):
        return val
    if not isinstance(val, str):
        return val
    
    val = val.strip()
    # Try standard SQL/CSV format first
    for fmt in [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d"
    ]:
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            pass
            
    # Try ISO fromisoformat fallback
    try:
        # In Python 3.11+, handles space separator; in older versions, may raise ValueError
        return datetime.fromisoformat(val)
    except ValueError:
        return val


class MockCollection:
    def __init__(self, filename):
        self.filepath = os.path.join("backend", "mock_db", filename)
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        if not os.path.exists(self.filepath):
            with open(self.filepath, "w") as f:
                json.dump([], f)
        self._cache = None

    def _read_data(self):
        if self._cache is not None:
            return self._cache
        try:
            with open(self.filepath, "r") as f:
                data = json.load(f)
                # Convert date strings back to datetime objects
                for doc in data:
                    if "timestamp" in doc:
                        doc["timestamp"] = parse_date_robust(doc["timestamp"])
                self._cache = data
                return data
        except Exception:
            return []

    def _write_data(self, data):
        self._cache = data
        serializable_data = []
        for doc in data:
            new_doc = doc.copy()
            if "_id" in new_doc:
                new_doc["_id"] = str(new_doc["_id"])
            for key, val in new_doc.items():
                if isinstance(val, datetime):
                    new_doc[key] = val.isoformat()
                elif isinstance(val, dict):
                    new_doc[key] = val.copy()
                    for subkey, subval in new_doc[key].items():
                        if isinstance(subval, datetime):
                            new_doc[key][subkey] = subval.isoformat()
            serializable_data.append(new_doc)
            
        with open(self.filepath, "w") as f:
            json.dump(serializable_data, f, indent=2)

    def _match_query(self, doc, query):
        if not query:
            return True
        for key, val in query.items():
            if key == "event_id" and isinstance(val, dict) and "$regex" in val:
                regex = val["$regex"].replace("^", "")
                if not str(doc.get("event_id", "")).startswith(regex):
                    return False
                continue
            if key == "alert_id" and isinstance(val, dict) and "$regex" in val:
                regex = val["$regex"].replace("^", "")
                if not str(doc.get("alert_id", "")).startswith(regex):
                    return False
                continue
            if key == "current_score" and isinstance(val, dict) and "$lt" in val:
                if doc.get("current_score", 100) >= val["$lt"]:
                    return False
                continue
            if doc.get(key) != val:
                return False
        return True

    def find_one(self, query=None, projection=None):
        data = self._read_data()
        for doc in data:
            if self._match_query(doc, query):
                return doc
        return None

    def find(self, query=None, projection=None):
        data = self._read_data()
        matches = [doc for doc in data if self._match_query(doc, query)]
        
        class MockCursor(list):
            def sort(self, key_or_list, direction=1):
                if isinstance(key_or_list, list):
                    key = key_or_list[0][0]
                    rev = key_or_list[0][1] == -1
                else:
                    key = key_or_list
                    rev = direction == -1
                
                def get_sort_val(x):
                    val = x.get(key)
                    if val is None:
                        return datetime.min
                    if isinstance(val, str):
                        parsed = parse_date_robust(val)
                        if isinstance(parsed, datetime):
                            return parsed
                        return datetime.min
                    return val
                
                super().sort(key=get_sort_val, reverse=rev)
                return self
        
        return MockCursor(matches)

    def count_documents(self, query=None):
        return len(self.find(query))

    def insert_one(self, doc):
        data = self._read_data()
        if "_id" not in doc:
            doc["_id"] = str(datetime.now().timestamp())
        data.append(doc)
        self._write_data(data)
        return doc

    def insert_many(self, docs):
        data = self._read_data()
        for doc in docs:
            if "_id" not in doc:
                doc["_id"] = str(datetime.now().timestamp())
            data.append(doc)
        self._write_data(data)
        return docs

    def update_one(self, query, update, upsert=False):
        data = self._read_data()
        found = False
        
        set_fields = update.get("$set", {})
        setOnInsert = update.get("$setOnInsert", {})
        
        for doc in data:
            if self._match_query(doc, query):
                for k, v in set_fields.items():
                    if k.startswith("details."):
                        subkey = k.split(".")[1]
                        if "details" not in doc:
                            doc["details"] = {}
                        doc["details"][subkey] = v
                    else:
                        doc[k] = v
                found = True
                break
                
        if not found and upsert:
            new_doc = query.copy()
            for k, v in set_fields.items():
                if k.startswith("details."):
                    subkey = k.split(".")[1]
                    if "details" not in new_doc:
                        new_doc["details"] = {}
                    new_doc["details"][subkey] = v
                else:
                    new_doc[k] = v
            for k, v in setOnInsert.items():
                new_doc[k] = v
            data.append(new_doc)
            
        self._write_data(data)
        return found

    def update_many(self, query, update):
        data = self._read_data()
        set_fields = update.get("$set", {})
        count = 0
        for doc in data:
            if self._match_query(doc, query):
                for k, v in set_fields.items():
                    doc[k] = v
                count += 1
        if count > 0:
            self._write_data(data)
        return count

    def delete_many(self, query):
        data = self._read_data()
        original_len = len(data)
        data = [doc for doc in data if not self._match_query(doc, query)]
        if len(data) != original_len:
            self._write_data(data)
        return original_len - len(data)

    def create_index(self, keys, **kwargs):
        pass

    def bulk_write(self, operations):
        data = self._read_data()
        
        primary_key = None
        if operations:
            first_q = operations[0]._filter
            if len(first_q) == 1:
                key = list(first_q.keys())[0]
                if key in ["event_id", "employee_id", "alert_id"]:
                    primary_key = key
                    
        lookup = {}
        if primary_key:
            for doc in data:
                val = doc.get(primary_key)
                if val:
                    lookup[val] = doc
                    
        for op in operations:
            query = op._filter
            update = op._doc
            upsert = op._upsert
            
            found = False
            set_fields = update.get("$set", {})
            setOnInsert = update.get("$setOnInsert", {})
            
            if primary_key and primary_key in query:
                val = query[primary_key]
                doc = lookup.get(val)
                if doc:
                    for k, v in set_fields.items():
                        if k.startswith("details."):
                            subkey = k.split(".")[1]
                            if "details" not in doc:
                                doc["details"] = {}
                            doc["details"][subkey] = v
                        else:
                            doc[k] = v
                    found = True
            else:
                for doc in data:
                    if self._match_query(doc, query):
                        for k, v in set_fields.items():
                            if k.startswith("details."):
                                subkey = k.split(".")[1]
                                if "details" not in doc:
                                    doc["details"] = {}
                                doc["details"][subkey] = v
                            else:
                                doc[k] = v
                        found = True
                        break
                        
            if not found and upsert:
                new_doc = query.copy()
                for k, v in set_fields.items():
                    if k.startswith("details."):
                        subkey = k.split(".")[1]
                        if "details" not in new_doc:
                            new_doc["details"] = {}
                        new_doc["details"][subkey] = v
                    else:
                        new_doc[k] = v
                for k, v in setOnInsert.items():
                    new_doc[k] = v
                data.append(new_doc)
                if primary_key and primary_key in query:
                    lookup[query[primary_key]] = new_doc
                    
        self._write_data(data)


class MockDatabase:
    def __init__(self):
        self.employees = MockCollection("employees.json")
        self.events = MockCollection("events.json")
        self.trust_scores = MockCollection("trust_scores.json")
        self.alerts = MockCollection("alerts.json")
        self.simulations = MockCollection("simulations.json")

    def get_database(self):
        return self


def get_db(mongodb_uri=None):
    if not mongodb_uri:
        mongodb_uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/garudaai")
        if os.path.exists(".env"):
            with open(".env", "r") as f:
                for line in f:
                    if "=" in line and not line.startswith("#"):
                        k, v = line.strip().split("=", 1)
                        if k.strip() == "MONGODB_URI":
                            mongodb_uri = v.strip().strip('"').strip("'")
                            
    try:
        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=1000)
        client.server_info()
        print(f"Database Connected: Actual MongoDB Server ({mongodb_uri})")
        return client.get_database()
    except Exception:
        print("Database Connected: Fallback File-Based JSON Database (Active)")
        return MockDatabase()
