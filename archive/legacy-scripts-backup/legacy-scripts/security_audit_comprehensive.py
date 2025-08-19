#!/usr/bin/env python3
"""
Comprehensive Security Audit Script
Phase 1 Step 3 - Critical security validation and OWASP compliance check
"""
import json
import time
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class SecurityAuditResult:
    """Security audit result data structure."""
    category: str
    check_name: str
    status: str  # PASS, FAIL, WARNING, INFO
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW, INFO
    description: str
    recommendation: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

class SecurityAuditor:
    """Comprehensive security auditor for Phase 1 Step 3 implementation."""
    
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.results: List[SecurityAuditResult] = []
        self.backend_path = self.project_root / "velro-backend"
        
    def add_result(self, result: SecurityAuditResult):
        """Add audit result."""
        self.results.append(result)
        
        # Color coding for console output
        colors = {
            "PASS": "\033[92m✅",      # Green
            "FAIL": "\033[91m❌",      # Red  
            "WARNING": "\033[93m⚠️ ",  # Yellow
            "INFO": "\033[94mℹ️ "      # Blue
        }
        
        severity_colors = {
            "CRITICAL": "\033[91m🚨",  # Red
            "HIGH": "\033[93m⚠️ ",     # Yellow
            "MEDIUM": "\033[94mℹ️ ",   # Blue
            "LOW": "\033[90m📝",       # Gray
            "INFO": "\033[94mℹ️ "      # Blue
        }
        
        color = colors.get(result.status, "")
        severity_color = severity_colors.get(result.severity, "")
        reset = "\033[0m"
        
        print(f"{color} {severity_color} [{result.category}] {result.check_name}: {result.description}{reset}")
    
    def audit_csrf_implementation(self):
        """Audit CSRF protection implementation."""
        logger.info("🔍 Auditing CSRF Protection Implementation...")
        
        # Check CSRF middleware exists
        csrf_middleware_path = self.backend_path / "middleware" / "csrf_protection.py"
        if csrf_middleware_path.exists():
            self.add_result(SecurityAuditResult(
                category="CSRF Protection",
                check_name="CSRF Middleware File",
                status="PASS",
                severity="INFO",
                description="CSRF protection middleware file exists"
            ))
            
            # Analyze CSRF middleware implementation
            self._analyze_csrf_middleware(csrf_middleware_path)
        else:
            self.add_result(SecurityAuditResult(
                category="CSRF Protection", 
                check_name="CSRF Middleware File",
                status="FAIL",
                severity="CRITICAL",
                description="CSRF protection middleware file missing",
                recommendation="Implement CSRF protection middleware"
            ))
        
        # Check CSRF router exists
        csrf_router_path = self.backend_path / "routers" / "csrf_security.py"
        if csrf_router_path.exists():
            self.add_result(SecurityAuditResult(
                category="CSRF Protection",
                check_name="CSRF Security Router",
                status="PASS", 
                severity="INFO",
                description="CSRF security router exists"
            ))
        else:
            self.add_result(SecurityAuditResult(
                category="CSRF Protection",
                check_name="CSRF Security Router", 
                status="FAIL",
                severity="HIGH",
                description="CSRF security router missing",
                recommendation="Implement CSRF security endpoints"
            ))
        
        # Check main.py integration
        self._audit_main_py_csrf_integration()
    
    def _analyze_csrf_middleware(self, filepath: Path):
        """Analyze CSRF middleware implementation."""
        try:
            content = filepath.read_text()
            
            # Check for key CSRF features
            csrf_features = {
                "Double-submit cookie pattern": "double.submit" in content.lower() or "cookie" in content,
                "Token generation": "generate" in content and "token" in content,
                "Token validation": "validate" in content and "csrf" in content,
                "HMAC signing": "hmac" in content,
                "Rate limiting": "rate_limit" in content or "rate.limit" in content,
                "Origin validation": "origin" in content and "validate" in content,
                "Secure token storage": "secure" in content and "token" in content
            }
            
            for feature, implemented in csrf_features.items():
                self.add_result(SecurityAuditResult(
                    category="CSRF Protection",
                    check_name=f"CSRF Feature: {feature}",
                    status="PASS" if implemented else "WARNING",
                    severity="MEDIUM" if implemented else "HIGH",
                    description=f"{feature} {'implemented' if implemented else 'not detected'}",
                    recommendation=None if implemented else f"Implement {feature} in CSRF middleware"
                ))
                
        except Exception as e:
            self.add_result(SecurityAuditResult(
                category="CSRF Protection",
                check_name="CSRF Middleware Analysis",
                status="FAIL",
                severity="HIGH", 
                description=f"Failed to analyze CSRF middleware: {e}",
                recommendation="Review and fix CSRF middleware implementation"
            ))
    
    def _audit_main_py_csrf_integration(self):
        """Audit CSRF integration in main.py."""
        main_py_path = self.backend_path / "main.py"
        
        if not main_py_path.exists():
            self.add_result(SecurityAuditResult(
                category="CSRF Protection",
                check_name="Main.py Integration",
                status="FAIL",
                severity="CRITICAL",
                description="main.py file not found",
                recommendation="Ensure main.py exists and includes CSRF middleware"
            ))
            return
        
        try:
            content = main_py_path.read_text()
            
            # Check for CSRF middleware registration
            csrf_registered = "CSRFProtectionMiddleware" in content or "csrf_protection" in content
            self.add_result(SecurityAuditResult(
                category="CSRF Protection",
                check_name="CSRF Middleware Registration",
                status="PASS" if csrf_registered else "FAIL",
                severity="INFO" if csrf_registered else "CRITICAL",
                description=f"CSRF middleware {'registered' if csrf_registered else 'not registered'} in main.py",
                recommendation=None if csrf_registered else "Register CSRF middleware in main.py"
            ))
            
            # Check for CSRF router registration
            csrf_router_registered = "csrf_security" in content
            self.add_result(SecurityAuditResult(
                category="CSRF Protection",
                check_name="CSRF Router Registration", 
                status="PASS" if csrf_router_registered else "WARNING",
                severity="INFO" if csrf_router_registered else "MEDIUM",
                description=f"CSRF router {'registered' if csrf_router_registered else 'not registered'} in main.py",
                recommendation=None if csrf_router_registered else "Register CSRF security router in main.py"
            ))
            
        except Exception as e:
            self.add_result(SecurityAuditResult(
                category="CSRF Protection",
                check_name="Main.py Integration Analysis",
                status="FAIL",
                severity="HIGH",
                description=f"Failed to analyze main.py: {e}",
                recommendation="Review main.py for CSRF integration issues"
            ))
    
    def audit_security_headers(self):
        """Audit security headers implementation.""" 
        logger.info("🔍 Auditing Security Headers Implementation...")
        
        # Check security middleware files
        security_files = [
            ("security.py", "Basic Security Middleware"),
            ("security_enhanced.py", "Enhanced Security Middleware")
        ]
        
        for filename, description in security_files:
            filepath = self.backend_path / "middleware" / filename
            if filepath.exists():
                self.add_result(SecurityAuditResult(
                    category="Security Headers",
                    check_name=description,
                    status="PASS",
                    severity="INFO", 
                    description=f"{description} file exists"
                ))
                
                self._analyze_security_middleware(filepath, filename)
            else:
                self.add_result(SecurityAuditResult(
                    category="Security Headers",
                    check_name=description,
                    status="WARNING",
                    severity="MEDIUM",
                    description=f"{description} file missing"
                ))
    
    def _analyze_security_middleware(self, filepath: Path, filename: str):
        """Analyze security middleware implementation."""
        try:
            content = filepath.read_text()
            
            # OWASP recommended security headers
            owasp_headers = {
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "X-XSS-Protection": "1; mode=block", 
                "Strict-Transport-Security": "HSTS",
                "Content-Security-Policy": "CSP",
                "Referrer-Policy": "strict-origin-when-cross-origin",
                "Permissions-Policy": "Feature policy"
            }
            
            for header, description in owasp_headers.items():
                header_implemented = header.replace("-", "").lower() in content.lower()
                
                self.add_result(SecurityAuditResult(
                    category="Security Headers",
                    check_name=f"OWASP Header: {header}",
                    status="PASS" if header_implemented else "WARNING",
                    severity="INFO" if header_implemented else "MEDIUM",
                    description=f"{description} header {'implemented' if header_implemented else 'not detected'}",
                    recommendation=None if header_implemented else f"Implement {header} header"
                ))
            
            # Check for threat detection
            threat_features = [
                ("SQL Injection Detection", "sql.*injection"),
                ("XSS Protection", "xss.*protection|script.*block"),
                ("Path Traversal Detection", "path.*traversal|\\.\\./"),
                ("Rate Limiting", "rate.*limit"),
                ("IP Blocking", "block.*ip|ip.*block")
            ]
            
            import re
            for feature, pattern in threat_features:
                detected = bool(re.search(pattern, content, re.IGNORECASE))
                
                self.add_result(SecurityAuditResult(
                    category="Threat Detection",
                    check_name=feature,
                    status="PASS" if detected else "WARNING", 
                    severity="INFO" if detected else "MEDIUM",
                    description=f"{feature} {'detected' if detected else 'not detected'}",
                    recommendation=None if detected else f"Implement {feature}"
                ))
                
        except Exception as e:
            self.add_result(SecurityAuditResult(
                category="Security Headers",
                check_name=f"Security Middleware Analysis ({filename})",
                status="FAIL",
                severity="HIGH",
                description=f"Failed to analyze {filename}: {e}",
                recommendation=f"Review and fix {filename} implementation"
            ))
    
    def audit_configuration_security(self):
        """Audit security configuration."""
        logger.info("🔍 Auditing Security Configuration...")
        
        config_path = self.backend_path / "config.py"
        if not config_path.exists():
            self.add_result(SecurityAuditResult(
                category="Configuration Security",
                check_name="Config File Exists",
                status="FAIL", 
                severity="CRITICAL",
                description="config.py file not found",
                recommendation="Create secure configuration file"
            ))
            return
        
        try:
            content = config_path.read_text()
            
            # Security configuration checks
            security_configs = {
                "CSRF Protection Enabled": "csrf_protection_enabled",
                "Security Headers Enabled": "security_headers_enabled", 
                "Production Security Validation": "_validate_production_security",
                "JWT Secret Validation": "jwt_secret",
                "HSTS Configuration": "hsts_max_age",
                "CSP Configuration": "content_security_policy"
            }
            
            for config_name, config_key in security_configs.items():
                configured = config_key.lower() in content.lower()
                
                self.add_result(SecurityAuditResult(
                    category="Configuration Security",
                    check_name=config_name,
                    status="PASS" if configured else "WARNING",
                    severity="INFO" if configured else "MEDIUM",
                    description=f"{config_name} {'configured' if configured else 'not configured'}",
                    recommendation=None if configured else f"Configure {config_name}"
                ))
            
            # Check for dangerous defaults
            dangerous_patterns = [
                ("Default JWT Secret", "your-secret-key-change-in-production"),
                ("Debug Mode in Production", "debug.*=.*true"),
                ("Verbose Error Messages", "verbose_error_messages.*=.*true")
            ]
            
            import re
            for issue, pattern in dangerous_patterns:
                found = bool(re.search(pattern, content, re.IGNORECASE))
                
                if found:
                    self.add_result(SecurityAuditResult(
                        category="Configuration Security", 
                        check_name=f"Security Issue: {issue}",
                        status="FAIL",
                        severity="CRITICAL",
                        description=f"{issue} detected in configuration",
                        recommendation=f"Fix {issue} for production security"
                    ))
                    
        except Exception as e:
            self.add_result(SecurityAuditResult(
                category="Configuration Security",
                check_name="Configuration Analysis",
                status="FAIL",
                severity="HIGH",
                description=f"Failed to analyze configuration: {e}",
                recommendation="Review configuration file for security issues"
            ))
    
    def audit_dependencies_security(self):
        """Audit dependencies for security vulnerabilities."""
        logger.info("🔍 Auditing Dependencies Security...")
        
        requirements_path = self.backend_path / "requirements.txt"
        if not requirements_path.exists():
            self.add_result(SecurityAuditResult(
                category="Dependencies Security",
                check_name="Requirements File",
                status="WARNING",
                severity="MEDIUM", 
                description="requirements.txt not found",
                recommendation="Create requirements.txt with pinned versions"
            ))
            return
        
        try:
            # Check for pip-audit if available
            result = subprocess.run(
                ["pip-audit", "--format=json", "--requirement", str(requirements_path)],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                # Parse pip-audit results
                try:
                    audit_data = json.loads(result.stdout)
                    vulnerabilities = audit_data.get("vulnerabilities", [])
                    
                    if not vulnerabilities:
                        self.add_result(SecurityAuditResult(
                            category="Dependencies Security",
                            check_name="Vulnerability Scan",
                            status="PASS",
                            severity="INFO",
                            description="No known vulnerabilities found in dependencies"
                        ))
                    else:
                        for vuln in vulnerabilities:
                            package = vuln.get("package", "unknown")
                            version = vuln.get("installed_version", "unknown")
                            cve = vuln.get("id", "unknown")
                            
                            self.add_result(SecurityAuditResult(
                                category="Dependencies Security",
                                check_name=f"Vulnerability: {package}",
                                status="FAIL",
                                severity="HIGH",
                                description=f"Vulnerable package {package}@{version} ({cve})",
                                recommendation=f"Update {package} to fix {cve}",
                                details=vuln
                            ))
                            
                except json.JSONDecodeError:
                    self.add_result(SecurityAuditResult(
                        category="Dependencies Security",
                        check_name="Vulnerability Scan",
                        status="WARNING",
                        severity="MEDIUM",
                        description="pip-audit output could not be parsed"
                    ))
                    
            else:
                # pip-audit not available or failed
                self.add_result(SecurityAuditResult(
                    category="Dependencies Security", 
                    check_name="Vulnerability Scan",
                    status="WARNING",
                    severity="LOW",
                    description="pip-audit not available or failed",
                    recommendation="Install pip-audit for dependency vulnerability scanning"
                ))
                
        except FileNotFoundError:
            self.add_result(SecurityAuditResult(
                category="Dependencies Security",
                check_name="Vulnerability Scan Tool",
                status="WARNING",
                severity="LOW", 
                description="pip-audit tool not installed",
                recommendation="Install pip-audit: pip install pip-audit"
            ))
        except subprocess.TimeoutExpired:
            self.add_result(SecurityAuditResult(
                category="Dependencies Security",
                check_name="Vulnerability Scan",
                status="WARNING", 
                severity="MEDIUM",
                description="Vulnerability scan timed out",
                recommendation="Check dependencies manually for vulnerabilities"
            ))
    
    def audit_file_permissions(self):
        """Audit file permissions for security."""
        logger.info("🔍 Auditing File Permissions...")
        
        # Critical files that should not be world-readable
        critical_files = [
            ".env",
            ".env.production",
            ".env.local",
            "config.py",
            "database.py"
        ]
        
        for filename in critical_files:
            filepath = self.backend_path / filename
            if filepath.exists():
                try:
                    import stat
                    file_stat = filepath.stat()
                    permissions = stat.filemode(file_stat.st_mode)
                    
                    # Check if file is world-readable (dangerous for config files)
                    world_readable = file_stat.st_mode & stat.S_IROTH
                    
                    self.add_result(SecurityAuditResult(
                        category="File Permissions",
                        check_name=f"File Permissions: {filename}",
                        status="WARNING" if world_readable else "PASS",
                        severity="MEDIUM" if world_readable else "INFO",
                        description=f"{filename} permissions: {permissions}",
                        recommendation="Restrict file permissions (chmod 600)" if world_readable else None,
                        details={"permissions": permissions, "world_readable": bool(world_readable)}
                    ))
                    
                except Exception as e:
                    self.add_result(SecurityAuditResult(
                        category="File Permissions",
                        check_name=f"File Permissions Check: {filename}",
                        status="WARNING",
                        severity="LOW",
                        description=f"Could not check permissions for {filename}: {e}"
                    ))
    
    def audit_documentation(self):
        """Audit security documentation."""
        logger.info("🔍 Auditing Security Documentation...")
        
        docs_path = self.backend_path / "docs"
        security_docs = [
            ("CSRF_FRONTEND_INTEGRATION.md", "CSRF Frontend Integration Guide"),
            ("SECURITY_AUDIT_REPORT.md", "Security Audit Report"),
            ("SECURITY_FIXES_JWT_PHASE1_STEP2.md", "JWT Security Fixes")
        ]
        
        for doc_file, description in security_docs:
            doc_path = docs_path / doc_file
            if doc_path.exists():
                self.add_result(SecurityAuditResult(
                    category="Documentation", 
                    check_name=description,
                    status="PASS",
                    severity="INFO",
                    description=f"{description} documentation exists"
                ))
            else:
                self.add_result(SecurityAuditResult(
                    category="Documentation",
                    check_name=description,
                    status="WARNING", 
                    severity="LOW",
                    description=f"{description} documentation missing",
                    recommendation=f"Create {doc_file} documentation"
                ))
    
    def run_comprehensive_audit(self) -> Dict[str, Any]:
        """Run comprehensive security audit."""
        logger.info("🚀 Starting Comprehensive Security Audit...")
        logger.info(f"🎯 Project Root: {self.project_root}")
        logger.info(f"🎯 Backend Path: {self.backend_path}")
        
        # Run all audit categories
        audit_functions = [
            self.audit_csrf_implementation,
            self.audit_security_headers,
            self.audit_configuration_security,
            self.audit_dependencies_security,
            self.audit_file_permissions,
            self.audit_documentation
        ]
        
        for audit_func in audit_functions:
            try:
                audit_func()
            except Exception as e:
                logger.error(f"❌ Audit function {audit_func.__name__} failed: {e}")
                self.add_result(SecurityAuditResult(
                    category="Audit System",
                    check_name=f"Audit Function: {audit_func.__name__}",
                    status="FAIL",
                    severity="HIGH",
                    description=f"Audit function failed: {e}",
                    recommendation="Review audit system for issues"
                ))
        
        return self.generate_audit_report()
    
    def generate_audit_report(self) -> Dict[str, Any]:
        """Generate comprehensive audit report."""
        # Calculate statistics
        total_checks = len(self.results)
        
        status_counts = {}
        severity_counts = {}
        category_counts = {}
        
        for result in self.results:
            status_counts[result.status] = status_counts.get(result.status, 0) + 1
            severity_counts[result.severity] = severity_counts.get(result.severity, 0) + 1
            category_counts[result.category] = category_counts.get(result.category, 0) + 1
        
        # Determine overall security posture
        critical_issues = severity_counts.get("CRITICAL", 0)
        high_issues = severity_counts.get("HIGH", 0)
        
        if critical_issues > 0:
            overall_status = "CRITICAL"
            overall_message = f"Critical security issues found: {critical_issues}"
        elif high_issues > 0:
            overall_status = "HIGH_RISK"
            overall_message = f"High-risk security issues found: {high_issues}"
        elif severity_counts.get("MEDIUM", 0) > 5:
            overall_status = "MEDIUM_RISK"
            overall_message = "Multiple medium-risk issues require attention"
        else:
            overall_status = "SECURE"
            overall_message = "Good security posture with minor issues"
        
        # Generate recommendations
        recommendations = self._generate_security_recommendations()
        
        report = {
            "security_audit_report": {
                "metadata": {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                    "audit_version": "1.0",
                    "project_root": str(self.project_root),
                    "backend_path": str(self.backend_path)
                },
                "summary": {
                    "overall_status": overall_status,
                    "overall_message": overall_message,
                    "total_checks": total_checks,
                    "status_distribution": status_counts,
                    "severity_distribution": severity_counts,
                    "category_distribution": category_counts
                },
                "detailed_results": [asdict(result) for result in self.results],
                "security_recommendations": recommendations,
                "compliance": {
                    "owasp_top_10": self._check_owasp_compliance(),
                    "csrf_protection": self._check_csrf_compliance(),
                    "security_headers": self._check_headers_compliance()
                }
            }
        }
        
        return report
    
    def _generate_security_recommendations(self) -> List[str]:
        """Generate security recommendations based on audit results."""
        recommendations = []
        
        # Critical issues first
        critical_results = [r for r in self.results if r.severity == "CRITICAL"]
        for result in critical_results:
            if result.recommendation:
                recommendations.append(f"CRITICAL: {result.recommendation}")
        
        # High-priority issues
        high_results = [r for r in self.results if r.severity == "HIGH"]
        for result in high_results:
            if result.recommendation and result.recommendation not in recommendations:
                recommendations.append(f"HIGH: {result.recommendation}")
        
        # Medium-priority issues (limit to most important)
        medium_results = [r for r in self.results if r.severity == "MEDIUM" and r.status == "FAIL"]
        for result in medium_results[:5]:  # Top 5 medium issues
            if result.recommendation and result.recommendation not in recommendations:
                recommendations.append(f"MEDIUM: {result.recommendation}")
        
        # General recommendations
        if not critical_results and not high_results:
            recommendations.append("Maintain current security posture with regular audits")
            recommendations.append("Consider implementing additional security monitoring")
        
        return recommendations
    
    def _check_owasp_compliance(self) -> Dict[str, Any]:
        """Check OWASP Top 10 compliance."""
        owasp_categories = {
            "A01_Broken_Access_Control": ["CSRF Protection", "Authentication"],
            "A02_Cryptographic_Failures": ["Configuration Security", "Dependencies Security"],
            "A03_Injection": ["Threat Detection", "Input Validation"],
            "A04_Insecure_Design": ["Security Headers", "Configuration Security"],
            "A05_Security_Misconfiguration": ["Configuration Security", "File Permissions"],
            "A06_Vulnerable_Components": ["Dependencies Security"],
            "A07_Authentication_Failures": ["CSRF Protection", "Authentication"],
            "A08_Software_Integrity_Failures": ["Dependencies Security"],
            "A09_Security_Logging_Failures": ["Documentation", "Audit System"], 
            "A10_Server_Side_Request_Forgery": ["Threat Detection", "Input Validation"]
        }
        
        compliance_status = {}
        for owasp_item, categories in owasp_categories.items():
            relevant_results = [r for r in self.results if r.category in categories]
            failed_results = [r for r in relevant_results if r.status == "FAIL"]
            
            if not relevant_results:
                compliance_status[owasp_item] = "NOT_ASSESSED"
            elif failed_results:
                compliance_status[owasp_item] = "NON_COMPLIANT"
            else:
                compliance_status[owasp_item] = "COMPLIANT"
        
        return compliance_status
    
    def _check_csrf_compliance(self) -> Dict[str, Any]:
        """Check CSRF protection compliance."""
        csrf_results = [r for r in self.results if r.category == "CSRF Protection"]
        csrf_failed = [r for r in csrf_results if r.status == "FAIL"]
        csrf_passed = [r for r in csrf_results if r.status == "PASS"]
        
        return {
            "status": "COMPLIANT" if not csrf_failed else "NON_COMPLIANT",
            "total_checks": len(csrf_results),
            "passed_checks": len(csrf_passed),
            "failed_checks": len(csrf_failed)
        }
    
    def _check_headers_compliance(self) -> Dict[str, Any]:
        """Check security headers compliance."""
        headers_results = [r for r in self.results if r.category == "Security Headers"]
        headers_failed = [r for r in headers_results if r.status == "FAIL"]
        headers_passed = [r for r in headers_results if r.status == "PASS"]
        
        return {
            "status": "COMPLIANT" if not headers_failed else "NON_COMPLIANT", 
            "total_checks": len(headers_results),
            "passed_checks": len(headers_passed),
            "failed_checks": len(headers_failed)
        }

def main():
    """Main audit execution."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Comprehensive Security Audit")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    parser.add_argument("--output", default="security_audit_report.json", help="Output report file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    # Run audit
    auditor = SecurityAuditor(args.project_root)
    report = auditor.run_comprehensive_audit()
    
    # Save report
    with open(args.output, 'w') as f:
        json.dump(report, f, indent=2)
    
    # Print summary
    summary = report["security_audit_report"]["summary"]
    print("\n" + "="*80)
    print("🛡️  COMPREHENSIVE SECURITY AUDIT RESULTS")
    print("="*80)
    print(f"📊 Overall Status: {summary['overall_status']}")
    print(f"📝 {summary['overall_message']}")
    print(f"🔍 Total Checks: {summary['total_checks']}")
    print(f"✅ Passed: {summary['status_distribution'].get('PASS', 0)}")
    print(f"❌ Failed: {summary['status_distribution'].get('FAIL', 0)}")
    print(f"⚠️  Warnings: {summary['status_distribution'].get('WARNING', 0)}")
    print("="*80)
    
    # Print recommendations
    recommendations = report["security_audit_report"]["security_recommendations"]
    if recommendations:
        print("\n🔧 TOP SECURITY RECOMMENDATIONS:")
        for i, rec in enumerate(recommendations[:10], 1):  # Top 10
            print(f"{i}. {rec}")
    
    # Print compliance status
    compliance = report["security_audit_report"]["compliance"]
    print("\n📋 COMPLIANCE STATUS:")
    print(f"🛡️  CSRF Protection: {compliance['csrf_protection']['status']}")
    print(f"🔒 Security Headers: {compliance['security_headers']['status']}")
    
    owasp_compliant = sum(1 for status in compliance['owasp_top_10'].values() if status == 'COMPLIANT')
    owasp_total = len(compliance['owasp_top_10'])
    print(f"🏆 OWASP Top 10: {owasp_compliant}/{owasp_total} categories compliant")
    
    print(f"\n📋 Detailed report saved: {args.output}")
    
    # Exit with appropriate code
    critical_issues = summary["severity_distribution"].get("CRITICAL", 0)
    high_issues = summary["severity_distribution"].get("HIGH", 0)
    
    if critical_issues > 0:
        print(f"\n🚨 CRITICAL: {critical_issues} critical security issues must be addressed immediately!")
        sys.exit(2)
    elif high_issues > 0:
        print(f"\n⚠️  HIGH RISK: {high_issues} high-risk security issues should be addressed")
        sys.exit(1)
    else:
        print(f"\n✅ Security audit completed successfully")
        sys.exit(0)

if __name__ == "__main__":
    main()