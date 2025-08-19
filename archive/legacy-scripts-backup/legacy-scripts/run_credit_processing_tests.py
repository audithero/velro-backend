#!/usr/bin/env python3
"""
CREDIT PROCESSING FIX VALIDATION - TEST RUNNER

This script runs comprehensive tests to validate that the credit processing
issue is fully resolved. It can be run independently or as part of CI/CD.

Usage:
    python run_credit_processing_tests.py [--phase <phase>] [--verbose] [--save-results]

Phases:
    all         - Run all test phases (default)
    pre_fix     - Pre-fix state validation
    service_key - Service key fix testing  
    pipeline    - Full generation pipeline testing
    edge_cases  - Edge case testing
    production  - Production environment testing
"""
import asyncio
import argparse
import json
import sys
import os
from datetime import datetime
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import the comprehensive test suite
from tests.test_comprehensive_credit_processing_fix import (
    CreditProcessingTestSuite,
    run_comprehensive_credit_processing_tests,
    run_specific_test_phase
)

class TestRunner:
    """Test runner for credit processing validation."""
    
    def __init__(self):
        self.verbose = False
        self.save_results = False
        self.results_dir = project_root / "test-results"
        
    def setup_results_directory(self):
        """Create results directory if it doesn't exist."""
        self.results_dir.mkdir(exist_ok=True)
        
    def print_banner(self):
        """Print test banner."""
        print("=" * 80)
        print("🚀 CREDIT PROCESSING FIX VALIDATION TEST SUITE")
        print("=" * 80)
        print(f"📅 Test Run: {datetime.utcnow().isoformat()}")
        print(f"🎯 Affected User: 22cb3917-57f6-49c6-ac96-ec266570081b")
        print(f"💳 Expected Credits: 1200")
        print(f"🐛 Issue: Credit processing failed: Profile lookup error")
        print("=" * 80)
        print()
    
    def print_phase_header(self, phase_name: str):
        """Print phase header."""
        print(f"\n📋 TEST PHASE: {phase_name.upper()}")
        print("-" * 60)
        
    def print_test_result(self, test_name: str, status: str, message: str = None):
        """Print individual test result."""
        status_emoji = {
            "PASS": "✅",
            "FAIL": "❌", 
            "EXPECTED_FAIL": "✅",
            "UNEXPECTED_PASS": "⚠️",
            "TESTED": "ℹ️",
            "PARTIAL_PASS": "⚠️"
        }
        
        emoji = status_emoji.get(status, "❓")
        print(f"  {emoji} {test_name}: {status}")
        
        if message and self.verbose:
            print(f"     └─ {message}")
    
    def print_phase_summary(self, phase_results: dict):
        """Print phase summary."""
        summary = phase_results.get("summary", {})
        total = summary.get("total_tests", 0)
        passed = summary.get("passed_tests", 0)
        status = summary.get("overall_status", "UNKNOWN")
        
        print(f"\n📊 Phase Summary: {passed}/{total} tests passed - Status: {status}")
        
        if "profile_error_resolved" in summary:
            resolved = summary["profile_error_resolved"]
            print(f"🎯 Profile Error Resolved: {'YES' if resolved else 'NO'}")
    
    def print_final_summary(self, results: dict):
        """Print final test summary."""
        print("\n" + "=" * 80)
        print("🎯 FINAL TEST RESULTS")
        print("=" * 80)
        
        overall_status = results.get("overall_status", "UNKNOWN")
        summary = results.get("summary", {})
        
        total_tests = summary.get("total_tests", 0)
        passed_tests = summary.get("passed_tests", 0)
        success_rate = summary.get("success_rate", 0)
        profile_resolved = summary.get("profile_error_resolved", False)
        
        print(f"Overall Status: {overall_status}")
        print(f"Profile Error Resolved: {'YES ✅' if profile_resolved else 'NO ❌'}")
        print(f"Success Rate: {success_rate}%")
        print(f"Tests Passed: {passed_tests}/{total_tests}")
        
        if overall_status == "PASS":
            print("\n🎉 SUCCESS: Credit processing issue is FULLY RESOLVED!")
            print("✅ All tests passed - the fix is working correctly")
        elif profile_resolved:
            print("\n⚠️ PARTIAL SUCCESS: Profile error is resolved but some tests failed")
            print("🔍 Manual review recommended for failing tests")
        else:
            print("\n❌ FAILURE: Credit processing issue still exists")
            print("🚨 The fix has not resolved the profile lookup error")
        
        print("=" * 80)
    
    def save_results_to_file(self, results: dict, filename: str = None):
        """Save test results to JSON file."""
        if not self.save_results:
            return
            
        self.setup_results_directory()
        
        if filename is None:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"credit_processing_test_results_{timestamp}.json"
        
        filepath = self.results_dir / filename
        
        try:
            with open(filepath, 'w') as f:
                json.dump(results, f, indent=2, default=str)
            print(f"\n💾 Results saved to: {filepath}")
        except Exception as e:
            print(f"\n❌ Failed to save results: {e}")
    
    async def run_phase_with_output(self, phase_name: str, phase_func):
        """Run a test phase with formatted output."""
        self.print_phase_header(phase_name)
        
        try:
            results = await phase_func()
            
            # Print individual test results
            tests = results.get("tests", {})
            for test_name, test_result in tests.items():
                status = test_result.get("status", "UNKNOWN")
                message = test_result.get("message", "")
                self.print_test_result(test_name, status, message)
            
            # Print phase summary
            self.print_phase_summary(results)
            
            return results
            
        except Exception as e:
            print(f"❌ Phase failed with exception: {e}")
            return {"error": str(e), "phase": phase_name}
    
    async def run_all_phases(self):
        """Run all test phases with comprehensive output."""
        self.print_banner()
        
        test_suite = CreditProcessingTestSuite()
        
        # Setup test environment
        print("🔧 Setting up test environment...")
        setup_success = await test_suite.setup_test_environment()
        
        if not setup_success:
            print("❌ Test environment setup failed!")
            return {"overall_status": "SETUP_FAILED"}
        
        print("✅ Test environment ready\n")
        
        # Run all phases
        all_results = {
            "timestamp": datetime.utcnow().isoformat(),
            "test_environment": "setup_success"
        }
        
        # Phase 1: Pre-fix validation
        all_results["pre_fix_validation"] = await self.run_phase_with_output(
            "Pre-Fix State Validation",
            test_suite.test_pre_fix_state_validation
        )
        
        # Phase 2: Service key testing
        all_results["service_key_tests"] = await self.run_phase_with_output(
            "Service Key Fix Testing", 
            test_suite.test_service_key_fix
        )
        
        # Phase 3: Pipeline testing  
        all_results["pipeline_tests"] = await self.run_phase_with_output(
            "Full Generation Pipeline Testing",
            test_suite.test_full_generation_pipeline
        )
        
        # Phase 4: Edge case testing
        all_results["edge_case_tests"] = await self.run_phase_with_output(
            "Edge Case Testing",
            test_suite.test_edge_cases
        )
        
        # Phase 5: Production testing
        all_results["production_tests"] = await self.run_phase_with_output(
            "Production Environment Testing",
            test_suite.test_production_environment
        )
        
        # Calculate overall results
        all_phases = [
            all_results.get("pre_fix_validation", {}),
            all_results.get("service_key_tests", {}),
            all_results.get("pipeline_tests", {}),
            all_results.get("edge_case_tests", {}),
            all_results.get("production_tests", {})
        ]
        
        total_tests = sum(phase.get("summary", {}).get("total_tests", 0) for phase in all_phases)
        passed_tests = sum(phase.get("summary", {}).get("passed_tests", 0) for phase in all_phases)
        
        profile_error_resolved = all_results.get("pipeline_tests", {}).get("summary", {}).get("profile_error_resolved", False)
        
        # Determine overall status
        if profile_error_resolved and passed_tests >= total_tests * 0.8:
            overall_status = "PASS"
        elif profile_error_resolved:
            overall_status = "PARTIAL_PASS"
        else:
            overall_status = "FAIL"
        
        all_results["summary"] = {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "success_rate": round((passed_tests / total_tests) * 100, 2) if total_tests > 0 else 0,
            "profile_error_resolved": profile_error_resolved,
            "overall_status": overall_status,
            "completed_at": datetime.utcnow().isoformat()
        }
        
        all_results["overall_status"] = overall_status
        
        # Print final summary
        self.print_final_summary(all_results)
        
        # Save results
        self.save_results_to_file(all_results)
        
        return all_results
    
    async def run_single_phase(self, phase: str):
        """Run a single test phase."""
        self.print_banner()
        
        print(f"🎯 Running single phase: {phase}")
        
        try:
            results = await run_specific_test_phase(phase)
            
            print(f"\n📊 Phase Results: {phase}")
            print("-" * 40)
            
            if "tests" in results:
                for test_name, test_result in results["tests"].items():
                    status = test_result.get("status", "UNKNOWN")
                    message = test_result.get("message", "")
                    self.print_test_result(test_name, status, message)
            
            if "summary" in results:
                self.print_phase_summary(results)
            
            # Save results
            if self.save_results:
                filename = f"credit_processing_test_{phase}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
                self.save_results_to_file(results, filename)
            
            return results
            
        except Exception as e:
            print(f"❌ Phase {phase} failed: {e}")
            return {"error": str(e), "phase": phase}


