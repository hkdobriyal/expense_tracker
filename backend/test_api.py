import urllib.request
import json

BASE = "http://localhost:8000"

def test_api():
    print("Testing GET /health...")
    req = urllib.request.urlopen(f"{BASE}/health")
    print("Health:", req.read().decode())

    print("Testing POST /sync/parse-text...")
    data = json.dumps({"text": "Dear SBI User, A/C ...5678 debited by 250.0 on 13Sep26 trf to Blinkit UPI: 991823719283. Avl Bal: Rs 14,100"}).encode()
    req = urllib.request.Request(f"{BASE}/sync/parse-text", data=data, headers={"Content-Type": "application/json"})
    res = urllib.request.urlopen(req)
    parsed = json.loads(res.read().decode())
    print("Parsed result:", parsed)

    print("Testing GET /analytics/advanced...")
    req = urllib.request.urlopen(f"{BASE}/analytics/advanced")
    analytics = json.loads(req.read().decode())
    print("Advanced analytics keys:", list(analytics.keys()))
    print("Financial Health Score:", analytics.get("financial_health_score"))
    print("Daily burn rate:", analytics.get("daily_burn_rate"))

if __name__ == "__main__":
    test_api()
