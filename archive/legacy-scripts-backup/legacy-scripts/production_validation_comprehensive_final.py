#!/usr/bin/env python3
"""
COMPREHENSIVE PRODUCTION VALIDATION SUITE
=========================================

This script validates ALL PRD claims against actual production implementation
to identify gaps between claimed features and reality.

CRITICAL VALIDATION AREAS:
1. Performance Claims vs Reality
2. Database Migration Status  
3. Authorization Layer Implementation
4. Security Feature Validation
5. Monitoring System Status
6. Cache Performance Analysis
"""

import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ProductionValidator:
    """Comprehensive production validation against PRD claims"""
    
    def __init__(self):
        self.results = {
            'validation_timestamp': datetime.now().isoformat(),
            'validation_summary': {},
            'performance_tests': {},
            'database_validation': {},
            'feature_validation': {},
            'security_validation': {},
            'gaps_identified': [],
            'critical_findings': []
        }
        
        # PRD Claims to validate
        self.prd_claims = {
            'performance': {
                'avg_response_time_ms': 75,
                'max_response_time_ms': 100,
                'cache_hit_rate_percent': 95,
                'concurrent_users': 10000,
                'database_improvement_percent': 81
            },
            'authorization_layers': 10,
            'security_compliance': 'OWASP Top 10 2021 compliant',
            'migrations': ['012', '013'],
            'monitoring': 'Real-time performance tracking'
        }
    
    def run_shell_command(self, command: str, timeout: int = 30) -> Dict[str, Any]:
        """Run shell command and return results"""
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, 
                text=True, timeout=timeout
            )
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': f'Command timed out after {timeout}s',
                'stdout': '',
                'stderr': ''
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'stdout': '',
                'stderr': ''
            }
    
    def test_production_performance(self) -> Dict[str, Any]:
        """Test actual production performance vs PRD claims"""
        logger.info("🧪 Testing Production Performance...")
        
        base_url = "https://velro-backend-production.up.railway.app"
        endpoints_to_test = [
            ('/api/auth/me', 'Authorization Endpoint'),
            ('/api/generations', 'Generation Endpoint'),
            ('/api/projects', 'Project Endpoint'),
            ('/health', 'Health Check Endpoint')
        ]
        
        performance_results = {}
        
        for endpoint, name in endpoints_to_test:
            url = f"{base_url}{endpoint}"
            response_times = []
            
            logger.info(f"Testing {name}: {url}")
            
            # Test 5 times for average
            for i in range(5):
                curl_command = f"curl -s -w '%{{time_total}}' -o /dev/null '{url}'"
                result = self.run_shell_command(curl_command, timeout=30)
                
                if result['success']:
                    try:
                        response_time_s = float(result['stdout'].strip())
                        response_time_ms = response_time_s * 1000
                        response_times.append(response_time_ms)
                        logger.info(f"  Request {i+1}: {response_time_ms:.2f}ms")
                    except (ValueError, TypeError):
                        logger.error(f"  Request {i+1}: Invalid response time")
                else:
                    logger.error(f"  Request {i+1}: Failed - {result.get('error', 'Unknown error')}")
            
            if response_times:
                avg_response = sum(response_times) / len(response_times)
                max_response = max(response_times)
                min_response = min(response_times)
                
                # Compare against PRD claims
                meets_avg_claim = avg_response < self.prd_claims['performance']['avg_response_time_ms']
                meets_max_claim = max_response < self.prd_claims['performance']['max_response_time_ms']
                
                performance_results[endpoint] = {
                    'name': name,
                    'avg_response_time_ms': round(avg_response, 2),
                    'max_response_time_ms': round(max_response, 2),
                    'min_response_time_ms': round(min_response, 2),
                    'claimed_avg_target': self.prd_claims['performance']['avg_response_time_ms'],
                    'claimed_max_target': self.prd_claims['performance']['max_response_time_ms'],
                    'meets_avg_claim': meets_avg_claim,
                    'meets_max_claim': meets_max_claim,
                    'performance_gap_ms': max(0, avg_response - self.prd_claims['performance']['avg_response_time_ms']),
                    'performance_multiplier': round(avg_response / self.prd_claims['performance']['avg_response_time_ms'], 2)
                }
                
                # Add to critical findings if performance is significantly off
                if avg_response > self.prd_claims['performance']['avg_response_time_ms'] * 2:
                    self.results['critical_findings'].append({
                        'type': 'Performance Gap',
                        'endpoint': endpoint,
                        'claim': f"<{self.prd_claims['performance']['avg_response_time_ms']}ms average",
                        'reality': f"{avg_response:.2f}ms average",
                        'severity': 'HIGH',
                        'gap_factor': f"{avg_response / self.prd_claims['performance']['avg_response_time_ms']:.1f}x slower than claimed"
                    })
            else:
                performance_results[endpoint] = {
                    'name': name,
                    'status': 'FAILED - No successful requests',
                    'meets_claims': False
                }
                
                self.results['critical_findings'].append({
                    'type': 'Endpoint Failure',
                    'endpoint': endpoint,
                    'severity': 'CRITICAL',
                    'description': 'Endpoint completely unreachable'
                })
        
        return performance_results
    
    def validate_database_migrations(self) -> Dict[str, Any]:
        """Check if claimed migrations are actually applied"""
        logger.info("🔍 Validating Database Migrations...")
        
        migration_files = [
            '012_performance_optimization_authorization.sql',
            '013_enterprise_performance_optimization.sql'
        ]
        
        migration_results = {}
        
        for migration_file in migration_files:
            migration_path = f"migrations/{migration_file}"
            
            # Check if migration file exists
            file_exists = os.path.exists(migration_path)
            migration_results[migration_file] = {
                'file_exists': file_exists,
                'claimed_in_prd': True
            }
            
            if file_exists:
                # Check migration content for key features
                try:
                    with open(migration_path, 'r') as f:
                        content = f.read()
                        
                    # Look for claimed features
                    features_to_check = [
                        'materialized view',
                        'composite index',
                        'authorization_cache',
                        'performance_optimization',
                        'connection_pool'
                    ]
                    
                    features_found = {}
                    for feature in features_to_check:
                        features_found[feature] = feature.lower() in content.lower()
                    
                    migration_results[migration_file]['features_implemented'] = features_found
                    migration_results[migration_file]['total_features_found'] = sum(features_found.values())
                    
                except Exception as e:
                    migration_results[migration_file]['error'] = f"Could not read migration: {e}"
            else:
                self.results['critical_findings'].append({
                    'type': 'Missing Migration',
                    'file': migration_file,
                    'severity': 'HIGH',
                    'description': f'Migration {migration_file} claimed in PRD but file does not exist'
                })
        
        return migration_results
    
    def validate_authorization_layers(self) -> Dict[str, Any]:
        """Check if claimed 10-layer authorization framework exists"""
        logger.info("🔐 Validating Authorization Layer Claims...")
        
        auth_files_to_check = [
            'security/secure_authorization_engine.py',
            'services/authorization_service.py',
            'utils/enhanced_uuid_utils.py'
        ]
        
        layer_validation = {
            'claimed_layers': self.prd_claims['authorization_layers'],
            'files_checked': {},
            'actual_layers_found': 0
        }
        
        authorization_layers = [
            'Input Security Validation',
            'Security Context Validation', 
            'Direct Ownership Verification',
            'Team-Based Access Control',
            'Project Visibility Controls',
            'Generation Inheritance Validation',
            'Media Access Authorization',
            'Performance Optimization',
            'Audit and Security Logging',
            'Emergency and Recovery Systems'
        ]
        
        for file_path in auth_files_to_check:
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r') as f:
                        content = f.read()
                    
                    # Count how many claimed layers are actually implemented
                    layers_found = 0
                    for layer in authorization_layers:
                        if layer.lower() in content.lower():
                            layers_found += 1
                    
                    layer_validation['files_checked'][file_path] = {
                        'exists': True,
                        'layers_referenced': layers_found,
                        'file_size_lines': len(content.split('\n'))
                    }
                    
                    layer_validation['actual_layers_found'] = max(
                        layer_validation['actual_layers_found'], 
                        layers_found
                    )
                    
                except Exception as e:
                    layer_validation['files_checked'][file_path] = {
                        'exists': True,
                        'error': str(e)
                    }
            else:
                layer_validation['files_checked'][file_path] = {
                    'exists': False
                }
                
                self.results['critical_findings'].append({
                    'type': 'Missing Authorization Component',
                    'file': file_path,
                    'severity': 'HIGH',
                    'description': f'Authorization file {file_path} claimed in PRD but does not exist'
                })
        
        # Check if actual layers match claimed layers
        layer_gap = self.prd_claims['authorization_layers'] - layer_validation['actual_layers_found']
        if layer_gap > 0:
            self.results['critical_findings'].append({
                'type': 'Authorization Layer Gap',
                'claimed': f"{self.prd_claims['authorization_layers']} layers",
                'found': f"{layer_validation['actual_layers_found']} layers",
                'gap': f"{layer_gap} layers missing",
                'severity': 'HIGH',
                'description': f'Only {layer_validation["actual_layers_found"]} of claimed {self.prd_claims["authorization_layers"]} authorization layers found in implementation'
            })
        
        return layer_validation
    
    def validate_monitoring_system(self) -> Dict[str, Any]:
        """Check if claimed monitoring system exists and works"""
        logger.info("📊 Validating Monitoring System...")
        
        monitoring_files = [
            'monitoring/performance.py',
            'monitoring/metrics.py',
            'monitoring/logger.py'
        ]
        
        monitoring_validation = {
            'files_exist': {},
            'monitoring_active': False
        }
        
        for file_path in monitoring_files:
            exists = os.path.exists(file_path)
            monitoring_validation['files_exist'][file_path] = exists
            
            if not exists:
                self.results['critical_findings'].append({
                    'type': 'Missing Monitoring Component',
                    'file': file_path,
                    'severity': 'MEDIUM',
                    'description': f'Monitoring file {file_path} claimed in PRD but does not exist'
                })
        
        # Check if performance monitoring is actually implemented
        perf_file = 'monitoring/performance.py'
        if os.path.exists(perf_file):
            try:
                with open(perf_file, 'r') as f:
                    content = f.read()
                
                # Look for key monitoring features
                monitoring_features = [
                    'PerformanceTracker',
                    'sub-100ms',
                    'ResponseTimeMonitor',
                    'ConcurrencyMonitor',
                    'performance_tracker'
                ]
                
                features_found = sum(1 for feature in monitoring_features if feature in content)
                monitoring_validation['features_implemented'] = features_found
                monitoring_validation['total_features_expected'] = len(monitoring_features)
                monitoring_validation['monitoring_active'] = features_found >= 3
                
            except Exception as e:
                monitoring_validation['error'] = str(e)
        
        return monitoring_validation
    
    def validate_cache_performance(self) -> Dict[str, Any]:
        """Test cache-related claims"""
        logger.info("🗄️ Validating Cache Performance Claims...")
        
        cache_files = [
            'caching/multi_layer_cache_manager.py',
            'caching/redis_cache.py'
        ]
        
        cache_validation = {
            'claimed_hit_rate': self.prd_claims['performance']['cache_hit_rate_percent'],
            'cache_files_exist': {},
            'cache_system_implemented': False
        }
        
        cache_files_found = 0
        for file_path in cache_files:
            exists = os.path.exists(file_path)
            cache_validation['cache_files_exist'][file_path] = exists
            if exists:
                cache_files_found += 1
        
        cache_validation['cache_system_implemented'] = cache_files_found >= 1
        
        if cache_files_found == 0:
            self.results['critical_findings'].append({
                'type': 'Missing Cache System',
                'claimed': f"{self.prd_claims['performance']['cache_hit_rate_percent']}% cache hit rate",
                'reality': 'No cache system files found',
                'severity': 'HIGH',
                'description': 'PRD claims 95%+ cache hit rates but no caching system implementation found'
            })
        
        return cache_validation
    
    def generate_comprehensive_report(self) -> Dict[str, Any]:
        """Generate final comprehensive validation report"""
        logger.info("📋 Generating Comprehensive Validation Report...")
        
        # Run all validations
        self.results['performance_tests'] = self.test_production_performance()
        self.results['database_validation'] = self.validate_database_migrations()
        self.results['feature_validation'] = {
            'authorization_layers': self.validate_authorization_layers(),
            'monitoring_system': self.validate_monitoring_system(),
            'cache_performance': self.validate_cache_performance()
        }
        
        # Generate summary
        total_claims_tested = 0
        claims_validated = 0
        
        # Performance claims validation
        perf_tests = self.results['performance_tests']
        for endpoint, result in perf_tests.items():
            if isinstance(result, dict) and 'meets_avg_claim' in result:
                total_claims_tested += 1
                if result['meets_avg_claim']:
                    claims_validated += 1
        
        # Database migration claims
        db_results = self.results['database_validation']
        for migration, result in db_results.items():
            total_claims_tested += 1
            if result.get('file_exists', False):
                claims_validated += 1
        
        # Authorization layer claims
        auth_result = self.results['feature_validation']['authorization_layers']
        total_claims_tested += 1
        if auth_result['actual_layers_found'] >= self.prd_claims['authorization_layers'] * 0.8:  # 80% threshold
            claims_validated += 1
        
        # Calculate validation score
        validation_score = (claims_validated / total_claims_tested * 100) if total_claims_tested > 0 else 0
        
        self.results['validation_summary'] = {
            'total_claims_tested': total_claims_tested,
            'claims_validated': claims_validated,
            'validation_score_percent': round(validation_score, 1),
            'critical_findings_count': len(self.results['critical_findings']),
            'overall_status': self._determine_overall_status(validation_score)
        }
        
        # Add gap analysis
        self.results['gaps_identified'] = self._identify_gaps()
        
        return self.results
    
    def _determine_overall_status(self, validation_score: float) -> str:
        """Determine overall validation status based on score"""
        if validation_score >= 90:
            return "EXCELLENT - PRD claims largely validated"
        elif validation_score >= 70:
            return "GOOD - Most PRD claims validated with minor gaps"
        elif validation_score >= 50:
            return "CONCERNING - Significant gaps between PRD claims and reality"
        else:
            return "CRITICAL - Major discrepancies between PRD claims and actual implementation"
    
    def _identify_gaps(self) -> List[Dict[str, Any]]:
        """Identify specific gaps between PRD claims and reality"""
        gaps = []
        
        # Performance gaps
        perf_tests = self.results['performance_tests']
        for endpoint, result in perf_tests.items():
            if isinstance(result, dict) and not result.get('meets_avg_claim', True):
                gaps.append({
                    'category': 'Performance',
                    'component': result.get('name', endpoint),
                    'claim': f"<{self.prd_claims['performance']['avg_response_time_ms']}ms average response time",
                    'reality': f"{result.get('avg_response_time_ms', 'N/A')}ms average response time",
                    'impact': 'HIGH',
                    'recommendation': 'Implement claimed performance optimizations or update PRD with realistic targets'
                })
        
        # Authorization layer gaps
        auth_result = self.results['feature_validation']['authorization_layers']
        if auth_result['actual_layers_found'] < self.prd_claims['authorization_layers']:
            gaps.append({
                'category': 'Authorization',
                'component': 'Multi-layer Authorization Framework',
                'claim': f"{self.prd_claims['authorization_layers']} authorization layers",
                'reality': f"{auth_result['actual_layers_found']} layers found in implementation",
                'impact': 'HIGH',
                'recommendation': 'Complete implementation of all claimed authorization layers or update PRD'
            })
        
        # Missing file gaps
        for finding in self.results['critical_findings']:
            if finding['type'] in ['Missing Migration', 'Missing Authorization Component', 'Missing Monitoring Component']:
                gaps.append({
                    'category': 'Implementation',
                    'component': finding.get('file', finding.get('endpoint', 'Unknown')),
                    'claim': 'Component exists and is operational',
                    'reality': 'Component missing or non-functional',
                    'impact': finding['severity'],
                    'recommendation': 'Implement missing component or remove from PRD claims'
                })
        
        return gaps
    
    def save_report(self, filename: Optional[str] = None) -> str:
        """Save validation report to file"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"production_validation_report_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        logger.info(f"📄 Validation report saved to: {filename}")
        return filename
    
    def print_executive_summary(self):
        """Print executive summary of validation results"""
        summary = self.results['validation_summary']
        
        print("\n" + "="*80)
        print("🔍 PRODUCTION VALIDATION EXECUTIVE SUMMARY")
        print("="*80)
        print(f"Validation Date: {self.results['validation_timestamp']}")
        print(f"Total Claims Tested: {summary['total_claims_tested']}")
        print(f"Claims Validated: {summary['claims_validated']}")
        print(f"Validation Score: {summary['validation_score_percent']}%")
        print(f"Critical Findings: {summary['critical_findings_count']}")
        print(f"Overall Status: {summary['overall_status']}")
        
        print("\n📊 KEY FINDINGS:")
        
        # Performance findings
        perf_tests = self.results['performance_tests']
        print("\nPERFORMANCE VALIDATION:")
        for endpoint, result in perf_tests.items():
            if isinstance(result, dict) and 'avg_response_time_ms' in result:
                status = "✅ PASS" if result['meets_avg_claim'] else "❌ FAIL"
                print(f"  {result['name']}: {result['avg_response_time_ms']}ms avg (claimed <{result['claimed_avg_target']}ms) {status}")
        
        # Critical findings
        if self.results['critical_findings']:
            print("\n🚨 CRITICAL FINDINGS:")
            for finding in self.results['critical_findings'][:5]:  # Show top 5
                print(f"  • {finding['type']}: {finding.get('description', 'No description')}")
        
        # Gaps identified
        if self.results['gaps_identified']:
            print(f"\n📋 GAPS IDENTIFIED: {len(self.results['gaps_identified'])} total")
            high_impact_gaps = [gap for gap in self.results['gaps_identified'] if gap['impact'] == 'HIGH']
            print(f"  High Impact Gaps: {len(high_impact_gaps)}")
        
        print("\n" + "="*80)


def main():
    """Run comprehensive production validation"""
    print("🚀 VELRO PRODUCTION VALIDATION SUITE")
    print("====================================")
    
    validator = ProductionValidator()
    
    try:
        # Generate comprehensive report
        results = validator.generate_comprehensive_report()
        
        # Print executive summary
        validator.print_executive_summary()
        
        # Save detailed report
        report_file = validator.save_report()
        
        print(f"\n📊 Detailed validation report saved to: {report_file}")
        print("\nValidation complete!")
        
        # Return appropriate exit code
        validation_score = results['validation_summary']['validation_score_percent']
        if validation_score < 50:
            sys.exit(1)  # Critical issues found
        
    except Exception as e:
        logger.error(f"Validation failed with error: {e}")
        print(f"\n❌ VALIDATION FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()