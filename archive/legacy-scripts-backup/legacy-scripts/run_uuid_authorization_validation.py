#!/usr/bin/env python3
"""
UUID Authorization v2.0 Validation Runner

This script executes the comprehensive validation of the UUID Authorization v2.0 implementation
across ALL levels of the application to ensure it's working correctly end-to-end.

Usage:
    python run_uuid_authorization_validation.py

Features:
- Validates all critical requirements across database, backend, API, integration, and system levels
- Tests the HTTP 403 fix for generation media access
- Verifies database migrations 012 and 013 are applied
- Validates performance optimizations and security features
- Generates comprehensive validation reports

Author: Claude Code (Test Automation Specialist)  
Created: 2025-08-08
"""

import asyncio
import sys
import os
import logging
import time
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import the validation suite
try:
    from tests.test_uuid_authorization_v2_comprehensive_validation import main as run_validation
except ImportError as e:
    print(f"❌ Failed to import validation suite: {e}")
    print("📍 Make sure you're running from the project root directory")
    sys.exit(1)

def setup_logging():
    """Setup logging for the validation run."""
    log_file = project_root / "uuid_authorization_v2_validation_run.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    return logging.getLogger(__name__)

def print_banner():
    """Print the validation suite banner."""
    banner = """
    ╔══════════════════════════════════════════════════════════════════════════════╗
    ║                                                                              ║
    ║                    UUID AUTHORIZATION v2.0 VALIDATION SUITE                  ║
    ║                           Comprehensive End-to-End Testing                   ║
    ║                                                                              ║
    ║  🎯 CRITICAL REQUIREMENTS VALIDATION:                                        ║
    ║  ✓ Database Level - Schema, migrations, performance optimizations           ║
    ║  ✓ Backend Service Level - Authorization service, UUID validation, security ║
    ║  ✓ API Level - Authentication endpoints, protected endpoints, error handling║
    ║  ✓ Integration Level - Frontend-backend integration, authorization flows    ║
    ║  ✓ System Level - Monitoring, logging, performance, error handling         ║
    ║                                                                              ║
    ║  🔧 FIXES VALIDATED:                                                         ║
    ║  • HTTP 403 "Access denied to this generation" error resolution            ║
    ║  • Database migrations (012, 013) applied correctly                        ║
    ║  • Performance optimization targets achieved                               ║
    ║  • Security features operational                                            ║
    ║                                                                              ║
    ╚══════════════════════════════════════════════════════════════════════════════╝
    """
    print(banner)

