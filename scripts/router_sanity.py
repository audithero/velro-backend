#!/usr/bin/env python3
"""
Router sanity check script
Tests that all routers can be imported successfully
"""

import importlib
import sys
import os

# Add parent directory to path to allow imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# List of routers to test
ROUTERS = [
    "routers.public",
    "routers.auth",
    "routers.projects",
    "routers.generations",
    "routers.models",
    "routers.credits",
    "routers.debug",
    "routers.diagnostics"
]

def test_router_imports():
    """Test importing all routers"""
    print("🔍 Testing router imports...")
    print("-" * 50)
    
    failed = []
    succeeded = []
    
    for module_name in ROUTERS:
        try:
            importlib.import_module(module_name)
            print(f"✅ {module_name:<30} OK")
            succeeded.append(module_name)
        except Exception as e:
            print(f"❌ {module_name:<30} FAILED: {e}", file=sys.stderr)
            failed.append((module_name, str(e)))
    
    print("-" * 50)
    print(f"\n📊 Results: {len(succeeded)} passed, {len(failed)} failed")
    
    if failed:
        print("\n❌ Failed imports:")
        for module, error in failed:
            print(f"  - {module}: {error}")
        return False
    else:
        print("\n✅ All routers imported successfully!")
        return True

if __name__ == "__main__":
    success = test_router_imports()
    sys.exit(0 if success else 1)