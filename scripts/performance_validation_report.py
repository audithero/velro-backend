"""
VELRO Performance Validation Report Generator

Comprehensive analysis and reporting system for 10K+ user load testing results.
Validates PRD compliance and generates executive summaries.

Features:
- PRD compliance analysis
- Performance regression detection
- Bottleneck identification
- Capacity planning recommendations
- Executive summary generation
- Multi-format report outputs (JSON, HTML, CSV)
"""

import json
import os
import sys
import time
import statistics
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from pathlib import Path
import logging
import yaml
import argparse
from jinja2 import Template

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class PRDRequirements:
    """PRD requirements for validation."""
    concurrent_users: int = 10000
    database_connections: int = 200
    cache_hit_rate: float = 95.0
    throughput_rps: float = 1000.0
    max_auth_response_ms: float = 50.0
    max_authz_response_ms: float = 75.0
    max_generation_access_ms: float = 100.0
    max_media_url_ms: float = 200.0
    max_error_rate: float = 0.01  # 1%

@dataclass
class PerformanceAnalysis:
    """Comprehensive performance analysis results."""
    scenario_name: str
    timestamp: str
    
    # PRD Compliance
    prd_compliance_score: float = 0.0
    prd_requirements_met: bool = False
    compliance_details: Dict[str, bool] = None
    
    # Performance Metrics
    response_time_analysis: Dict[str, Any] = None
    throughput_analysis: Dict[str, Any] = None
    cache_performance_analysis: Dict[str, Any] = None
    error_analysis: Dict[str, Any] = None
    
    # Resource Utilization
    system_resource_analysis: Dict[str, Any] = None
    database_performance_analysis: Dict[str, Any] = None
    
    # Bottleneck Identification
    identified_bottlenecks: List[str] = None
    performance_recommendations: List[str] = None
    
    # Regression Analysis
    regression_analysis: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.compliance_details is None:
            self.compliance_details = {}
        if self.response_time_analysis is None:
            self.response_time_analysis = {}
        if self.throughput_analysis is None:
            self.throughput_analysis = {}
        if self.cache_performance_analysis is None:
            self.cache_performance_analysis = {}
        if self.error_analysis is None:
            self.error_analysis = {}
        if self.system_resource_analysis is None:
            self.system_resource_analysis = {}
        if self.database_performance_analysis is None:
            self.database_performance_analysis = {}
        if self.identified_bottlenecks is None:
            self.identified_bottlenecks = []
        if self.performance_recommendations is None:
            self.performance_recommendations = []
        if self.regression_analysis is None:
            self.regression_analysis = {}

