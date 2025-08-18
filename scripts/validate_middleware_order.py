#!/usr/bin/env python3
"""
Middleware Order Validation Script
Ensures the optimized middleware order is maintained in CI/CD.
"""

import sys
import re
from pathlib import Path

def validate_middleware_order():
    """
    Validate that middleware order in main.py follows the optimized pattern.
    Returns 0 on success, 1 on validation failure.
    """
    
    # Find main.py
    main_py = Path(__file__).parent.parent / "main.py"
    if not main_py.exists():
        print("❌ main.py not found")
        return 1
    
    content = main_py.read_text()
    
    # Expected middleware order (cheap → expensive)
    expected_order = [
        "CORSMiddleware",
        "TrustedHostMiddleware", 
        "GZipMiddleware",
        "ProductionOptimizedMiddleware",
        "AccessControlMiddleware",
        "SSRFProtectionMiddleware", 
        "SecureDesignMiddleware",
        "SecurityEnhancedMiddleware",
        "CSRFProtectionMiddleware",
        "RateLimitMiddleware"
    ]
    
    # Find middleware additions in main.py
    middleware_pattern = r'app\.add_middleware\(([^,\)]+)'
    middleware_matches = re.findall(middleware_pattern, content)
    
    # Extract middleware class names
    found_middleware = []
    for match in middleware_matches:
        # Clean up the match (remove imports, etc.)
        class_name = match.strip().split('.')[-1]
        if class_name in expected_order:
            found_middleware.append(class_name)
    
    print("🔍 Middleware Order Validation")
    print("=" * 40)
    
    # Check order
    validation_passed = True
    last_index = -1
    
    for middleware in found_middleware:
        if middleware in expected_order:
            current_index = expected_order.index(middleware)
            if current_index < last_index:
                print(f"❌ {middleware} is out of order (should come before previous middleware)")
                validation_passed = False
            else:
                print(f"✅ {middleware} - correct position")
            last_index = current_index
        else:
            print(f"⚠️ {middleware} - not in expected order list (manual review needed)")
    
    # Check for fastpath implementation
    print("\n🚀 Fastpath Implementation Check")
    print("=" * 40)
    
    fastpath_checks = [
        ("is_fastpath import", r'from middleware\.utils import.*is_fastpath'),
        ("AccessControl fastpath", r'if is_fastpath\(request\):.*access_control'),
        ("SecurityEnhanced fastpath", r'if is_fastpath\(request\):.*security_enhanced'),
        ("RateLimit fastpath", r'if is_fastpath\(request\):.*rate_limiting')
    ]
    
    for check_name, pattern in fastpath_checks:
        if re.search(pattern, content, re.DOTALL | re.IGNORECASE):
            print(f"✅ {check_name} - implemented")
        else:
            print(f"❌ {check_name} - missing")
            validation_passed = False
    
    # Check configuration
    print("\n⚙️ Configuration Check")
    print("=" * 40)
    
    config_py = Path(__file__).parent.parent / "config.py"
    if config_py.exists():
        config_content = config_py.read_text()
        if 'fastpath_exempt_paths' in config_content:
            print("✅ fastpath_exempt_paths - configured")
            
            # Check for required endpoints
            required_endpoints = [
                '/health',
                '/api/v1/auth/ping',
                '/api/v1/auth/login'
            ]
            
            for endpoint in required_endpoints:
                if endpoint in config_content:
                    print(f"✅ {endpoint} - in fastpath config")
                else:
                    print(f"❌ {endpoint} - missing from fastpath config")
                    validation_passed = False
        else:
            print("❌ fastpath_exempt_paths - not configured")
            validation_passed = False
    else:
        print("❌ config.py not found")
        validation_passed = False
    
    # Summary
    print("\n" + "=" * 40)
    if validation_passed:
        print("🎉 All middleware optimizations validated successfully!")
        print("\n✅ Ready for deployment:")
        print("   - Middleware order optimized")
        print("   - Fastpath implementation complete")
        print("   - Configuration properly set")
        return 0
    else:
        print("❌ Middleware validation failed!")
        print("\n🔧 Action required:")
        print("   - Fix middleware order issues")
        print("   - Implement missing fastpath bypasses")
        print("   - Update configuration")
        return 1

def main():
    """Main execution function for CI/CD integration."""
    try:
        exit_code = validate_middleware_order()
        sys.exit(exit_code)
    except Exception as e:
        print(f"❌ Validation script failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()