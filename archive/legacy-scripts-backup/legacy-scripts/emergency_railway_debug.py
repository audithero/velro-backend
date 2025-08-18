#!/usr/bin/env python3
"""
Emergency Railway deployment debugging utility
Analyzes the current deployment state and provides recovery instructions.
"""
import subprocess
import json
import sys
from datetime import datetime

def run_command(cmd, capture_output=True):
    """Run a shell command and return result"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=capture_output, text=True)
        return {
            "command": cmd,
            "returncode": result.returncode,
            "stdout": result.stdout.strip() if result.stdout else "",
            "stderr": result.stderr.strip() if result.stderr else "",
            "success": result.returncode == 0
        }
    except Exception as e:
        return {
            "command": cmd,
            "error": str(e),
            "success": False
        }

def main():
    print("🚨 EMERGENCY RAILWAY DEPLOYMENT DEBUG")
    print("=" * 50)
    
    debug_info = {
        "timestamp": datetime.now().isoformat(),
        "issue": "Complete service outage - application not found",
        "diagnosis": {},
        "recovery_steps": []
    }
    
    # Check Railway authentication
    print("\n1. Checking Railway authentication...")
    auth_result = run_command("railway whoami")
    debug_info["diagnosis"]["auth"] = auth_result
    if auth_result["success"]:
        print(f"✅ Authenticated as: {auth_result['stdout']}")
    else:
        print("❌ Not authenticated to Railway")
        debug_info["recovery_steps"].append("Login to Railway: railway login")
    
    # Check Railway projects
    print("\n2. Checking Railway projects...")
    projects_result = run_command("railway list")
    debug_info["diagnosis"]["projects"] = projects_result
    if projects_result["success"]:
        print(f"📋 Projects: {projects_result['stdout']}")
    else:
        print("❌ Failed to list projects")
    
    # Check current environment
    print("\n3. Checking current environment...")
    env_result = run_command("railway status")
    debug_info["diagnosis"]["environment"] = env_result
    if not env_result["success"]:
        print("❌ No linked environment")
        debug_info["recovery_steps"].append("Link to environment: railway connect velro-production")
    
    # Check service status
    print("\n4. Checking service status...")
    service_result = run_command("railway domain")
    debug_info["diagnosis"]["service"] = service_result
    if not service_result["success"]:
        print("❌ No service found")
        debug_info["recovery_steps"].append("Deploy new service: railway up --detach")
    
    # Test current endpoint
    print("\n5. Testing current endpoint...")
    endpoint_result = run_command("curl -s https://velro-backend-production.up.railway.app/")
    debug_info["diagnosis"]["endpoint"] = endpoint_result
    if "Application not found" in endpoint_result.get("stdout", ""):
        print("❌ Endpoint returns 'Application not found' - service is down")
        debug_info["recovery_steps"].append("Service needs complete redeployment")
    
    # Check local files
    print("\n6. Checking local deployment files...")
    files_to_check = ["main.py", "requirements.txt", "Dockerfile", "railway.toml"]
    for file in files_to_check:
        file_result = run_command(f"ls -la {file}")
        debug_info["diagnosis"][f"file_{file}"] = file_result["success"]
        print(f"{'✅' if file_result['success'] else '❌'} {file}")
    
    # Generate report
    print(f"\n📊 DIAGNOSIS COMPLETE")
    print("=" * 50)
    
    if debug_info["recovery_steps"]:
        print("\n🔧 REQUIRED RECOVERY STEPS:")
        for i, step in enumerate(debug_info["recovery_steps"], 1):
            print(f"{i}. {step}")
    
    print(f"\n🚨 ROOT CAUSE: Railway service is completely missing or disconnected")
    print(f"🎯 SOLUTION: Redeploy service to Railway")
    
    # Save debug report
    with open("emergency_debug_report.json", "w") as f:
        json.dump(debug_info, f, indent=2)
    
    print(f"\n📄 Debug report saved to: emergency_debug_report.json")
    
    return debug_info

if __name__ == "__main__":
    main()