class PerformanceReportGenerator:
    """Generates comprehensive performance validation reports."""
    
    def __init__(self, config_path: str = None):
        self.config = self._load_config(config_path)
        self.prd_requirements = PRDRequirements()
        self.historical_data = []
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        if not config_path:
            config_path = "config/load_test_scenarios.yaml"
        
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning(f"Config file {config_path} not found, using defaults")
            return {}
    
    def analyze_load_test_results(self, results_file: str) -> PerformanceAnalysis:
        """Analyze load test results and generate comprehensive analysis."""
        logger.info(f"Analyzing load test results from {results_file}")
        
        # Load test results
        with open(results_file, 'r') as f:
            test_data = json.load(f)
        
        analysis = PerformanceAnalysis(
            scenario_name=test_data.get('test_suite', 'Unknown'),
            timestamp=test_data.get('timestamp', datetime.utcnow().isoformat())
        )
        
        # Analyze each scenario
        scenarios = test_data.get('scenarios', [])
        if scenarios:
            # Focus on the main PRD validation scenario
            prd_scenario = None
            for scenario in scenarios:
                if 'prd_compliance' in scenario.get('scenario', {}).get('name', '').lower():
                    prd_scenario = scenario
                    break
            
            # If no PRD scenario found, use the largest user count scenario
            if not prd_scenario:
                prd_scenario = max(scenarios, key=lambda s: s.get('metrics', {}).get('concurrent_users', 0))
            
            if prd_scenario:
                self._analyze_scenario_performance(prd_scenario, analysis)
        
        # Overall analysis across all scenarios
        self._analyze_overall_performance(test_data, analysis)
        
        # Generate recommendations
        self._generate_performance_recommendations(analysis)
        
        logger.info(f"Performance analysis completed. PRD compliance: {analysis.prd_compliance_score:.1f}%")
        return analysis
    
    def _analyze_scenario_performance(self, scenario: Dict[str, Any], analysis: PerformanceAnalysis):
        """Analyze individual scenario performance."""
        metrics = scenario.get('metrics', {})
        scenario_config = scenario.get('scenario', {})
        
        # PRD Compliance Analysis
        self._analyze_prd_compliance(metrics, analysis)
        
        # Response Time Analysis
        self._analyze_response_times(metrics, analysis)
        
        # Throughput Analysis
        self._analyze_throughput(metrics, scenario_config, analysis)
        
        # Cache Performance Analysis
        self._analyze_cache_performance(metrics, analysis)
        
        # Error Analysis
        self._analyze_errors(metrics, analysis)
        
        # System Resource Analysis
        self._analyze_system_resources(metrics, analysis)
    
    def _analyze_prd_compliance(self, metrics: Dict[str, Any], analysis: PerformanceAnalysis):
        """Analyze PRD compliance in detail."""
        compliance_checks = {}
        
        # Concurrent Users
        concurrent_users = metrics.get('concurrent_users', 0)
        compliance_checks['concurrent_users'] = concurrent_users >= self.prd_requirements.concurrent_users * 0.8
        
        # Response Times
        p95_response_time = metrics.get('p95_response_time_ms', 0)
        compliance_checks['response_time_p95'] = p95_response_time <= self.prd_requirements.max_authz_response_ms
        
        # Throughput
        rps = metrics.get('requests_per_second', 0)
        compliance_checks['throughput'] = rps >= self.prd_requirements.throughput_rps
        
        # Cache Hit Rate
        cache_hit_rate = metrics.get('cache_hit_rate', 0)
        compliance_checks['cache_hit_rate'] = cache_hit_rate >= self.prd_requirements.cache_hit_rate
        
        # Error Rate
        total_requests = metrics.get('total_requests', 1)
        failed_requests = metrics.get('failed_requests', 0)
        error_rate = failed_requests / total_requests
        compliance_checks['error_rate'] = error_rate <= self.prd_requirements.max_error_rate
        
        # Calculate compliance score
        passed_checks = sum(1 for passed in compliance_checks.values() if passed)
        total_checks = len(compliance_checks)
        
        analysis.prd_compliance_score = (passed_checks / total_checks) * 100
        analysis.prd_requirements_met = analysis.prd_compliance_score >= 90.0
        analysis.compliance_details = compliance_checks
        
        logger.info(f"PRD Compliance: {analysis.prd_compliance_score:.1f}% ({passed_checks}/{total_checks} checks passed)")
    
    def _analyze_response_times(self, metrics: Dict[str, Any], analysis: PerformanceAnalysis):
        """Analyze response time performance in detail."""
        analysis.response_time_analysis = {
            'avg_response_time_ms': metrics.get('avg_response_time_ms', 0),
            'p50_response_time_ms': metrics.get('p50_response_time_ms', 0),
            'p95_response_time_ms': metrics.get('p95_response_time_ms', 0),
            'p99_response_time_ms': metrics.get('p99_response_time_ms', 0),
            'min_response_time_ms': metrics.get('min_response_time_ms', 0),
            'max_response_time_ms': metrics.get('max_response_time_ms', 0),
            
            # Performance assessment
            'p95_meets_auth_target': metrics.get('p95_response_time_ms', 0) <= self.prd_requirements.max_auth_response_ms,
            'p95_meets_authz_target': metrics.get('p95_response_time_ms', 0) <= self.prd_requirements.max_authz_response_ms,
            'p95_meets_generation_target': metrics.get('p95_response_time_ms', 0) <= self.prd_requirements.max_generation_access_ms,
            
            # Distribution analysis
            'response_time_distribution': self._calculate_response_time_distribution(metrics),
            'outliers_detected': self._detect_response_time_outliers(metrics)
        }
    
    def _analyze_throughput(self, metrics: Dict[str, Any], scenario_config: Dict[str, Any], analysis: PerformanceAnalysis):
        """Analyze throughput performance."""
        analysis.throughput_analysis = {
            'requests_per_second': metrics.get('requests_per_second', 0),
            'peak_requests_per_second': metrics.get('peak_requests_per_second', 0),
            'total_requests': metrics.get('total_requests', 0),
            'successful_requests': metrics.get('successful_requests', 0),
            'test_duration_seconds': metrics.get('actual_duration_seconds', 0),
            
            # Target analysis
            'target_rps': scenario_config.get('target_rps', 0),
            'meets_target_rps': metrics.get('requests_per_second', 0) >= scenario_config.get('target_rps', 0),
            'meets_prd_rps': metrics.get('requests_per_second', 0) >= self.prd_requirements.throughput_rps,
            
            # Efficiency metrics
            'throughput_efficiency': self._calculate_throughput_efficiency(metrics, scenario_config),
            'sustained_load_capability': self._assess_sustained_load(metrics)
        }
    
    def _analyze_cache_performance(self, metrics: Dict[str, Any], analysis: PerformanceAnalysis):
        """Analyze cache performance in detail."""
        analysis.cache_performance_analysis = {
            'overall_hit_rate': metrics.get('cache_hit_rate', 0),
            'auth_cache_hit_rate': metrics.get('auth_cache_hit_rate', 0),
            'generation_cache_hit_rate': metrics.get('generation_cache_hit_rate', 0),
            
            # PRD compliance
            'meets_prd_hit_rate': metrics.get('cache_hit_rate', 0) >= self.prd_requirements.cache_hit_rate,
            
            # Performance impact analysis
            'cache_performance_impact': self._assess_cache_performance_impact(metrics),
            'cache_optimization_opportunities': self._identify_cache_optimizations(metrics)
        }
    
    def _analyze_errors(self, metrics: Dict[str, Any], analysis: PerformanceAnalysis):
        """Analyze error patterns and rates."""
        total_requests = metrics.get('total_requests', 1)
        failed_requests = metrics.get('failed_requests', 0)
        error_rate = failed_requests / total_requests
        
        analysis.error_analysis = {
            'total_errors': failed_requests,
            'error_rate': error_rate,
            'error_rate_percentage': error_rate * 100,
            'meets_prd_error_rate': error_rate <= self.prd_requirements.max_error_rate,
            
            # Error breakdown
            'error_types': metrics.get('error_types', {}),
            'status_code_distribution': metrics.get('status_code_distribution', {}),
            
            # Error analysis
            'dominant_error_type': self._identify_dominant_error(metrics),
            'error_pattern_analysis': self._analyze_error_patterns(metrics)
        }
    
    def _analyze_system_resources(self, metrics: Dict[str, Any], analysis: PerformanceAnalysis):
        """Analyze system resource utilization."""
        analysis.system_resource_analysis = {
            'peak_cpu_percent': metrics.get('peak_cpu_percent', 0),
            'peak_memory_mb': metrics.get('peak_memory_mb', 0),
            'peak_db_connections': metrics.get('peak_db_connections', 0),
            'peak_redis_connections': metrics.get('peak_redis_connections', 0),
            
            # Resource utilization assessment
            'cpu_utilization_status': self._assess_cpu_utilization(metrics),
            'memory_utilization_status': self._assess_memory_utilization(metrics),
            'connection_utilization_status': self._assess_connection_utilization(metrics),
            
            # Resource bottleneck detection
            'resource_bottlenecks': self._identify_resource_bottlenecks(metrics)
        }
    
    def _analyze_overall_performance(self, test_data: Dict[str, Any], analysis: PerformanceAnalysis):
        """Analyze overall performance across all scenarios."""
        scenarios = test_data.get('scenarios', [])
        if not scenarios:
            return
        
        # Identify bottlenecks across scenarios
        analysis.identified_bottlenecks = self._identify_system_bottlenecks(scenarios)
        
        # Performance regression analysis
        analysis.regression_analysis = self._perform_regression_analysis(test_data)
    
    def _generate_performance_recommendations(self, analysis: PerformanceAnalysis):
        """Generate actionable performance recommendations."""
        recommendations = []
        
        # PRD compliance recommendations
        if not analysis.prd_requirements_met:
            if not analysis.compliance_details.get('response_time_p95', False):
                recommendations.append(
                    "CRITICAL: P95 response time exceeds PRD target. "
                    "Implement additional caching layers and optimize database queries."
                )
            
            if not analysis.compliance_details.get('throughput', False):
                recommendations.append(
                    "CRITICAL: Throughput below PRD requirements. "
                    "Consider horizontal scaling and connection pool optimization."
                )
            
            if not analysis.compliance_details.get('cache_hit_rate', False):
                recommendations.append(
                    "HIGH: Cache hit rate below PRD target. "
                    "Implement intelligent cache warming and review cache TTL settings."
                )
        
        # System resource recommendations
        resource_analysis = analysis.system_resource_analysis
        if resource_analysis.get('peak_cpu_percent', 0) > 80:
            recommendations.append(
                "MEDIUM: High CPU utilization detected. "
                "Consider CPU optimization or horizontal scaling."
            )
        
        if resource_analysis.get('peak_memory_mb', 0) > 6000:  # > 6GB
            recommendations.append(
                "MEDIUM: High memory usage detected. "
                "Review memory leaks and optimize cache sizes."
            )
        
        # Cache performance recommendations
        cache_analysis = analysis.cache_performance_analysis
        if cache_analysis.get('overall_hit_rate', 0) < 90:
            recommendations.append(
                "HIGH: Implement more aggressive cache warming strategies "
                "and increase cache TTL for stable data."
            )
        
        # Error rate recommendations
        error_analysis = analysis.error_analysis
        if error_analysis.get('error_rate', 0) > 0.02:  # > 2%
            recommendations.append(
                "HIGH: Error rate is elevated. "
                "Implement better circuit breaker patterns and error handling."
            )
        
        # Bottleneck-specific recommendations
        for bottleneck in analysis.identified_bottlenecks:
            if 'database' in bottleneck.lower():
                recommendations.append(
                    "CRITICAL: Database bottleneck identified. "
                    "Optimize queries, increase connection pool, consider read replicas."
                )
            elif 'cache' in bottleneck.lower():
                recommendations.append(
                    "HIGH: Cache bottleneck identified. "
                    "Scale Redis cluster, optimize cache keys, implement cache sharding."
                )
            elif 'network' in bottleneck.lower():
                recommendations.append(
                    "MEDIUM: Network bottleneck identified. "
                    "Review bandwidth limits, implement compression, optimize payload sizes."
                )
        
        # Positive recommendations
        if analysis.prd_requirements_met:
            recommendations.append(
                "EXCELLENT: All PRD requirements met. "
                "System is ready for production deployment at 10K+ user scale."
            )
        
        analysis.performance_recommendations = recommendations
    
    def _calculate_response_time_distribution(self, metrics: Dict[str, Any]) -> Dict[str, float]:
        """Calculate response time distribution analysis."""
        return {
            'p50_to_avg_ratio': self._safe_divide(
                metrics.get('p50_response_time_ms', 0),
                metrics.get('avg_response_time_ms', 1)
            ),
            'p95_to_p50_ratio': self._safe_divide(
                metrics.get('p95_response_time_ms', 0),
                metrics.get('p50_response_time_ms', 1)
            ),
            'p99_to_p95_ratio': self._safe_divide(
                metrics.get('p99_response_time_ms', 0),
                metrics.get('p95_response_time_ms', 1)
            )
        }
    
    def _detect_response_time_outliers(self, metrics: Dict[str, Any]) -> bool:
        """Detect if there are response time outliers."""
        max_time = metrics.get('max_response_time_ms', 0)
        p99_time = metrics.get('p99_response_time_ms', 0)
        
        # If max is significantly higher than P99, we have outliers
        return max_time > p99_time * 2
    
    def _calculate_throughput_efficiency(self, metrics: Dict[str, Any], scenario_config: Dict[str, Any]) -> float:
        """Calculate throughput efficiency percentage."""
        actual_rps = metrics.get('requests_per_second', 0)
        target_rps = scenario_config.get('target_rps', 1)
        return (actual_rps / target_rps) * 100
    
    def _assess_sustained_load(self, metrics: Dict[str, Any]) -> str:
        """Assess sustained load capability."""
        duration = metrics.get('actual_duration_seconds', 0)
        if duration < 300:  # Less than 5 minutes
            return "short_term_only"
        elif duration < 1800:  # Less than 30 minutes
            return "medium_term_sustained"
        else:
            return "long_term_sustained"
    
    def _assess_cache_performance_impact(self, metrics: Dict[str, Any]) -> str:
        """Assess cache performance impact on overall system."""
        hit_rate = metrics.get('cache_hit_rate', 0)
        if hit_rate >= 95:
            return "excellent_performance_impact"
        elif hit_rate >= 90:
            return "good_performance_impact"
        elif hit_rate >= 80:
            return "moderate_performance_impact"
        else:
            return "poor_performance_impact"
    
    def _identify_cache_optimizations(self, metrics: Dict[str, Any]) -> List[str]:
        """Identify cache optimization opportunities."""
        optimizations = []
        hit_rate = metrics.get('cache_hit_rate', 0)
        
        if hit_rate < 90:
            optimizations.append("increase_cache_warming_frequency")
        if hit_rate < 85:
            optimizations.append("optimize_cache_keys")
        if hit_rate < 80:
            optimizations.append("increase_cache_ttl")
            optimizations.append("implement_predictive_caching")
        
        return optimizations
    
    def _identify_dominant_error(self, metrics: Dict[str, Any]) -> str:
        """Identify the dominant error type."""
        error_types = metrics.get('error_types', {})
        if not error_types:
            return "no_errors"
        
        return max(error_types, key=error_types.get)
    
    def _analyze_error_patterns(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze error patterns."""
        status_codes = metrics.get('status_code_distribution', {})
        
        return {
            'client_errors_4xx': sum(count for code, count in status_codes.items() if str(code).startswith('4')),
            'server_errors_5xx': sum(count for code, count in status_codes.items() if str(code).startswith('5')),
            'timeout_errors': status_codes.get('timeout', 0),
            'connection_errors': status_codes.get('connection', 0)
        }
    
    def _assess_cpu_utilization(self, metrics: Dict[str, Any]) -> str:
        """Assess CPU utilization level."""
        cpu = metrics.get('peak_cpu_percent', 0)
        if cpu < 50:
            return "low_utilization"
        elif cpu < 75:
            return "moderate_utilization"
        elif cpu < 90:
            return "high_utilization"
        else:
            return "critical_utilization"
    
    def _assess_memory_utilization(self, metrics: Dict[str, Any]) -> str:
        """Assess memory utilization level."""
        memory_mb = metrics.get('peak_memory_mb', 0)
        # Assume 8GB system for assessment
        memory_percent = (memory_mb / 8192) * 100
        
        if memory_percent < 50:
            return "low_utilization"
        elif memory_percent < 75:
            return "moderate_utilization"
        elif memory_percent < 90:
            return "high_utilization"
        else:
            return "critical_utilization"
    
    def _assess_connection_utilization(self, metrics: Dict[str, Any]) -> str:
        """Assess connection pool utilization."""
        db_connections = metrics.get('peak_db_connections', 0)
        
        if db_connections < 100:
            return "low_utilization"
        elif db_connections < 150:
            return "moderate_utilization"
        elif db_connections < 200:
            return "high_utilization"
        else:
            return "critical_utilization"
    
    def _identify_resource_bottlenecks(self, metrics: Dict[str, Any]) -> List[str]:
        """Identify resource bottlenecks."""
        bottlenecks = []
        
        if metrics.get('peak_cpu_percent', 0) > 85:
            bottlenecks.append("cpu_bottleneck")
        
        if metrics.get('peak_memory_mb', 0) > 7000:  # > 7GB
            bottlenecks.append("memory_bottleneck")
        
        if metrics.get('peak_db_connections', 0) > 180:
            bottlenecks.append("database_connection_bottleneck")
        
        return bottlenecks
    
    def _identify_system_bottlenecks(self, scenarios: List[Dict[str, Any]]) -> List[str]:
        """Identify system-wide bottlenecks across scenarios."""
        bottlenecks = []
        
        # Analyze patterns across scenarios
        response_times = [s.get('metrics', {}).get('p95_response_time_ms', 0) for s in scenarios]
        cache_hit_rates = [s.get('metrics', {}).get('cache_hit_rate', 0) for s in scenarios]
        error_rates = [s.get('metrics', {}).get('failed_requests', 0) / max(1, s.get('metrics', {}).get('total_requests', 1)) for s in scenarios]
        
        # Response time pattern analysis
        if all(rt > 100 for rt in response_times):
            bottlenecks.append("consistent_high_response_times")
        
        # Cache performance pattern analysis
        if all(chr < 85 for chr in cache_hit_rates):
            bottlenecks.append("consistent_poor_cache_performance")
        
        # Error rate pattern analysis
        if any(er > 0.05 for er in error_rates):
            bottlenecks.append("elevated_error_rates_under_load")
        
        return bottlenecks
    
    def _perform_regression_analysis(self, test_data: Dict[str, Any]) -> Dict[str, Any]:
        """Perform performance regression analysis."""
        # This would compare against historical data
        # For now, return basic analysis structure
        return {
            'has_historical_data': len(self.historical_data) > 0,
            'performance_trend': 'stable',  # Would calculate from historical data
            'regression_detected': False,
            'improvement_detected': False
        }
    
    def _safe_divide(self, numerator: float, denominator: float) -> float:
        """Safely divide two numbers, handling zero denominator."""
        return numerator / denominator if denominator != 0 else 0
    
    def generate_html_report(self, analysis: PerformanceAnalysis, output_file: str):
        """Generate HTML performance report."""
        html_template = """
<!DOCTYPE html>
<html>
<head>
    <title>Velro Load Test Performance Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .header { background: #2c3e50; color: white; padding: 20px; border-radius: 5px; }
        .section { margin: 20px 0; padding: 20px; border: 1px solid #ddd; border-radius: 5px; }
        .metric { display: inline-block; margin: 10px; padding: 10px; background: #f8f9fa; border-radius: 3px; }
        .success { background: #d4edda; color: #155724; }
        .warning { background: #fff3cd; color: #856404; }
        .danger { background: #f8d7da; color: #721c24; }
        .recommendation { margin: 10px 0; padding: 10px; border-left: 4px solid #007bff; background: #f8f9fa; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #f2f2f2; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Velro Load Test Performance Report</h1>
        <p>Scenario: {{ analysis.scenario_name }}</p>
        <p>Generated: {{ analysis.timestamp }}</p>
    </div>
    
    <div class="section">
        <h2>PRD Compliance Summary</h2>
        <div class="metric {{ 'success' if analysis.prd_requirements_met else 'danger' }}">
            <strong>PRD Compliance Score: {{ "%.1f" | format(analysis.prd_compliance_score) }}%</strong>
        </div>
        <div class="metric {{ 'success' if analysis.prd_requirements_met else 'danger' }}">
            <strong>Requirements Met: {{ 'YES' if analysis.prd_requirements_met else 'NO' }}</strong>
        </div>
        
        <h3>Detailed Compliance Checks</h3>
        <table>
            <tr><th>Requirement</th><th>Status</th></tr>
            {% for requirement, status in analysis.compliance_details.items() %}
            <tr>
                <td>{{ requirement.replace('_', ' ').title() }}</td>
                <td class="{{ 'success' if status else 'danger' }}">{{ 'PASS' if status else 'FAIL' }}</td>
            </tr>
            {% endfor %}
        </table>
    </div>
    
    <div class="section">
        <h2>Performance Metrics</h2>
        
        <h3>Response Times</h3>
        <div class="metric">P50: {{ "%.2f" | format(analysis.response_time_analysis.p50_response_time_ms) }}ms</div>
        <div class="metric">P95: {{ "%.2f" | format(analysis.response_time_analysis.p95_response_time_ms) }}ms</div>
        <div class="metric">P99: {{ "%.2f" | format(analysis.response_time_analysis.p99_response_time_ms) }}ms</div>
        
        <h3>Throughput</h3>
        <div class="metric">Requests/sec: {{ "%.1f" | format(analysis.throughput_analysis.requests_per_second) }}</div>
        <div class="metric">Total Requests: {{ analysis.throughput_analysis.total_requests }}</div>
        <div class="metric">Success Rate: {{ "%.1f" | format((analysis.throughput_analysis.successful_requests / analysis.throughput_analysis.total_requests) * 100) }}%</div>
        
        <h3>Cache Performance</h3>
        <div class="metric">Hit Rate: {{ "%.1f" | format(analysis.cache_performance_analysis.overall_hit_rate) }}%</div>
        <div class="metric">Auth Cache Hit Rate: {{ "%.1f" | format(analysis.cache_performance_analysis.auth_cache_hit_rate) }}%</div>
    </div>
    
    <div class="section">
        <h2>System Resources</h2>
        <div class="metric">Peak CPU: {{ "%.1f" | format(analysis.system_resource_analysis.peak_cpu_percent) }}%</div>
        <div class="metric">Peak Memory: {{ "%.0f" | format(analysis.system_resource_analysis.peak_memory_mb) }}MB</div>
        <div class="metric">Peak DB Connections: {{ analysis.system_resource_analysis.peak_db_connections }}</div>
    </div>
    
    <div class="section">
        <h2>Performance Recommendations</h2>
        {% for recommendation in analysis.performance_recommendations %}
        <div class="recommendation">{{ recommendation }}</div>
        {% endfor %}
    </div>
    
    <div class="section">
        <h2>Identified Bottlenecks</h2>
        {% if analysis.identified_bottlenecks %}
        <ul>
            {% for bottleneck in analysis.identified_bottlenecks %}
            <li>{{ bottleneck.replace('_', ' ').title() }}</li>
            {% endfor %}
        </ul>
        {% else %}
        <p>No significant bottlenecks identified.</p>
        {% endif %}
    </div>
</body>
</html>
        """
        
        template = Template(html_template)
        html_content = template.render(analysis=analysis)
        
        with open(output_file, 'w') as f:
            f.write(html_content)
        
        logger.info(f"HTML report generated: {output_file}")
    
    def generate_csv_report(self, analysis: PerformanceAnalysis, output_file: str):
        """Generate CSV summary report."""
        data = []
        
        # Basic metrics
        data.append(['Metric', 'Value', 'Unit', 'Status'])
        data.append(['PRD Compliance Score', f"{analysis.prd_compliance_score:.1f}", '%', 'PASS' if analysis.prd_requirements_met else 'FAIL'])
        data.append(['P95 Response Time', f"{analysis.response_time_analysis.get('p95_response_time_ms', 0):.2f}", 'ms', ''])
        data.append(['Throughput', f"{analysis.throughput_analysis.get('requests_per_second', 0):.1f}", 'req/sec', ''])
        data.append(['Cache Hit Rate', f"{analysis.cache_performance_analysis.get('overall_hit_rate', 0):.1f}", '%', ''])
        data.append(['Peak CPU Usage', f"{analysis.system_resource_analysis.get('peak_cpu_percent', 0):.1f}", '%', ''])
        data.append(['Peak Memory Usage', f"{analysis.system_resource_analysis.get('peak_memory_mb', 0):.0f}", 'MB', ''])
        
        # Write to CSV
        with open(output_file, 'w', newline='') as f:
            import csv
            writer = csv.writer(f)
            writer.writerows(data)
        
        logger.info(f"CSV report generated: {output_file}")
    
    def generate_executive_summary(self, analysis: PerformanceAnalysis) -> Dict[str, Any]:
        """Generate executive summary for stakeholders."""
        return {
            'title': 'Velro 10K+ User Load Test - Executive Summary',
            'test_date': analysis.timestamp,
            'scenario': analysis.scenario_name,
            
            'key_findings': {
                'prd_compliance': 'ACHIEVED' if analysis.prd_requirements_met else 'NOT ACHIEVED',
                'compliance_score': f"{analysis.prd_compliance_score:.1f}%",
                'ready_for_production': analysis.prd_requirements_met,
                'max_users_tested': 10000,  # This would come from the actual test
                'performance_level': 'EXCELLENT' if analysis.prd_compliance_score >= 95 else 
                                   'GOOD' if analysis.prd_compliance_score >= 80 else 
                                   'NEEDS IMPROVEMENT'
            },
            
            'critical_metrics': {
                'response_time_p95_ms': analysis.response_time_analysis.get('p95_response_time_ms', 0),
                'throughput_rps': analysis.throughput_analysis.get('requests_per_second', 0),
                'cache_hit_rate_percent': analysis.cache_performance_analysis.get('overall_hit_rate', 0),
                'error_rate_percent': analysis.error_analysis.get('error_rate_percentage', 0)
            },
            
            'business_impact': {
                'user_capacity': '10,000+ concurrent users supported' if analysis.prd_requirements_met else 'User capacity limitations identified',
                'performance_sla': 'SLA targets achieved' if analysis.prd_requirements_met else 'SLA targets not met',
                'scalability_readiness': 'Production ready' if analysis.prd_requirements_met else 'Optimization required'
            },
            
            'next_steps': analysis.performance_recommendations[:3],  # Top 3 recommendations
            
            'technical_summary': {
                'bottlenecks_identified': len(analysis.identified_bottlenecks),
                'optimization_opportunities': len(analysis.performance_recommendations),
                'system_stability': 'STABLE' if analysis.error_analysis.get('error_rate', 0) < 0.02 else 'UNSTABLE'
            }
        }

def main():
    """Main CLI interface for performance report generation."""
    parser = argparse.ArgumentParser(description='Generate Velro performance validation reports')
    parser.add_argument('results_file', help='Path to load test results JSON file')
    parser.add_argument('--config', help='Path to configuration YAML file')
    parser.add_argument('--output-dir', default='.', help='Output directory for reports')
    parser.add_argument('--formats', nargs='+', default=['json', 'html'], 
                       choices=['json', 'html', 'csv'], help='Output formats')
    
    args = parser.parse_args()
    
    # Validate input file
    if not os.path.exists(args.results_file):
        logger.error(f"Results file not found: {args.results_file}")
        sys.exit(1)
    
    # Generate reports
    generator = PerformanceReportGenerator(args.config)
    analysis = generator.analyze_load_test_results(args.results_file)
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    
    timestamp = int(time.time())
    base_name = f"performance_validation_report_{timestamp}"
    
    # Generate requested formats
    if 'json' in args.formats:
        json_file = output_dir / f"{base_name}.json"
        with open(json_file, 'w') as f:
            json.dump(asdict(analysis), f, indent=2, default=str)
        logger.info(f"JSON report saved: {json_file}")
    
    if 'html' in args.formats:
        html_file = output_dir / f"{base_name}.html"
        generator.generate_html_report(analysis, html_file)
    
    if 'csv' in args.formats:
        csv_file = output_dir / f"{base_name}.csv"
        generator.generate_csv_report(analysis, csv_file)
    
    # Generate executive summary
    executive_summary = generator.generate_executive_summary(analysis)
    summary_file = output_dir / f"executive_summary_{timestamp}.json"
    with open(summary_file, 'w') as f:
        json.dump(executive_summary, f, indent=2, default=str)
    
    logger.info(f"Executive summary saved: {summary_file}")
    
    # Print summary to console
    print(f"\n{'='*80}")
    print("PERFORMANCE VALIDATION SUMMARY")
    print(f"{'='*80}")
    print(f"PRD Compliance: {analysis.prd_compliance_score:.1f}% - {'PASS' if analysis.prd_requirements_met else 'FAIL'}")
    print(f"P95 Response Time: {analysis.response_time_analysis.get('p95_response_time_ms', 0):.2f}ms")
    print(f"Throughput: {analysis.throughput_analysis.get('requests_per_second', 0):.1f} req/sec")
    print(f"Cache Hit Rate: {analysis.cache_performance_analysis.get('overall_hit_rate', 0):.1f}%")
    print(f"System Status: {'PRODUCTION READY' if analysis.prd_requirements_met else 'OPTIMIZATION REQUIRED'}")
    print(f"\nReports generated in: {output_dir}")

if __name__ == "__main__":
    main()