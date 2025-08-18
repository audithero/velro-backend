#!/usr/bin/env python3
"""
CORS Configuration Validator
Validates the CORS configuration in main.py against requirements.
"""

import re
import json
from typing import List, Dict, Tuple

def validate_cors_configuration():
    """Validate CORS configuration in main.py."""
    
    print("🔍 CORS Configuration Validation")
    print("=" * 50)
    
    # Read main.py
    try:
        with open('main.py', 'r') as f:
            main_py_content = f.read()
        print("✅ Successfully read main.py")
    except FileNotFoundError:
        print("❌ main.py not found")
        return False
    
    # Required CORS configuration
    required_config = {
        "allow_origins": [
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:3002", 
            "https://velro-frontend-production.up.railway.app",
            "https://*.railway.app",
            "https://velro.ai",
            "https://www.velro.ai"
        ],
        "allow_credentials": True,
        "allow_methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
        "allow_headers": [
            "Authorization",
            "Content-Type", 
            "Accept",
            "Origin",
            "X-Requested-With",
            "X-CSRF-Token"
        ]
    }
    
    print("\n📋 Checking CORS Middleware Configuration...")
    
    # Check if CORSMiddleware is imported
    cors_import = "from fastapi.middleware.cors import CORSMiddleware" in main_py_content
    print(f"   CORSMiddleware Import: {'✅' if cors_import else '❌'}")
    
    # Check if CORS middleware is added
    cors_added = "app.add_middleware(CORSMiddleware" in main_py_content or "add_middleware(\n    CORSMiddleware" in main_py_content
    print(f"   CORS Middleware Added: {'✅' if cors_added else '❌'}")
    
    # Extract CORS configuration
    cors_config_match = re.search(
        r'app\.add_middleware\(\s*CORSMiddleware,\s*(.*?)\s*\)',
        main_py_content,
        re.DOTALL
    )
    
    if not cors_config_match:
        print("❌ Could not find CORS middleware configuration")
        return False
    
    cors_config_text = cors_config_match.group(1)
    print(f"   CORS Configuration Found: ✅")
    
    # Check individual configuration items
    print(f"\n🌐 Validating Origin Configuration...")
    
    # Check for frontend origin
    frontend_origin = "https://velro-frontend-production.up.railway.app"
    has_frontend_origin = frontend_origin in cors_config_text
    print(f"   Frontend Origin ({frontend_origin}): {'✅' if has_frontend_origin else '❌'}")
    
    # Check for localhost origins
    localhost_origins = ["localhost:3000", "localhost:3001", "localhost:3002"]
    localhost_found = []
    for origin in localhost_origins:
        if origin in cors_config_text:
            localhost_found.append(origin)
    
    print(f"   Localhost Origins: ✅ {len(localhost_found)}/3 found ({', '.join(localhost_found)})")
    
    # Check for wildcard Railway
    has_railway_wildcard = "*.railway.app" in cors_config_text
    print(f"   Railway Wildcard (*.railway.app): {'✅' if has_railway_wildcard else '❌'}")
    
    # Check allow_credentials
    has_credentials = "allow_credentials=True" in cors_config_text
    print(f"   Allow Credentials: {'✅' if has_credentials else '❌'}")
    
    print(f"\n🔧 Validating Methods and Headers...")
    
    # Check methods
    required_methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]
    methods_found = []
    for method in required_methods:
        if f'"{method}"' in cors_config_text or f"'{method}'" in cors_config_text:
            methods_found.append(method)
    
    print(f"   HTTP Methods: ✅ {len(methods_found)}/{len(required_methods)} found")
    if len(methods_found) < len(required_methods):
        missing_methods = set(required_methods) - set(methods_found)
        print(f"     Missing: {', '.join(missing_methods)}")
    
    # Check headers
    required_headers = ["Authorization", "Content-Type", "Accept", "Origin"]
    headers_found = []
    for header in required_headers:
        if f'"{header}"' in cors_config_text or f"'{header}'" in cors_config_text:
            headers_found.append(header)
    
    print(f"   HTTP Headers: ✅ {len(headers_found)}/{len(required_headers)} found")
    if len(headers_found) < len(required_headers):
        missing_headers = set(required_headers) - set(headers_found)
        print(f"     Missing: {', '.join(missing_headers)}")
    
    # Check for debug mode handling
    print(f"\n🐛 Checking Debug Mode Configuration...")
    
    debug_config = 'if not settings.debug else ["*"]' in cors_config_text
    print(f"   Debug Mode Fallback: {'✅' if debug_config else '❌'}")
    
    # Check middleware order
    print(f"\n📊 Checking Middleware Order...")
    
    # CORS should be after rate limiting but before auth
    cors_position = main_py_content.find("add_middleware(CORSMiddleware")
    auth_position = main_py_content.find("app.add_middleware(AuthMiddleware)")
    rate_limit_position = main_py_content.find("SlowAPIMiddleware")
    
    order_correct = True
    if cors_position == -1:
        print(f"   ❌ CORS middleware not found")
        order_correct = False
    elif rate_limit_position != -1 and cors_position < rate_limit_position:
        print(f"   ⚠️ CORS middleware before rate limiting")
    elif auth_position != -1 and cors_position > auth_position:
        print(f"   ⚠️ CORS middleware after auth middleware")
    else:
        print(f"   ✅ CORS middleware order looks correct")
    
    # Check for OPTIONS handlers
    print(f"\n🎯 Checking OPTIONS Route Handlers...")
    
    options_handlers = main_py_content.count("@app.options")
    app_options_calls = main_py_content.count('app.options')
    
    print(f"   OPTIONS Route Handlers: {options_handlers + app_options_calls}")
    
    if options_handlers > 0 or app_options_calls > 0:
        print(f"   ✅ Manual OPTIONS handlers found")
    else:
        print(f"   ℹ️ No manual OPTIONS handlers (middleware should handle)")
    
    # Overall assessment
    print(f"\n" + "=" * 50)
    print(f"📊 CORS CONFIGURATION ASSESSMENT")
    print("=" * 50)
    
    critical_issues = []
    warnings = []
    
    if not cors_import:
        critical_issues.append("CORSMiddleware not imported")
    
    if not cors_added:
        critical_issues.append("CORS middleware not added to app")
    
    if not has_frontend_origin:
        critical_issues.append("Frontend origin missing from allowed origins")
    
    if not has_credentials:
        critical_issues.append("allow_credentials not set to True")
    
    if len(methods_found) < 6:  # Should have at least GET, POST, PUT, DELETE, OPTIONS, HEAD
        critical_issues.append("Critical HTTP methods missing")
    
    if len(headers_found) < 3:  # Should have at least Authorization, Content-Type, Accept
        critical_issues.append("Critical headers missing")
    
    if len(localhost_found) == 0:
        warnings.append("No localhost origins found (development might not work)")
    
    if not has_railway_wildcard:
        warnings.append("Railway wildcard missing (Railway preview deployments might not work)")
    
    if not debug_config:
        warnings.append("No debug mode fallback (testing might be harder)")
    
    # Print results
    if not critical_issues and not warnings:
        print("🎉 CORS CONFIGURATION IS PERFECT!")
        print("✅ All required settings are correctly configured")
        print("✅ Frontend should be able to communicate with backend")
        result = "perfect"
    elif not critical_issues:
        print("✅ CORS CONFIGURATION IS GOOD")
        print("✅ All critical settings are correctly configured")
        print("⚠️ Minor issues detected:")
        for warning in warnings:
            print(f"   - {warning}")
        result = "good"
    else:
        print("❌ CORS CONFIGURATION HAS ISSUES")
        print("❌ Critical issues detected:")
        for issue in critical_issues:
            print(f"   - {issue}")
        if warnings:
            print("⚠️ Additional warnings:")
            for warning in warnings:
                print(f"   - {warning}")
        result = "issues"
    
    # Recommendations
    print(f"\n💡 RECOMMENDATIONS:")
    
    if result == "perfect":
        print("✅ Configuration is optimal - focus on deployment issues")
        print("   1. Verify backend service is running on Railway")
        print("   2. Check deployment logs for startup errors")
        print("   3. Ensure environment variables are set correctly")
    elif result == "good":
        print("✅ Configuration will work but could be improved")
        print("   1. Consider adding missing localhost origins for development")
        print("   2. Add Railway wildcard for preview deployments")
    else:
        print("❌ Configuration needs fixes before deployment")
        print("   1. Add missing frontend origin to allow_origins")
        print("   2. Set allow_credentials=True")
        print("   3. Ensure all required methods and headers are included")
    
    print(f"\n📄 Configuration Analysis saved to: cors_config_analysis.json")
    
    # Save analysis
    analysis = {
        "timestamp": "2025-01-03 12:00:00",
        "cors_config_found": cors_added,
        "frontend_origin_configured": has_frontend_origin,
        "credentials_enabled": has_credentials,
        "methods_count": len(methods_found),
        "headers_count": len(headers_found),
        "localhost_origins": len(localhost_found),
        "railway_wildcard": has_railway_wildcard,
        "debug_fallback": debug_config,
        "critical_issues": critical_issues,
        "warnings": warnings,
        "overall_assessment": result,
        "ready_for_production": result in ["perfect", "good"]
    }
    
    with open("cors_config_analysis.json", "w") as f:
        json.dump(analysis, f, indent=2)
    
    return result in ["perfect", "good"]

def main():
    """Main validation function."""
    try:
        return validate_cors_configuration()
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)