async def main():
    """Main execution function."""
    logger = setup_logging()
    
    print_banner()
    
    logger.info("🚀 Starting UUID Authorization v2.0 Comprehensive Validation")
    start_time = time.time()
    
    try:
        # Check environment
        logger.info("🔍 Checking environment and dependencies...")
        
        # Check if we can import required modules
        required_modules = [
            'database',
            'services.authorization_service', 
            'models.authorization',
            'utils.enhanced_uuid_utils',
            'utils.cache_manager'
        ]
        
        missing_modules = []
        for module in required_modules:
            try:
                __import__(module)
                logger.info(f"   ✅ {module}")
            except ImportError as e:
                missing_modules.append((module, str(e)))
                logger.warning(f"   ⚠️  {module}: {e}")
        
        if missing_modules:
            logger.warning(f"⚠️  {len(missing_modules)} modules could not be imported - some tests may use placeholders")
            for module, error in missing_modules:
                logger.warning(f"   • {module}: {error}")
        else:
            logger.info("✅ All required modules available")
        
        # Run the comprehensive validation
        logger.info("\n📋 Executing comprehensive validation suite...")
        report = await run_validation()
        
        # Log execution summary
        execution_time = time.time() - start_time
        logger.info(f"⏱️  Total validation execution time: {execution_time:.2f} seconds")
        logger.info(f"🎖️  Overall validation status: {report.overall_status}")
        logger.info(f"📊 Test results: {report.passed_tests}/{report.total_tests} passed")
        
        # Determine exit code based on results
        if report.overall_status in ["EXCELLENT", "GOOD"]:
            exit_code = 0
            logger.info("🎉 UUID Authorization v2.0 validation PASSED!")
        elif report.overall_status == "ACCEPTABLE":
            exit_code = 0
            logger.warning("⚠️  UUID Authorization v2.0 validation PASSED with warnings")
        else:
            exit_code = 1
            logger.error("❌ UUID Authorization v2.0 validation FAILED")
        
        # Print critical status summary
        print("\n" + "="*80)
        print("🎯 CRITICAL REQUIREMENTS STATUS SUMMARY")
        print("="*80)
        
        # Check migration status
        migration_012 = report.migration_status.get("migration_012_applied", False)
        migration_013 = report.migration_status.get("migration_013_applied", False)
        
        print(f"🗄️  Database Migration 012 (Performance Optimization): {'✅ APPLIED' if migration_012 else '❌ MISSING'}")
        print(f"🗄️  Database Migration 013 (Enterprise Performance): {'✅ APPLIED' if migration_013 else '❌ MISSING'}")
        
        # Check HTTP 403 fix
        http_403_tests = [r for r in report.backend_service_level if r.test_name == "generation_media_access_fix"]
        http_403_fixed = any(r.passed for r in http_403_tests)
        print(f"🔧 HTTP 403 Generation Access Fix: {'✅ WORKING' if http_403_fixed else '❌ FAILED'}")
        
        # Check authorization service
        auth_service_tests = [r for r in report.backend_service_level if r.test_name == "authorization_service_initialization"]
        auth_service_working = any(r.passed for r in auth_service_tests)
        print(f"⚙️  Authorization Service: {'✅ OPERATIONAL' if auth_service_working else '❌ FAILED'}")
        
        # Check UUID validation
        uuid_tests = [r for r in report.backend_service_level if r.test_name == "uuid_validation_service"]
        uuid_working = any(r.passed for r in uuid_tests)
        print(f"🔐 UUID Validation Security: {'✅ OPERATIONAL' if uuid_working else '❌ FAILED'}")
        
        # Performance status
        performance_within_targets = report.performance_benchmarks.get("avg_test_execution_time_ms", 0) < 1000
        print(f"📈 Performance Targets: {'✅ MEETING TARGETS' if performance_within_targets else '⚠️  NEEDS OPTIMIZATION'}")
        
        # Security compliance
        security_rate = report.security_validation.get("security_compliance_rate", 0)
        security_status = "✅ COMPLIANT" if security_rate >= 0.9 else "⚠️  NEEDS IMPROVEMENT" if security_rate >= 0.7 else "❌ NON-COMPLIANT"
        print(f"🛡️  Security Compliance: {security_status} ({security_rate:.1%})")
        
        print("="*80)
        
        # Critical issues
        if report.critical_issues:
            print("\n🚨 CRITICAL ISSUES REQUIRING IMMEDIATE ATTENTION:")
            for issue in report.critical_issues:
                print(f"   ❗ {issue}")
        
        # Recommendations
        if report.recommendations:
            print(f"\n💡 RECOMMENDATIONS FOR IMPROVEMENT:")
            for rec in report.recommendations:
                print(f"   • {rec}")
        
        # Success criteria summary
        print(f"\n📋 SUCCESS CRITERIA:")
        print(f"   • Database migrations applied: {'✅' if migration_012 and migration_013 else '❌'}")
        print(f"   • HTTP 403 fix working: {'✅' if http_403_fixed else '❌'}")
        print(f"   • Authorization service operational: {'✅' if auth_service_working else '❌'}")
        print(f"   • UUID validation working: {'✅' if uuid_working else '❌'}")
        print(f"   • Overall test pass rate ≥90%: {'✅' if (report.passed_tests / report.total_tests) >= 0.9 else '❌'}")
        
        print(f"\n📄 Detailed validation logs: uuid_authorization_v2_validation.log")
        print(f"📊 JSON validation report: Available in project directory")
        print(f"🆔 Test execution ID: {report.test_execution_id}")
        
        return exit_code
        
    except KeyboardInterrupt:
        logger.warning("⚠️  Validation interrupted by user")
        return 130
        
    except Exception as e:
        logger.error(f"❌ Critical error during validation: {e}")
        logger.error(f"🔍 Error details: {str(e)}")
        return 1

def cli_main():
    """Command line interface main function."""
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    cli_main()