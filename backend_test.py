#!/usr/bin/env python3
"""
Backend integration test for SynthTest external integrations:
1. LLM persona generation (Emergent Universal Key + gpt-5)
2. Cloudinary mockup upload
3. Browserbase runtime persona run (full engine loop)
"""

import asyncio
import io
import time
import sys
from PIL import Image
import requests

import os

# Backend base URL from env or default to local
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8001/api").rstrip("/")

def create_test_png() -> bytes:
    """Create a small valid PNG image in memory."""
    img = Image.new('RGB', (100, 100), color='red')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf.read()


def test_llm_persona_generation():
    """Test 1: LLM persona generation via POST /api/generate-personas"""
    print("\n" + "="*80)
    print("TEST 1: LLM Persona Generation (Emergent Universal Key + gpt-5)")
    print("="*80)
    
    url = f"{BASE_URL}/generate-personas"
    payload = {
        "audience_description": "budget travelers on mobile",
        "count": 3
    }
    
    print(f"POST {url}")
    print(f"Payload: {payload}")
    
    try:
        response = requests.post(url, json=payload, timeout=60)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            personas = data.get("personas", [])
            print(f"✅ SUCCESS: Received {len(personas)} personas")
            
            if len(personas) == 3:
                print("✅ Correct count (3 personas)")
                for i, p in enumerate(personas):
                    print(f"  Persona {i+1}: {p.get('name', 'UNNAMED')}")
                return True
            else:
                print(f"❌ FAIL: Expected 3 personas, got {len(personas)}")
                return False
        else:
            print(f"❌ FAIL: HTTP {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return False
            
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        return False


def test_cloudinary_upload():
    """Test 2: Cloudinary mockup upload via POST /api/prototype/upload-mockup"""
    print("\n" + "="*80)
    print("TEST 2: Cloudinary Mockup Upload")
    print("="*80)
    
    url = f"{BASE_URL}/prototype/upload-mockup"
    
    # Create a small test PNG
    png_bytes = create_test_png()
    print(f"Created test PNG: {len(png_bytes)} bytes")
    
    files = {
        'file': ('test_mockup.png', png_bytes, 'image/png')
    }
    
    print(f"POST {url}")
    
    try:
        response = requests.post(url, files=files, timeout=30)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            url_field = data.get("url", "")
            public_id = data.get("public_id", "")
            
            print(f"✅ SUCCESS: Upload completed")
            print(f"  URL: {url_field}")
            print(f"  Public ID: {public_id}")
            
            # Verify it's a Cloudinary secure URL
            if "res.cloudinary.com" in url_field and url_field.startswith("https://"):
                print("✅ Valid Cloudinary secure_url")
                return True
            else:
                print(f"❌ FAIL: URL doesn't look like Cloudinary secure_url: {url_field}")
                return False
                
        elif response.status_code == 502:
            print(f"❌ FAIL: 502 Bad Gateway - Cloudinary credentials likely wrong")
            print(f"Response: {response.text[:500]}")
            return False
        else:
            print(f"❌ FAIL: HTTP {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return False
            
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        return False


def test_browserbase_runtime_run():
    """Test 3: Full Browserbase runtime persona run"""
    print("\n" + "="*80)
    print("TEST 3: Browserbase Runtime Persona Run (Full Engine Loop)")
    print("="*80)
    
    # Step 3a: Get seed panel ID
    print("\nStep 3a: Getting seed panel ID...")
    panels_url = f"{BASE_URL}/persona-panels"
    
    try:
        response = requests.get(panels_url, timeout=10)
        if response.status_code != 200:
            print(f"❌ FAIL: Could not fetch persona panels (HTTP {response.status_code})")
            return False
            
        panels = response.json()
        seed_panel = None
        for panel in panels:
            if panel.get("client_ref") == "seed-demo":
                seed_panel = panel
                break
        
        if not seed_panel:
            print("❌ FAIL: seed-demo panel not found")
            return False
            
        seed_panel_id = seed_panel.get("id")
        print(f"✅ Found seed panel: {seed_panel_id}")
        
    except Exception as e:
        print(f"❌ EXCEPTION getting panels: {e}")
        return False
    
    # Step 3b: Check credits
    print("\nStep 3b: Checking run credits...")
    credits_url = f"{BASE_URL}/payments/credits"
    
    try:
        response = requests.get(credits_url, timeout=10)
        if response.status_code != 200:
            print(f"❌ FAIL: Could not check credits (HTTP {response.status_code})")
            return False
            
        credits = response.json()
        can_run = credits.get("can_run", False)
        print(f"Credits response: {credits}")
        
        if not can_run:
            print("❌ FAIL: can_run is false - no credits available")
            return False
            
        print("✅ can_run is true")
        
    except Exception as e:
        print(f"❌ EXCEPTION checking credits: {e}")
        return False
    
    # Step 3c: Start the run
    print("\nStep 3c: Starting runtime engine run...")
    run_url = f"{BASE_URL}/engine/run"
    run_payload = {
        "target_url": "https://example.com",
        "goal": "Find and read the more-information link",
        "stage": "runtime",
        "persona_panel_id": seed_panel_id,
        "persona_index": 0
    }
    
    print(f"POST {run_url}")
    print(f"Payload: {run_payload}")
    
    try:
        response = requests.post(run_url, json=run_payload, timeout=30)
        print(f"Status: {response.status_code}")
        
        if response.status_code != 202:
            print(f"❌ FAIL: Expected HTTP 202, got {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return False
            
        data = response.json()
        run_id = data.get("run_id")
        
        if not run_id:
            print(f"❌ FAIL: No run_id in response")
            print(f"Response: {data}")
            return False
            
        print(f"✅ Run started: {run_id}")
        
    except Exception as e:
        print(f"❌ EXCEPTION starting run: {e}")
        return False
    
    # Step 3d: Poll for completion
    print("\nStep 3d: Polling for run completion (max 3 minutes)...")
    status_url = f"{BASE_URL}/engine/run/{run_id}"
    
    max_polls = 18  # 18 * 10s = 3 minutes
    poll_interval = 10
    
    for poll_count in range(max_polls):
        print(f"  Poll {poll_count + 1}/{max_polls} (waiting {poll_interval}s)...")
        time.sleep(poll_interval)
        
        try:
            response = requests.get(status_url, timeout=10)
            if response.status_code != 200:
                print(f"❌ FAIL: Status check failed (HTTP {response.status_code})")
                return False
                
            run_data = response.json()
            outcome = run_data.get("outcome", "in_progress")
            still_running = run_data.get("still_running", False)
            
            print(f"    Outcome: {outcome}, still_running: {still_running}")
            
            if outcome != "in_progress":
                # Run completed
                print(f"\n✅ Run completed with outcome: {outcome}")
                
                steps = run_data.get("steps", [])
                total_steps = run_data.get("total_steps", len(steps))
                browserbase_session_id = run_data.get("browserbase_session_id")
                
                print(f"  Total steps: {total_steps}")
                print(f"  Browserbase session: {browserbase_session_id}")
                
                # SUCCESS CRITERIA: at least one real step with a Cloudinary screenshot
                if total_steps == 0:
                    print("\n❌ FAIL: Run gave up with ZERO steps")
                    print("This indicates a silent failure. Checking backend logs...")
                    return False
                
                # Check for real steps with screenshots
                real_steps_with_screenshots = 0
                for step in steps:
                    action = step.get("action", {})
                    action_type = action.get("type", "")
                    screenshot_before = step.get("screenshot_before_url", "")
                    screenshot_after = step.get("screenshot_after_url", "")
                    
                    # Real step = not just "wait"
                    if action_type != "wait":
                        if screenshot_before and "res.cloudinary.com" in screenshot_before:
                            real_steps_with_screenshots += 1
                            print(f"  Step {step.get('index')}: {action_type} - screenshot: {screenshot_before[:80]}...")
                
                if real_steps_with_screenshots > 0:
                    print(f"\n✅✅ SUCCESS: {real_steps_with_screenshots} real steps with Cloudinary screenshots")
                    print("Browserbase navigation and Cloudinary screenshot upload both working!")
                    return True
                else:
                    print(f"\n❌ FAIL: No real steps with Cloudinary screenshots found")
                    print("Run completed but didn't produce expected results")
                    if outcome == "gave_up" and total_steps <= 1:
                        print("This looks like a silent failure - check backend logs")
                    return False
                    
        except Exception as e:
            print(f"❌ EXCEPTION during polling: {e}")
            return False
    
    # Timeout
    print(f"\n❌ FAIL: Run did not complete within {max_polls * poll_interval} seconds")
    return False


def main():
    """Run all integration tests in order."""
    print("\n" + "="*80)
    print("SYNTHTEST BACKEND INTEGRATION TESTS")
    print("Testing: LLM (Emergent), Cloudinary, Browserbase")
    print("="*80)
    
    results = {}
    
    # Test 1: LLM (optional quick re-confirm)
    results["llm"] = test_llm_persona_generation()
    
    # Test 2: Cloudinary (HIGH PRIORITY)
    results["cloudinary"] = test_cloudinary_upload()
    
    # Test 3: Browserbase runtime (HIGH PRIORITY)
    results["browserbase"] = test_browserbase_runtime_run()
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name.upper()}: {status}")
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED")
        return 0
    else:
        print("\n⚠️  SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
