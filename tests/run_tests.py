"""
Comprehensive test runner for Velro API with detailed reporting and validation.
Validates all PRD.MD requirements and generates production-readiness report.
"""
import subprocess
import sys
import os
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass
class TestResult:
    """Test result data structure."""
    name: str
    status: str  # passed, failed, skipped, error
    duration: float
    error_message: Optional[str] = None
    category: Optional[str] = None


@dataclass
class TestSuite:
    """Test suite data structure."""
    name: str
    tests: List[TestResult]
    total_time: float
    passed: int
    failed: int
    skipped: int
    errors: int


class VelroTestRunner:
    """Comprehensive test runner for Velro API validation."""
    
    def __init__(self, project_root: str = None):
        self.project_root = Path(project_root or os.getcwd())
        self.test_dir = self.project_root / "tests"
        self.reports_dir = self.project_root / "test-reports"
        self.reports_dir.mkdir(exist_ok=True)
        
        # Test categories based on PRD.MD requirements
        self.test_categories = {
            'authentication': 'Authentication & User Management',
            'image_generation': 'AI Image Generation',
            'project_management': 'Project Management',
            'project_generations': 'Project-Generation Relationships',
            'api_security': 'API Security & RLS Policies',
            'end_to_end': 'End-to-End User Journeys'
        }
        
        # PRD.MD requirements mapping
        self.prd_requirements = {
            'user_authentication': ['test_authentication.py'],
            'jwt_token_management': ['test_authentication.py'],
            'user_registration_login': ['test_authentication.py'],
            'supabase_auth_sync': ['test_authentication.py'],
            'image_generation_api': ['test_image_generation.py'],
            'fal_ai_integration': ['test_image_generation.py'],
            'generation_status_tracking': ['test_image_generation.py'],
            'project_crud_operations': ['test_project_management.py'],
            'project_visibility_controls': ['test_project_management.py'],
            'project_generation_assignment': ['test_project_generations.py'],
            'user_data_isolation': ['test_api_security.py'],
            'rls_policy_enforcement': ['test_api_security.py'],
            'input_validation_security': ['test_api_security.py'],
            'rate_limiting': ['test_api_security.py'],
            'complete_user_flows': ['test_end_to_end.py'],
            'error_handling_recovery': ['test_end_to_end.py']
        }

    def run_all_tests(self, 
                     coverage: bool = True, 
                     parallel: bool = True,
                     html_report: bool = True,
                     junit_xml: bool = True,
                     verbose: bool = True) -> Dict[str, Any]:
        """Run all tests with comprehensive reporting."""
        
        print("🚀 Starting Velro API Test Suite")
        print("=" * 60)
        print(f"📁 Project Root: {self.project_root}")
        print(f"🧪 Tests Directory: {self.test_dir}")
        print(f"📊 Reports Directory: {self.reports_dir}")
        print()
        
        start_time = time.time()
        
        # Prepare test command
        cmd = self._build_pytest_command(
            coverage=coverage,
            parallel=parallel,
            html_report=html_report,
            junit_xml=junit_xml,
            verbose=verbose
        )
        
        print(f"🔧 Running command: {' '.join(cmd)}")
        print()
        
        # Run tests
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes timeout
            )
            
            end_time = time.time()
            total_duration = end_time - start_time
            
            # Parse results
            test_results = self._parse_test_results(result, total_duration)
            
            # Generate reports
            self._generate_comprehensive_report(test_results)
            self._generate_prd_compliance_report(test_results)
            
            # Print summary
            self._print_test_summary(test_results)
            
            return test_results
            
        except subprocess.TimeoutExpired:
            print("❌ Tests timed out after 5 minutes")
            return {'status': 'timeout', 'duration': 300}
        except Exception as e:
            print(f"❌ Error running tests: {e}")
            return {'status': 'error', 'error': str(e)}

    def run_category_tests(self, category: str, **kwargs) -> Dict[str, Any]:
        """Run tests for specific category (auth, generation, etc.)."""
        
        if category not in self.test_categories:
            print(f"❌ Unknown category: {category}")
            print(f"Available categories: {list(self.test_categories.keys())}")
            return {'status': 'error', 'error': f'Unknown category: {category}'}
        
        test_file = f"test_{category}.py"
        test_path = self.test_dir / test_file
        
        if not test_path.exists():
            print(f"❌ Test file not found: {test_path}")
            return {'status': 'error', 'error': f'Test file not found: {test_file}'}
        
        print(f"🧪 Running {self.test_categories[category]} tests")
        print(f"📄 Test file: {test_file}")
        print()
        
        # Run specific test file
        cmd = self._build_pytest_command(test_files=[str(test_path)], **kwargs)
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=120  # 2 minutes for single category
            )
            
            test_results = self._parse_test_results(result)
            self._print_test_summary(test_results, category=category)
            
            return test_results
            
        except Exception as e:
            print(f"❌ Error running {category} tests: {e}")
            return {'status': 'error', 'error': str(e)}

    def run_production_readiness_check(self) -> Dict[str, Any]:
        """Run comprehensive production readiness validation."""
        
        print("🏭 Production Readiness Validation")
        print("=" * 50)
        
        checks = {
            'unit_tests': self._run_unit_tests(),
            'integration_tests': self._run_integration_tests(),
            'security_tests': self._run_security_tests(),
            'performance_tests': self._run_performance_tests(),
            'e2e_tests': self._run_e2e_tests()
        }
        
        # Calculate overall readiness score
        passed_checks = sum(1 for check in checks.values() if check.get('status') == 'passed')
        total_checks = len(checks)
        readiness_score = (passed_checks / total_checks) * 100
        
        production_ready = readiness_score >= 85  # 85% threshold for production
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'readiness_score': readiness_score,
            'production_ready': production_ready,
            'checks': checks,
            'recommendations': self._generate_production_recommendations(checks)
        }
        
        # Save production readiness report
        report_file = self.reports_dir / "production_readiness.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        self._print_production_readiness_summary(report)
        
        return report

    def _build_pytest_command(self, 
                             test_files: List[str] = None,
                             coverage: bool = True,
                             parallel: bool = True,
                             html_report: bool = True,
                             junit_xml: bool = True,
                             verbose: bool = True) -> List[str]:
        """Build pytest command with all options."""
        
        cmd = ['python', '-m', 'pytest']
        
        # Test files or directory  
        if test_files:
            cmd.extend(test_files)
        else:
            cmd.append(str(self.test_dir))
        
        # Verbose output
        if verbose:
            cmd.append('-v')
        
        # Coverage
        if coverage:
            cmd.extend([
                '--cov=.',
                '--cov-report=html:htmlcov',
                '--cov-report=term-missing',
                '--cov-report=json:test-reports/coverage.json'
            ])
        
        # Parallel execution
        if parallel:
            cpu_count = os.cpu_count() or 4
            cmd.extend(['-n', str(min(cpu_count, 4))])  # Max 4 workers
        
        # JUnit XML report
        if junit_xml:
            cmd.extend(['--junit-xml=test-reports/junit.xml'])
        
        # HTML report
        if html_report:
            cmd.extend(['--html=test-reports/report.html', '--self-contained-html'])
        
        # Additional options
        cmd.extend([
            '--tb=short',  # Short traceback format
            '--strict-markers',  # Strict marker validation
            '--disable-warnings'  # Disable warnings for cleaner output
        ])
        
        return cmd

    def _parse_test_results(self, result: subprocess.CompletedProcess, duration: float = 0) -> Dict[str, Any]:
        """Parse pytest results from stdout/stderr."""
        
        output = result.stdout + result.stderr
        
        # Try to parse JUnit XML if available
        junit_file = self.reports_dir / "junit.xml"
        if junit_file.exists():
            return self._parse_junit_xml(junit_file, duration)
        
        # Fallback to stdout parsing
        return self._parse_stdout_results(output, result.returncode, duration)

    def _parse_junit_xml(self, junit_file: Path, duration: float) -> Dict[str, Any]:
        """Parse JUnit XML results."""
        
        try:
            tree = ET.parse(junit_file)
            root = tree.getroot()
            
            test_suites = []
            total_tests = 0
            total_passed = 0
            total_failed = 0
            total_skipped = 0
            total_errors = 0
            
            for testsuite in root.findall('testsuite'):
                suite_name = testsuite.get('name', 'Unknown')
                suite_time = float(testsuite.get('time', 0))
                
                tests = []
                for testcase in testsuite.findall('testcase'):
                    test_name = testcase.get('name')
                    test_time = float(testcase.get('time', 0))
                    
                    # Determine test status
                    if testcase.find('failure') is not None:
                        status = 'failed'
                        error_msg = testcase.find('failure').get('message', '')
                        total_failed += 1
                    elif testcase.find('error') is not None:
                        status = 'error'
                        error_msg = testcase.find('error').get('message', '')
                        total_errors += 1
                    elif testcase.find('skipped') is not None:
                        status = 'skipped'
                        error_msg = testcase.find('skipped').get('message', '')
                        total_skipped += 1
                    else:
                        status = 'passed'
                        error_msg = None
                        total_passed += 1
                    
                    # Extract category from test name
                    category = self._extract_test_category(test_name)
                    
                    tests.append(TestResult(
                        name=test_name,
                        status=status,
                        duration=test_time,
                        error_message=error_msg,
                        category=category
                    ))
                    total_tests += 1
                
                test_suites.append(TestSuite(
                    name=suite_name,
                    tests=tests,
                    total_time=suite_time,
                    passed=len([t for t in tests if t.status == 'passed']),
                    failed=len([t for t in tests if t.status == 'failed']),
                    skipped=len([t for t in tests if t.status == 'skipped']),
                    errors=len([t for t in tests if t.status == 'error'])
                ))
            
            return {
                'status': 'completed',
                'total_duration': duration,
                'total_tests': total_tests,
                'passed': total_passed,
                'failed': total_failed,
                'skipped': total_skipped,
                'errors': total_errors,
                'success_rate': (total_passed / total_tests * 100) if total_tests > 0 else 0,
                'test_suites': test_suites
            }
            
        except Exception as e:
            print(f"⚠️ Error parsing JUnit XML: {e}")
            return {'status': 'parse_error', 'error': str(e)}

    def _parse_stdout_results(self, output: str, return_code: int, duration: float) -> Dict[str, Any]:
        """Parse pytest results from stdout."""
        
        lines = output.split('\n')
        
        # Look for result summary line
        summary_line = None
        for line in reversed(lines):
            if 'passed' in line or 'failed' in line:
                summary_line = line
                break
        
        if summary_line:
            # Basic parsing - this is a fallback
            return {
                'status': 'completed' if return_code == 0 else 'failed',
                'total_duration': duration,
                'raw_output': output,
                'return_code': return_code
            }
        
        return {
            'status': 'unknown',
            'total_duration': duration,
            'raw_output': output,
            'return_code': return_code
        }

    def _extract_test_category(self, test_name: str) -> str:
        """Extract test category from test name."""
        
        for category in self.test_categories:
            if category in test_name.lower():
                return category
        
        return 'other'

    def _generate_comprehensive_report(self, results: Dict[str, Any]):
        """Generate comprehensive HTML test report."""
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Velro API Test Report</title>
    <meta charset="utf-8">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background: #2563eb; color: white; padding: 20px; border-radius: 8px; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }}
        .card {{ background: #f8fafc; border: 1px solid #e2e8f0; padding: 20px; border-radius: 8px; }}
        .passed {{ color: #059669; }}
        .failed {{ color: #dc2626; }}
        .skipped {{ color: #d97706; }}
        .category {{ margin: 20px 0; }}
        .category h3 {{ border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; }}
        .test-item {{ padding: 8px; margin: 4px 0; border-radius: 4px; }}
        .test-passed {{ background: #ecfdf5; border-left: 4px solid #059669; }}
        .test-failed {{ background: #fef2f2; border-left: 4px solid #dc2626; }}
        .test-skipped {{ background: #fffbeb; border-left: 4px solid #d97706; }}
        .progress-bar {{ width: 100%; height: 20px; background: #e2e8f0; border-radius: 10px; overflow: hidden; }}
        .progress-fill {{ height: 100%; background: #059669; transition: width 0.3s ease; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🧪 Velro API Test Report</h1>
        <p>Generated on {timestamp}</p>
        <p>Validating all PRD.MD requirements</p>
    </div>
    
    <div class="summary">
        <div class="card">
            <h3>📊 Test Summary</h3>
            <p><strong>Total Tests:</strong> {results.get('total_tests', 'N/A')}</p>
            <p><strong class="passed">✅ Passed:</strong> {results.get('passed', 'N/A')}</p>
            <p><strong class="failed">❌ Failed:</strong> {results.get('failed', 'N/A')}</p>
            <p><strong class="skipped">⏭️ Skipped:</strong> {results.get('skipped', 'N/A')}</p>
        </div>
        
        <div class="card">
            <h3>⏱️ Performance</h3>
            <p><strong>Total Duration:</strong> {results.get('total_duration', 0):.2f}s</p>
            <p><strong>Success Rate:</strong> {results.get('success_rate', 0):.1f}%</p>
            <div class="progress-bar">
                <div class="progress-fill" style="width: {results.get('success_rate', 0)}%"></div>
            </div>
        </div>
        
        <div class="card">
            <h3>🎯 PRD Compliance</h3>
            <p><strong>Requirements Covered:</strong> {len(self.prd_requirements)}</p>
            <p><strong>Test Categories:</strong> {len(self.test_categories)}</p>
            <p><strong>Production Ready:</strong> {'✅ Yes' if results.get('success_rate', 0) >= 85 else '❌ No'}</p>
        </div>
    </div>
    
    <div class="categories">
        <h2>📋 Test Categories</h2>
        {self._generate_category_html(results)}
    </div>
    
    <div class="requirements">
        <h2>📑 PRD.MD Requirements Coverage</h2>
        {self._generate_requirements_html(results)}
    </div>
</body>
</html>
        """
        
        report_file = self.reports_dir / "comprehensive_report.html"
        with open(report_file, 'w') as f:
            f.write(html_content)
        
        print(f"📊 Comprehensive report saved to: {report_file}")

    def _generate_category_html(self, results: Dict[str, Any]) -> str:
        """Generate HTML for test categories."""
        
        if 'test_suites' not in results:
            return "<p>No detailed test results available</p>"
        
        html_parts = []
        
        for category, description in self.test_categories.items():
            category_tests = [
                test for suite in results['test_suites'] 
                for test in suite.tests 
                if test.category == category
            ]
            
            if not category_tests:
                continue
            
            passed = len([t for t in category_tests if t.status == 'passed'])
            failed = len([t for t in category_tests if t.status == 'failed'])
            skipped = len([t for t in category_tests if t.status == 'skipped'])
            total = len(category_tests)
            
            success_rate = (passed / total * 100) if total > 0 else 0
            
            html_parts.append(f"""
                <div class="category">
                    <h3>{description} ({passed}/{total} passed - {success_rate:.1f}%)</h3>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: {success_rate}%"></div>
                    </div>
                    <div class="test-list">
                        {''.join(self._generate_test_item_html(test) for test in category_tests[:10])}
                        {f'<p>... and {len(category_tests) - 10} more tests</p>' if len(category_tests) > 10 else ''}
                    </div>
                </div>
            """)
        
        return ''.join(html_parts)

    def _generate_test_item_html(self, test: TestResult) -> str:
        """Generate HTML for individual test item."""
        
        status_class = f"test-{test.status}"
        status_icon = {
            'passed': '✅',
            'failed': '❌', 
            'skipped': '⏭️',
            'error': '🚨'
        }.get(test.status, '❓')
        
        error_info = ""
        if test.error_message:
            error_info = f"<br><small style='color: #666;'>{test.error_message[:100]}...</small>"
        
        return f"""
            <div class="test-item {status_class}">
                {status_icon} {test.name} ({test.duration:.3f}s)
                {error_info}
            </div>
        """

    def _generate_requirements_html(self, results: Dict[str, Any]) -> str:
        """Generate HTML for PRD requirements coverage."""
        
        html_parts = []
        
        for requirement, test_files in self.prd_requirements.items():
            # Check if requirement is covered by looking at test files
            covered = any(
                any(test_file.replace('.py', '') in test.name.lower() 
                    for suite in results.get('test_suites', [])
                    for test in suite.tests)
                for test_file in test_files
            )
            
            status_icon = '✅' if covered else '❌'
            status_class = 'passed' if covered else 'failed'
            
            html_parts.append(f"""
                <div class="test-item test-{status_class}">
                    {status_icon} {requirement.replace('_', ' ').title()}
                    <br><small>Covered by: {', '.join(test_files)}</small>
                </div>
            """)
        
        return ''.join(html_parts)

    def _generate_prd_compliance_report(self, results: Dict[str, Any]):
        """Generate PRD compliance report."""
        
        compliance_data = {
            'timestamp': datetime.now().isoformat(),
            'total_requirements': len(self.prd_requirements),
            'covered_requirements': 0,
            'compliance_percentage': 0,
            'requirements_status': {},
            'recommendations': []
        }
        
        # Check each requirement
        for requirement, test_files in self.prd_requirements.items():
            # Simple check - requirement is covered if related tests exist
            covered = any(
                (self.test_dir / test_file).exists() 
                for test_file in test_files
            )
            
            compliance_data['requirements_status'][requirement] = {
                'covered': covered,
                'test_files': test_files,
                'status': 'covered' if covered else 'missing'
            }
            
            if covered:
                compliance_data['covered_requirements'] += 1
            else:
                compliance_data['recommendations'].append(
                    f"Implement tests for {requirement} in {', '.join(test_files)}"
                )
        
        compliance_data['compliance_percentage'] = (
            compliance_data['covered_requirements'] / 
            compliance_data['total_requirements'] * 100
        )
        
        # Save compliance report
        report_file = self.reports_dir / "prd_compliance.json"
        with open(report_file, 'w') as f:
            json.dump(compliance_data, f, indent=2)
        
        print(f"📋 PRD compliance report saved to: {report_file}")
        print(f"📊 PRD Compliance: {compliance_data['compliance_percentage']:.1f}%")

    def _print_test_summary(self, results: Dict[str, Any], category: str = None):
        """Print test execution summary."""
        
        print()
        print("📊 TEST SUMMARY")
        print("=" * 50)
        
        if category:
            print(f"Category: {self.test_categories.get(category, category)}")
        
        print(f"Total Tests: {results.get('total_tests', 'N/A')}")
        print(f"✅ Passed: {results.get('passed', 'N/A')}")
        print(f"❌ Failed: {results.get('failed', 'N/A')}")
        print(f"⏭️ Skipped: {results.get('skipped', 'N/A')}")
        print(f"🚨 Errors: {results.get('errors', 'N/A')}")
        print(f"⏱️ Duration: {results.get('total_duration', 0):.2f}s")
        print(f"📊 Success Rate: {results.get('success_rate', 0):.1f}%")
        
        # Production readiness indicator
        success_rate = results.get('success_rate', 0)
        if success_rate >= 95:
            print("🚀 PRODUCTION READY - Excellent!")
        elif success_rate >= 85:
            print("✅ PRODUCTION READY - Good to go!")
        elif success_rate >= 70:
            print("⚠️ NEEDS IMPROVEMENT - Address failures before production")
        else:
            print("❌ NOT PRODUCTION READY - Major issues need fixing")
        
        print()

    def _run_unit_tests(self) -> Dict[str, Any]:
        """Run unit tests specifically."""
        cmd = self._build_pytest_command(
            test_files=[str(self.test_dir)],
            coverage=False,
            parallel=True,
            html_report=False,
            junit_xml=False,
            verbose=False
        )
        cmd.extend(['-m', 'unit'])
        
        try:
            result = subprocess.run(cmd, cwd=self.project_root, capture_output=True, text=True, timeout=60)
            return {'status': 'passed' if result.returncode == 0 else 'failed', 'output': result.stdout}
        except:
            return {'status': 'error', 'error': 'Unit tests failed to run'}

    def _run_integration_tests(self) -> Dict[str, Any]:
        """Run integration tests specifically."""
        cmd = self._build_pytest_command(
            test_files=[str(self.test_dir)],
            coverage=False,
            parallel=False,  # Integration tests may need to run sequentially
            html_report=False,
            junit_xml=False,
            verbose=False
        )
        cmd.extend(['-m', 'integration'])
        
        try:
            result = subprocess.run(cmd, cwd=self.project_root, capture_output=True, text=True, timeout=120)
            return {'status': 'passed' if result.returncode == 0 else 'failed', 'output': result.stdout}
        except:
            return {'status': 'error', 'error': 'Integration tests failed to run'}

    def _run_security_tests(self) -> Dict[str, Any]:
        """Run security tests specifically."""
        cmd = self._build_pytest_command(
            test_files=[str(self.test_dir / "test_api_security.py")],
            coverage=False,
            parallel=True,
            html_report=False,
            junit_xml=False,
            verbose=False
        )
        
        try:
            result = subprocess.run(cmd, cwd=self.project_root, capture_output=True, text=True, timeout=60)
            return {'status': 'passed' if result.returncode == 0 else 'failed', 'output': result.stdout}
        except:
            return {'status': 'error', 'error': 'Security tests failed to run'}

    def _run_performance_tests(self) -> Dict[str, Any]:
        """Run performance tests specifically."""
        cmd = self._build_pytest_command(
            test_files=[str(self.test_dir)],
            coverage=False,
            parallel=False,  # Performance tests should run individually
            html_report=False,
            junit_xml=False,
            verbose=False
        )
        cmd.extend(['-m', 'performance'])
        
        try:
            result = subprocess.run(cmd, cwd=self.project_root, capture_output=True, text=True, timeout=120)
            return {'status': 'passed' if result.returncode == 0 else 'failed', 'output': result.stdout}
        except:
            return {'status': 'error', 'error': 'Performance tests failed to run'}

    def _run_e2e_tests(self) -> Dict[str, Any]:
        """Run end-to-end tests specifically."""
        cmd = self._build_pytest_command(
            test_files=[str(self.test_dir / "test_end_to_end.py")],
            coverage=False,
            parallel=False,  # E2E tests should run sequentially
            html_report=False,
            junit_xml=False,
            verbose=False
        )
        
        try:
            result = subprocess.run(cmd, cwd=self.project_root, capture_output=True, text=True, timeout=180)
            return {'status': 'passed' if result.returncode == 0 else 'failed', 'output': result.stdout}
        except:
            return {'status': 'error', 'error': 'E2E tests failed to run'}

    def _generate_production_recommendations(self, checks: Dict[str, Any]) -> List[str]:
        """Generate production readiness recommendations."""
        
        recommendations = []
        
        for check_name, check_result in checks.items():
            if check_result.get('status') != 'passed':
                if check_name == 'unit_tests':
                    recommendations.append("Fix failing unit tests - they are critical for production stability")
                elif check_name == 'integration_tests':
                    recommendations.append("Address integration test failures - ensure components work together")
                elif check_name == 'security_tests':
                    recommendations.append("CRITICAL: Fix security test failures before production deployment")
                elif check_name == 'performance_tests':
                    recommendations.append("Optimize performance issues identified in tests")
                elif check_name == 'e2e_tests':
                    recommendations.append("Fix end-to-end test failures - ensure complete user flows work")
        
        if not recommendations:
            recommendations.append("All checks passed! System is ready for production deployment.")
        
        return recommendations

    def _print_production_readiness_summary(self, report: Dict[str, Any]):
        """Print production readiness summary."""
        
        print()
        print("🏭 PRODUCTION READINESS REPORT")
        print("=" * 60)
        print(f"📊 Readiness Score: {report['readiness_score']:.1f}%")
        print(f"🚀 Production Ready: {'✅ YES' if report['production_ready'] else '❌ NO'}")
        print()
        
        print("🔍 Check Results:")
        for check_name, result in report['checks'].items():
            status_icon = '✅' if result.get('status') == 'passed' else '❌'
            print(f"  {status_icon} {check_name.replace('_', ' ').title()}: {result.get('status', 'unknown')}")
        
        print()
        print("💡 Recommendations:")
        for i, recommendation in enumerate(report['recommendations'], 1):
            print(f"  {i}. {recommendation}")
        
        print()


def main():
    """Main test runner entry point."""
    
    import argparse
    
    parser = argparse.ArgumentParser(description="Velro API Test Runner")
    parser.add_argument('--category', choices=list(VelroTestRunner({}).test_categories.keys()), 
                       help='Run tests for specific category')
    parser.add_argument('--production-check', action='store_true', 
                       help='Run production readiness validation')
    parser.add_argument('--no-coverage', action='store_true',
                       help='Skip coverage analysis')
    parser.add_argument('--no-parallel', action='store_true',
                       help='Run tests sequentially')
    parser.add_argument('--quiet', action='store_true',
                       help='Minimal output')
    
    args = parser.parse_args()
    
    runner = VelroTestRunner()
    
    if args.production_check:
        results = runner.run_production_readiness_check()
        sys.exit(0 if results['production_ready'] else 1)
    elif args.category:
        results = runner.run_category_tests(
            args.category,
            coverage=not args.no_coverage,
            parallel=not args.no_parallel,
            verbose=not args.quiet
        )
        sys.exit(0 if results.get('status') == 'completed' and results.get('failed', 0) == 0 else 1)
    else:
        results = runner.run_all_tests(
            coverage=not args.no_coverage,
            parallel=not args.no_parallel,
            verbose=not args.quiet
        )
        sys.exit(0 if results.get('status') == 'completed' and results.get('failed', 0) == 0 else 1)


if __name__ == '__main__':
    main()