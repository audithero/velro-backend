#!/usr/bin/env python3
"""
Emergency Application Discovery
Find any working endpoints or determine if application is down.
"""

import requests
import json
from datetime import datetime

BASE_URL = "https://velro-backend-production.up.railway.app"

def test_basic_endpoints():
    """Test basic endpoints to see if app is running at all."""
    session = requests.Session()
    
    endpoints_to_try = [
        "/",
        "/health",
        "/status", 
        "/api",
        "/api/v1",
        "/api/v1/health",
        "/api/health",
        "/ping",
        "/docs",
        "/openapi.json",
        "/favicon.ico",
        "/robots.txt"
    ]
    
    results = []
    
    for endpoint in endpoints_to_try:
        try:
            url = f"{BASE_URL}{endpoint}"
            response = session.get(url, timeout=10)
            
            result = {
                "endpoint": endpoint,
                "url": url,
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "text": response.text[:200] if response.text else None,
                "working": 200 <= response.status_code < 300
            }
            
            if result["working"]:
                print(f"✅ WORKING: {endpoint} -> {response.status_code}")
                try:
                    result["json"] = response.json()
                except:
                    pass
            else:
                print(f"❌ FAILED: {endpoint} -> {response.status_code}: {result['text']}")
                
        except Exception as e:
            result = {
                "endpoint": endpoint,
                "url": f"{BASE_URL}{endpoint}",
                "error": str(e),
                "working": False
            }
            print(f"💥 ERROR: {endpoint} -> {str(e)}")
            
        results.append(result)
    
    return results

def test_common_framework_patterns():
    """Test common FastAPI/Flask patterns."""
    session = requests.Session()
    
    patterns = [
        # FastAPI patterns
        "/docs",
        "/redoc", 
        "/openapi.json",
        "/api/v1/docs",
        
        # Flask patterns
        "/api/spec",
        "/swagger",
        "/swagger-ui",
        
        # Generic health checks
        "/healthz",
        "/ready",
        "/live",
        "/version",
        "/info"
    ]
    
    print("\n🔍 Testing Framework Patterns...")
    results = []
    
    for pattern in patterns:
        try:
            url = f"{BASE_URL}{pattern}"
            response = session.get(url, timeout=5)
            
            if response.status_code != 404:
                print(f"📍 FOUND: {pattern} -> {response.status_code}")
                result = {
                    "pattern": pattern,
                    "status_code": response.status_code,
                    "content_type": response.headers.get("content-type", ""),
                    "text": response.text[:300]
                }
                results.append(result)
                
        except Exception as e:
            print(f"❌ {pattern} -> Error: {str(e)}")
    
    return results

def check_dns_and_connectivity():
    """Check if DNS resolves and basic connectivity works."""
    import socket
    
    print("\n🌐 DNS and Connectivity Check...")
    
    try:
        # Extract hostname
        hostname = BASE_URL.replace("https://", "").replace("http://", "")
        print(f"Hostname: {hostname}")
        
        # DNS lookup
        ip = socket.gethostbyname(hostname)
        print(f"✅ DNS resolves to: {ip}")
        
        # Port check
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((hostname, 443))
        sock.close()
        
        if result == 0:
            print("✅ Port 443 is open")
        else:
            print("❌ Port 443 is not accessible")
            
        return True
        
    except Exception as e:
        print(f"❌ DNS/Connectivity error: {str(e)}")
        return False

def main():
    """Main discovery function."""
    print("🚨 EMERGENCY APPLICATION DISCOVERY")
    print(f"🎯 Target: {BASE_URL}")
    print("=" * 60)
    
    # Check basic connectivity
    connectivity_ok = check_dns_and_connectivity()
    
    # Test basic endpoints
    print("\n🔍 Testing Basic Endpoints...")
    basic_results = test_basic_endpoints()
    
    # Test framework patterns
    framework_results = test_common_framework_patterns()
    
    # Summary
    working_basic = [r for r in basic_results if r.get("working", False)]
    
    print("\n" + "=" * 60)
    print("📊 DISCOVERY SUMMARY")
    print("=" * 60)
    
    print(f"DNS/Connectivity: {'✅ OK' if connectivity_ok else '❌ FAILED'}")
    print(f"Working Basic Endpoints: {len(working_basic)}")
    print(f"Framework Patterns Found: {len(framework_results)}")
    
    if working_basic:
        print("\n✅ WORKING ENDPOINTS:")
        for result in working_basic:
            print(f"  {result['endpoint']} -> {result['status_code']}")
            if result.get('json'):
                print(f"    Response: {result['json']}")
    
    if framework_results:
        print("\n📍 DISCOVERED PATTERNS:")
        for result in framework_results:
            print(f"  {result['pattern']} -> {result['status_code']} ({result['content_type']})")
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"emergency_discovery_results_{timestamp}.json"
    
    output = {
        "timestamp": datetime.now().isoformat(),
        "base_url": BASE_URL,
        "connectivity_check": connectivity_ok,
        "basic_endpoints": basic_results,
        "framework_patterns": framework_results,
        "summary": {
            "working_endpoints": len(working_basic),
            "patterns_found": len(framework_results)
        }
    }
    
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n💾 Results saved to: {output_file}")
    
    if not working_basic and not framework_results:
        print("\n🚨 CRITICAL: No working endpoints found!")
        print("   This suggests the application may be:")
        print("   1. Not deployed/running")
        print("   2. Running on different URL")
        print("   3. Behind authentication wall")
        print("   4. Misconfigured routing")
    
    return output_file

if __name__ == "__main__":
    main()