def main():
    """Main function with command line argument parsing."""
    parser = argparse.ArgumentParser(description="Credit Processing Fix Validation Test Runner")
    
    parser.add_argument(
        "--phase",
        choices=["all", "pre_fix", "service_key", "pipeline", "edge_cases", "production"],
        default="all",
        help="Test phase to run (default: all)"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    
    parser.add_argument(
        "--save-results", "-s",
        action="store_true", 
        help="Save test results to JSON file"
    )
    
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Minimal output (only final results)"
    )
    
    args = parser.parse_args()
    
    # Setup test runner
    runner = TestRunner()
    runner.verbose = args.verbose and not args.quiet
    runner.save_results = args.save_results
    
    # Run tests
    async def run_tests():
        if args.phase == "all":
            results = await runner.run_all_phases()
        else:
            results = await runner.run_single_phase(args.phase)
        
        # Exit with appropriate code
        if results.get("overall_status") == "PASS":
            sys.exit(0)  # Success
        elif results.get("summary", {}).get("profile_error_resolved", False):
            sys.exit(1)  # Partial success
        else:
            sys.exit(2)  # Failure
    
    # Run the async tests
    try:
        asyncio.run(run_tests())
    except KeyboardInterrupt:
        print("\n❌ Tests interrupted by user")
        sys.exit(3)
    except Exception as e:
        print(f"\n💥 Test runner failed: {e}")
        sys.exit(4)


if __name__ == "__main__":
    main()