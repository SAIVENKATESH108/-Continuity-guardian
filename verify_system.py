import sys
import time
import httpx
import json

BASE_URL = "http://localhost:8000"

def verify():
    print("=" * 60)
    print(" CONTINUITY GUARDIAN — SYSTEM VERIFICATION")
    print("=" * 60)
    
    # 1. Health check
    print("\n1. Checking API Health (GET /health)...")
    try:
        r = httpx.get(f"{BASE_URL}/health", timeout=10.0)
        print(f"   Status Code: {r.status_code}")
        print(f"   Response:    {r.json()}")
        assert r.status_code == 200, "Health check failed"
        print("   [PASS] API is online and healthy!")
    except Exception as e:
        print(f"   [FAIL] Could not connect to API at {BASE_URL}.")
        print("   Make sure the FastAPI backend is running with:")
        print("   .venv\\Scripts\\uvicorn api.main:app --reload --host 127.0.0.1 --port 8000")
        sys.exit(1)

    # 2. Episodes list
    print("\n2. Checking Stored Episodes (GET /episodes)...")
    try:
        r = httpx.get(f"{BASE_URL}/episodes", timeout=10.0)
        print(f"   Status Code: {r.status_code}")
        episodes = r.json()
        print(f"   Episodes found: {len(episodes)}")
        print("   [PASS] Show Bible database connection verified!")
    except Exception as e:
        print(f"   [FAIL] Error querying episodes: {e}")

    # 3. Test script continuity check
    print("\n3. Testing Continuity Pipeline (POST /check-episode)...")
    sample_script = """INT. DETECTIVE OFFICE - DAY
MAYA sits across from her client, visibly shaken.
MAYA: My brother Daniel is still alive. I know it.
CLIENT: But the police said the accident happened near the Golden Gate Bridge.
MAYA: Bridges can be faked. Daniel once told me penicillin was discovered by Alexander Fleming in 1928.
CLIENT: So he is hiding somewhere in the city?
MAYA: He loved Seattle. Not Portland. Seattle.
The real question is why Apex Corp wants us to think he is dead."""

    payload = {
        "episode_id": "test_s01e01",
        "script_text": sample_script
    }
    
    print("   Sending test script to Gemini + Parallel AI checkers...")
    start_t = time.time()
    try:
        r = httpx.post(f"{BASE_URL}/check-episode", json=payload, timeout=120.0)
        elapsed = time.time() - start_t
        print(f"   Pipeline completed in {elapsed:.1f}s")
        print(f"   Status Code: {r.status_code}")
        
        if r.status_code == 200:
            report = r.json()
            print(f"\n   --- REPORT FOR: {report.get('episode_id')} ---")
            print(f"   Summary:\n   \"{report.get('summary')}\"")
            print(f"\n   Flagged Issues: {len(report.get('results', []))}")
            for i, item in enumerate(report.get("results", []), 1):
                claim = item.get("claim", {})
                print(f"     [{i}] Type: {claim.get('claim_type')}")
                print(f"         Claim:       \"{claim.get('text')}\"")
                print(f"         Contradiction: {item.get('is_contradiction')} (Confidence: {item.get('confidence')*100:.0f}%)")
                print(f"         Explanation:   {item.get('explanation')}")
                if item.get("suggested_fix"):
                    print(f"         Suggested Fix: {item.get('suggested_fix')}")
            print("\n   [PASS] Full End-to-End Pipeline is operational!")
        else:
            print(f"   [FAIL] Server returned error {r.status_code}: {r.text}")
    except Exception as e:
        print(f"   [FAIL] Pipeline test failed with error: {e}")

    print("\n" + "=" * 60)
    print(" Verification complete!")
    print("=" * 60)

if __name__ == "__main__":
    verify()
