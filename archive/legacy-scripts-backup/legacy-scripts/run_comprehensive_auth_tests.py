#!/usr/bin/env python3
"""
Comprehensive Authentication Test Runner
Emergency Auth Validation Swarm - Master Test Orchestrator
Version: 1.0.0

This script orchestrates all authentication testing components:
1. Comprehensive functional tests
2. Security penetration tests
3. Load/performance tests
4. Browser integration tests
5. Report generation and analysis
"""

import asyncio
import subprocess
import sys
import os
import json
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
import logging
import argparse

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AuthTestOrchestrator:
    """Master orchestrator for all authentication tests"""
    
    def __init__(self, base_url: str = "https://velro-backend.railway.app"):
        self.base_url = base_url
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.results_dir = f"auth_test_suite_results_{self.timestamp}"
        self.test_results = {
            "timestamp": datetime.now().isoformat(),
            "base_url": base_url,
            "test_suite_version": "1.0.0",
            "test_components": {},
            "overall_summary": {
                "total_tests": 0,
                "passed_tests": 0,
                "failed_tests": 0,
                "warning_tests": 0,
                "security_issues": 0,
                "performance_metrics": {}
            }
        }
        
        # Create results directory
        os.makedirs(self.results_dir, exist_ok=True)
        
    def log_component_result(self, component: str, result: Dict[str, Any]):
        """Log results from a test component"""
        self.test_results["test_components"][component] = result
        
        # Update overall summary
        if "summary" in result:
            summary = result["summary"]
            if "total" in summary:
                self.test_results["overall_summary"]["total_tests"] += summary.get("total", 0)
            if "passed" in summary:
                self.test_results["overall_summary"]["passed_tests"] += summary.get("passed", 0)
            if "failed" in summary:
                self.test_results["overall_summary"]["failed_tests"] += summary.get("failed", 0)
        
        # Count security issues
        if "vulnerabilities" in result:
            self.test_results["overall_summary"]["security_issues"] += len(result["vulnerabilities"])
    
    async def run_comprehensive_functional_tests(self) -> bool:
        """Run the comprehensive functional test suite"""
        logger.info("🧪 Starting Comprehensive Functional Tests...")
        
        try:
            # Import and run the comprehensive test suite
            sys.path.append(os.getcwd())
            from comprehensive_auth_test_suite import AuthTestSuite
            
            test_suite = AuthTestSuite(self.base_url)
            results = await test_suite.run_all_tests()
            
            # Save component results
            component_file = os.path.join(self.results_dir, "functional_tests.json")
            with open(component_file, 'w') as f:
                json.dump(results, f, indent=2, default=str)
            
            self.log_component_result("functional_tests", results)
            
            success = results["summary"]["failed"] == 0
            logger.info(f"✅ Functional tests completed - Success: {success}")
            return success
            
        except Exception as e:
            logger.error(f"❌ Functional tests failed: {e}")
            self.log_component_result("functional_tests", {
                "error": str(e),
                "status": "FAILED",
                "summary": {"total": 1, "passed": 0, "failed": 1}
            })
            return False
    
    async def run_security_penetration_tests(self) -> bool:
        """Run the security penetration test suite"""
        logger.info("🔒 Starting Security Penetration Tests...")
        
        try:
            # Import and run the security test suite
            from auth_security_penetration_test import SecurityPenetrationTester
            
            security_tester = SecurityPenetrationTester(self.base_url)
            results = await security_tester.run_security_tests()
            
            # Save component results
            component_file = os.path.join(self.results_dir, "security_tests.json")
            with open(component_file, 'w') as f:
                json.dump(results, f, indent=2, default=str)
            
            self.log_component_result("security_tests", results)
            
            # Consider test successful if no critical/high vulnerabilities
            risk_level = results["summary"]["risk_level"]
            success = risk_level not in ["CRITICAL", "HIGH"]
            logger.info(f"🛡️ Security tests completed - Risk Level: {risk_level}")
            return success
            
        except Exception as e:
            logger.error(f"❌ Security tests failed: {e}")
            self.log_component_result("security_tests", {
                "error": str(e),
                "status": "FAILED",
                "summary": {"risk_level": "ERROR"}
            })
            return False
    
    def run_performance_tests(self) -> bool:
        """Run the load/performance test suite"""
        logger.info("⚡ Starting Performance Tests...")
        
        try:
            # Run the bash performance test script
            script_path = os.path.join(os.getcwd(), "auth_load_performance_test.sh")
            
            if not os.path.exists(script_path):
                logger.error(f"❌ Performance test script not found: {script_path}")
                return False
            
            # Make sure script is executable
            os.chmod(script_path, 0o755)
            
            # Run the performance tests
            result = subprocess.run(
                [script_path, self.base_url],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            # Find the performance results directory
            perf_results_dir = None
            for item in os.listdir('.'):
                if item.startswith('auth_performance_results_'):
                    perf_results_dir = item
                    break
            
            performance_results = {
                "return_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "performance_results_dir": perf_results_dir
            }
            
            # Try to parse performance results if available
            if perf_results_dir and os.path.exists(perf_results_dir):
                try:
                    # Copy performance results to our results directory
                    import shutil
                    perf_dest = os.path.join(self.results_dir, "performance_results")
                    shutil.copytree(perf_results_dir, perf_dest)
                    
                    # Parse test results if available
                    test_results_file = os.path.join(perf_dest, "test_results.jsonl")
                    if os.path.exists(test_results_file):
                        with open(test_results_file, 'r') as f:
                            perf_tests = [json.loads(line) for line in f]
                        
                        performance_results["tests"] = perf_tests
                        performance_results["summary"] = {
                            "total": len(perf_tests),
                            "passed": len([t for t in perf_tests if t.get("status") == "PASSED"]),
                            "failed": len([t for t in perf_tests if t.get("status") == "FAILED"])
                        }
                
                except Exception as parse_error:
                    logger.warning(f"⚠️ Failed to parse performance results: {parse_error}")
            
            # Save component results
            component_file = os.path.join(self.results_dir, "performance_tests.json")
            with open(component_file, 'w') as f:
                json.dump(performance_results, f, indent=2, default=str)
            
            self.log_component_result("performance_tests", performance_results)
            
            success = result.returncode == 0
            logger.info(f"📊 Performance tests completed - Success: {success}")
            return success
            
        except subprocess.TimeoutExpired:
            logger.error("❌ Performance tests timed out")
            return False
        except Exception as e:
            logger.error(f"❌ Performance tests failed: {e}")
            self.log_component_result("performance_tests", {
                "error": str(e),
                "status": "FAILED"
            })
            return False
    
    def run_browser_integration_tests(self) -> bool:
        """Run browser-based integration tests"""
        logger.info("🌐 Starting Browser Integration Tests...")
        
        try:
            # Create a simple browser test using requests to simulate browser behavior
            import requests
            
            browser_tests = []
            session = requests.Session()
            
            # Test 1: CORS with browser-like requests
            logger.info("  Testing CORS with browser-like requests...")
            
            # Preflight request
            preflight_response = session.options(
                f"{self.base_url}/api/v1/auth/login",
                headers={
                    'Origin': 'https://velro-frontend-production.up.railway.app',
                    'Access-Control-Request-Method': 'POST',
                    'Access-Control-Request-Headers': 'Content-Type,Authorization'
                },
                timeout=10
            )
            
            browser_tests.append({
                "test": "CORS Preflight",
                "status": "PASSED" if preflight_response.status_code in [200, 204] else "FAILED",
                "status_code": preflight_response.status_code,
                "cors_headers": dict(preflight_response.headers)
            })
            
            # Test 2: Actual request with CORS headers
            login_response = session.post(
                f"{self.base_url}/api/v1/auth/login",
                json={"email": "test@example.com", "password": "wrongpassword"},
                headers={
                    'Origin': 'https://velro-frontend-production.up.railway.app',
                    'Content-Type': 'application/json'
                },
                timeout=10
            )
            
            browser_tests.append({
                "test": "CORS Actual Request",
                "status": "PASSED" if login_response.status_code in [400, 401, 422] else "FAILED",
                "status_code": login_response.status_code,
                "has_cors_headers": 'Access-Control-Allow-Origin' in login_response.headers
            })
            
            # Test 3: Session persistence simulation
            logger.info("  Testing session persistence...")
            
            # Use emergency token for authenticated request
            emergency_token = "emergency_token_bd1a2f69-89eb-489f-9288-8aacf4924763"
            
            me_response1 = session.get(
                f"{self.base_url}/api/v1/auth/me",
                headers={'Authorization': f'Bearer {emergency_token}'},
                timeout=10
            )
            
            # Second request to test token persistence
            me_response2 = session.get(
                f"{self.base_url}/api/v1/auth/me",
                headers={'Authorization': f'Bearer {emergency_token}'},
                timeout=10
            )
            
            browser_tests.append({
                "test": "Token Persistence",
                "status": "PASSED" if me_response1.status_code == me_response2.status_code == 200 else "FAILED",
                "first_request": me_response1.status_code,
                "second_request": me_response2.status_code
            })
            
            browser_results = {
                "tests": browser_tests,
                "summary": {
                    "total": len(browser_tests),
                    "passed": len([t for t in browser_tests if t["status"] == "PASSED"]),
                    "failed": len([t for t in browser_tests if t["status"] == "FAILED"])
                }
            }
            
            # Save component results
            component_file = os.path.join(self.results_dir, "browser_tests.json")
            with open(component_file, 'w') as f:
                json.dump(browser_results, f, indent=2, default=str)
            
            self.log_component_result("browser_tests", browser_results)
            
            success = browser_results["summary"]["failed"] == 0
            logger.info(f"🌐 Browser tests completed - Success: {success}")
            return success
            
        except Exception as e:
            logger.error(f"❌ Browser tests failed: {e}")
            self.log_component_result("browser_tests", {
                "error": str(e),
                "status": "FAILED",
                "summary": {"total": 1, "passed": 0, "failed": 1}
            })
            return False
    
    def generate_comprehensive_report(self):
        """Generate a comprehensive test report"""
        logger.info("📊 Generating Comprehensive Test Report...")
        
        report_file = os.path.join(self.results_dir, "COMPREHENSIVE_AUTH_TEST_REPORT.md")
        
        # Calculate overall metrics
        overall = self.test_results["overall_summary"]
        total_tests = overall["total_tests"]
        success_rate = (overall["passed_tests"] / total_tests * 100) if total_tests > 0 else 0
        
        # Determine overall status
        if overall["failed_tests"] == 0 and overall["security_issues"] == 0:
            overall_status = "✅ PASS"
            status_color = "green"
        elif overall["security_issues"] > 0:
            overall_status = "🚨 SECURITY ISSUES FOUND"
            status_color = "red"
        else:
            overall_status = "❌ FAILURES DETECTED"
            status_color = "orange"
        
        with open(report_file, 'w') as f:
            f.write(f"""# 🛡️ Comprehensive Authentication Test Report

**Test Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Target System:** {self.base_url}
**Test Suite Version:** {self.test_results['test_suite_version']}
**Overall Status:** <span style="color: {status_color}">**{overall_status}**</span>

---

## 📋 Executive Summary

| Metric | Value |
|--------|-------|
| **Total Tests Executed** | {total_tests} |
| **Tests Passed** | {overall['passed_tests']} ✅ |
| **Tests Failed** | {overall['failed_tests']} ❌ |
| **Success Rate** | {success_rate:.1f}% |
| **Security Issues Found** | {overall['security_issues']} 🔒 |
| **Test Duration** | {self.timestamp} |

---

## 🧪 Test Components Results

""")
            
            # Component summaries
            for component, results in self.test_results["test_components"].items():
                component_name = component.replace('_', ' ').title()
                f.write(f"### {component_name}\n\n")
                
                if "error" in results:
                    f.write(f"❌ **Status:** FAILED\n")
                    f.write(f"**Error:** {results['error']}\n\n")
                elif "summary" in results:
                    summary = results["summary"]
                    if "total" in summary:
                        comp_success_rate = (summary.get("passed", 0) / summary["total"] * 100) if summary["total"] > 0 else 0
                        f.write(f"📊 **Tests:** {summary['total']} | **Passed:** {summary.get('passed', 0)} | **Failed:** {summary.get('failed', 0)} | **Success Rate:** {comp_success_rate:.1f}%\n\n")
                    elif "risk_level" in summary:
                        f.write(f"🛡️ **Risk Level:** {summary['risk_level']}\n\n")
                else:
                    f.write("ℹ️ Component executed successfully\n\n")
            
            f.write("""---

## 🔍 Detailed Findings

""")
            
            # Detailed findings for each component
            for component, results in self.test_results["test_components"].items():
                component_name = component.replace('_', ' ').title()
                f.write(f"### {component_name} Details\n\n")
                
                if component == "security_tests" and "vulnerabilities" in results:
                    if results["vulnerabilities"]:
                        f.write("🚨 **Security Vulnerabilities Found:**\n\n")
                        for vuln in results["vulnerabilities"]:
                            severity = vuln.get("severity", "UNKNOWN")
                            test_name = vuln.get("test_name", "Unknown Test")
                            f.write(f"- **{severity}:** {test_name}\n")
                    else:
                        f.write("✅ No security vulnerabilities detected\n\n")
                
                elif component == "functional_tests" and "tests" in results:
                    failed_tests = [t for t in results["tests"] if t.get("status") == "FAILED"]
                    if failed_tests:
                        f.write("❌ **Failed Functional Tests:**\n\n")
                        for test in failed_tests:
                            f.write(f"- {test.get('test_name', 'Unknown')}: {test.get('details', {}).get('error', 'No details')}\n")
                    else:
                        f.write("✅ All functional tests passed\n\n")
                
                elif component == "performance_tests" and "tests" in results:
                    perf_tests = results["tests"]
                    f.write(f"📊 **Performance Test Results:**\n\n")
                    for test in perf_tests:
                        status = test.get("status", "UNKNOWN")
                        details = test.get("details", "No details")
                        f.write(f"- {test.get('test', 'Unknown Test')}: {status} - {details}\n")
                
                f.write("\n")
            
            f.write(f"""---

## 📁 Generated Files

The following files have been generated as part of this test suite:

- `{report_file}` - This comprehensive report
- `functional_tests.json` - Detailed functional test results
- `security_tests.json` - Security penetration test results
- `performance_tests.json` - Load and performance test results
- `browser_tests.json` - Browser integration test results
- `performance_results/` - Detailed performance metrics and logs

---

## 🔧 Recommendations

""")
            
            # Generate recommendations based on results
            recommendations = []
            
            if overall["security_issues"] > 0:
                recommendations.append("🚨 **CRITICAL:** Address security vulnerabilities immediately before production deployment")
            
            if overall["failed_tests"] > 0:
                recommendations.append("⚠️ **HIGH:** Fix failing functional tests to ensure system reliability")
            
            if overall["security_issues"] == 0 and overall["failed_tests"] == 0:
                recommendations.append("✅ **GOOD:** Authentication system appears to be functioning correctly")
                recommendations.append("🔄 **MAINTENANCE:** Continue regular security testing and monitoring")
            
            recommendations.append("📊 **MONITORING:** Set up continuous monitoring for authentication performance")
            recommendations.append("🔒 **SECURITY:** Implement regular security audits and penetration testing")
            
            for rec in recommendations:
                f.write(f"{rec}\n\n")
            
            f.write(f"""---

## 📞 Support Information

- **Test Suite Version:** {self.test_results['test_suite_version']}
- **Generated:** {datetime.now().isoformat()}
- **Results Directory:** `{self.results_dir}`

For questions about this report or test results, please contact the QA team.

---

*Report generated by Emergency Auth Validation Swarm - Tester Agent*
""")
        
        logger.info(f"📊 Comprehensive report saved to: {report_file}")
        return report_file
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all authentication test components"""
        logger.info("🚀 Starting Comprehensive Authentication Test Suite")
        logger.info(f"   Target: {self.base_url}")
        logger.info(f"   Results: {self.results_dir}")
        logger.info("=" * 80)
        
        start_time = time.time()
        
        # Run all test components
        test_results = {}
        
        # 1. Functional Tests
        test_results["functional"] = await self.run_comprehensive_functional_tests()
        
        # 2. Security Tests
        test_results["security"] = await self.run_security_penetration_tests()
        
        # 3. Performance Tests
        test_results["performance"] = self.run_performance_tests()
        
        # 4. Browser Integration Tests
        test_results["browser"] = self.run_browser_integration_tests()
        
        total_duration = time.time() - start_time
        
        # Generate comprehensive report
        report_file = self.generate_comprehensive_report()
        
        # Final summary
        overall = self.test_results["overall_summary"]
        success_rate = (overall["passed_tests"] / overall["total_tests"] * 100) if overall["total_tests"] > 0 else 0
        
        logger.info("=" * 80)
        logger.info("🏁 Comprehensive Authentication Test Suite Complete")
        logger.info(f"   Total Tests: {overall['total_tests']}")
        logger.info(f"   Passed: {overall['passed_tests']} ✅")
        logger.info(f"   Failed: {overall['failed_tests']} ❌")
        logger.info(f"   Security Issues: {overall['security_issues']} 🔒")
        logger.info(f"   Success Rate: {success_rate:.1f}%")
        logger.info(f"   Total Duration: {total_duration:.2f}s")
        logger.info(f"   Report: {report_file}")
        
        # Save final results
        final_results_file = os.path.join(self.results_dir, "final_results.json")
        with open(final_results_file, 'w') as f:
            json.dump(self.test_results, f, indent=2, default=str)
        
        return self.test_results


async def main():
    """Main test orchestrator"""
    parser = argparse.ArgumentParser(description="Comprehensive Authentication Test Suite")
    parser.add_argument("--url", default="https://velro-backend.railway.app",
                      help="Base URL of the API to test")
    parser.add_argument("--components", nargs="+", 
                      choices=["functional", "security", "performance", "browser", "all"],
                      default=["all"],
                      help="Test components to run")
    
    args = parser.parse_args()
    
    # Initialize orchestrator
    orchestrator = AuthTestOrchestrator(base_url=args.url)
    
    try:
        # Run comprehensive tests
        results = await orchestrator.run_all_tests()
        
        # Determine exit code
        overall = results["overall_summary"]
        
        if overall["security_issues"] > 0:
            logger.error("🚨 CRITICAL: Security issues found!")
            sys.exit(2)  # Critical security issues
        elif overall["failed_tests"] > 0:
            logger.error("❌ Some tests failed")
            sys.exit(1)  # Test failures
        else:
            logger.info("✅ All tests passed successfully!")
            sys.exit(0)  # Success
            
    except KeyboardInterrupt:
        logger.info("Test suite interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Test suite failed with exception: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())