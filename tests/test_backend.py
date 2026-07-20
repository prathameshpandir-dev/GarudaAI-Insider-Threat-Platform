import os
import sys
import unittest
from datetime import datetime

# Add root folder to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.db_client import get_db
from backend.trust_score import evaluate_event_deduction, recalculate_score
from backend.app import app

class TestGarudaAIBackend(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        # Configure app in testing mode
        app.config["TESTING"] = True
        cls.client = app.test_client()
        cls.db = get_db()

    def test_01_evaluate_event_deduction(self):
        """Test score engine point deduction evaluations."""
        # 1. Normal logon (no deductions)
        normal_logon = {
            "type": "logon",
            "details": {
                "is_after_hours": False,
                "is_known_device": True,
                "location": "New York"
            }
        }
        deductions = evaluate_event_deduction(normal_logon)
        self.assertEqual(len(deductions), 0)

        # 2. Anomalous logon (after hours + unknown device)
        bad_logon = {
            "type": "logon",
            "details": {
                "is_after_hours": True,
                "is_known_device": False,
                "location": "Beijing"
            }
        }
        deductions = evaluate_event_deduction(bad_logon)
        self.assertEqual(len(deductions), 2)
        total_deduction = sum(d[1] for d in deductions)
        self.assertEqual(total_deduction, 8.0) # 3.0 (after hours) + 5.0 (unknown)

        # 3. Restricted File Read
        restricted_file = {
            "type": "file",
            "details": {
                "file_sensitivity": "Restricted",
                "file_size_mb": 45.0,
                "action": "Read"
            }
        }
        deductions = evaluate_event_deduction(restricted_file)
        self.assertEqual(len(deductions), 1)
        self.assertEqual(deductions[0][1], 8.0) # restricted_file_access (-8)

    def test_02_recalculate_score(self):
        """Test chronological score calculation and recovery."""
        # Query score for EMP015
        score = recalculate_score(self.db, "EMP015")
        employee = self.db.employees.find_one({"employee_id": "EMP015"})
        
        # Verify score matches saved field
        self.assertEqual(score, employee["current_score"])
        
        # Verify history is saved
        history_count = self.db.trust_scores.count_documents({"employee_id": "EMP015"})
        self.assertGreater(history_count, 0)

    def test_03_api_health(self):
        """Verify health check endpoint returns 200."""
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "healthy")

    def test_04_api_get_employees(self):
        """Verify fetching employee list returns 150 items."""
        res = self.client.get("/api/employees")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 150)

    def test_05_api_get_timeline(self):
        """Verify timeline query contains collapsed items."""
        res = self.client.get("/api/employees/EMP055/timeline")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

    def test_06_api_alerts(self):
        """Verify alerts listing returns active threats."""
        res = self.client.get("/api/alerts")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

    def test_07_api_simulation_flow(self):
        """Verify end-to-end simulation trigger, score recalc, and alert injection."""
        # 1. Reset database to clean baseline
        self.client.post("/api/reset")
        
        # 2. Trigger simulation for employee EMP032
        res = self.client.post("/api/simulate", json={
            "scenario": "mass_download",
            "employee_id": "EMP032"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        
        # Verify recalculation took place
        self.assertLess(data["new_score"], 90.0)
        self.assertEqual(data["events_injected"], 30)
        
        # Verify alert was created
        alert = self.db.alerts.find_one({"alert_id": data["alert_id"]})
        self.assertIsNotNone(alert)
        self.assertEqual(alert["type"], "Mass File Download")

        # 3. Clean up simulator logs
        self.client.post("/api/reset")

if __name__ == "__main__":
    unittest.main()
