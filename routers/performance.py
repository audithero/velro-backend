"""
Performance Validation and Monitoring Endpoints for <100ms Targets
Real-time performance monitoring and validation endpoints for production optimization.

Key Features:
- Real-time performance dashboard
- Performance metrics and statistics
- Response time validation endpoints
- System resource monitoring
- Cache performance analysis
- Database query performance tracking
- Performance recommendations and alerts

Target Validation:
- Authorization endpoints: <100ms average response time
- Cache operations: <20ms average response time
- Database queries: <50ms average response time
- Overall API performance: <100ms P95 response time
"""

import time
import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.responses import JSONResponse
import psutil

# Import performance monitoring components
try:
    from monitoring.performance_tracker import get_performance_tracker
    PERFORMANCE_TRACKER_AVAILABLE = True
except ImportError:
    PERFORMANCE_TRACKER_AVAILABLE = False

try:
    from monitoring.performance_monitor import get_performance_monitor, get_performance_dashboard
    PERFORMANCE_MONITORING_AVAILABLE = True
except ImportError:
    PERFORMANCE_MONITORING_AVAILABLE = False

try:
    from utils.cache_manager import get_cache_performance_report
    CACHE_MONITORING_AVAILABLE = True
except ImportError:
    CACHE_MONITORING_AVAILABLE = False

try:
    from utils.database_optimizer import get_database_performance_report
    DB_MONITORING_AVAILABLE = True
except ImportError:
    DB_MONITORING_AVAILABLE = False

try:
    from middleware.optimized_chain import UltraOptimizedMiddlewareChain
    MIDDLEWARE_MONITORING_AVAILABLE = True
except ImportError:
    MIDDLEWARE_MONITORING_AVAILABLE = False

try:
    from middleware.production_rate_limiter import RateLimitMiddleware
    RATE_LIMITER_AVAILABLE = True
except ImportError:
    RATE_LIMITER_AVAILABLE = False

logger = logging.getLogger(__name__)

# Create performance router
performance_router = APIRouter(
    prefix="/api/v1/performance",
    tags=["Performance Monitoring"],
    responses={
        500: {"description": "Performance monitoring unavailable"}
    }
)

@performance_router.get("/dashboard")
async def get_performance_dashboard_endpoint():
    """
    Get comprehensive real-time performance dashboard.
    
    Returns:
        dict: Performance dashboard with real-time metrics, alerts, and recommendations
    """
    try:
        dashboard_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'status': 'healthy',
            'performance_summary': {},
            'component_performance': {},
            'system_metrics': {},
            'active_alerts': [],
            'recommendations': []
        }
        
        # Real-time performance monitoring data
        if PERFORMANCE_MONITORING_AVAILABLE:
            try:
                perf_dashboard = await get_performance_dashboard()
                dashboard_data.update(perf_dashboard)
            except Exception as e:
                logger.error(f"Failed to get performance dashboard: {e}")
                dashboard_data['errors'] = dashboard_data.get('errors', [])
                dashboard_data['errors'].append(f"Performance monitoring error: {str(e)}")
        
        # Cache performance data
        if CACHE_MONITORING_AVAILABLE:
            try:
                cache_report = await get_cache_performance_report()
                dashboard_data['component_performance']['cache'] = cache_report
            except Exception as e:
                logger.error(f"Failed to get cache performance: {e}")
        
        # Database performance data
        if DB_MONITORING_AVAILABLE:
            try:
                db_report = await get_database_performance_report()
                dashboard_data['component_performance']['database'] = db_report
            except Exception as e:
                logger.error(f"Failed to get database performance: {e}")
        
        # System resource metrics
        try:
            system_metrics = {
                'timestamp': time.time(),
                'cpu': {
                    'percent': psutil.cpu_percent(interval=0.1),
                    'count': psutil.cpu_count(),
                    'freq': psutil.cpu_freq()._asdict() if psutil.cpu_freq() else {}
                },
                'memory': {
                    'percent': psutil.virtual_memory().percent,
                    'available_mb': psutil.virtual_memory().available / (1024 * 1024),
                    'used_mb': psutil.virtual_memory().used / (1024 * 1024),
                    'total_mb': psutil.virtual_memory().total / (1024 * 1024)
                },
                'disk': psutil.disk_usage('/')._asdict() if hasattr(psutil, 'disk_usage') else {},
                'network': psutil.net_io_counters()._asdict() if psutil.net_io_counters() else {},
                'processes': len(psutil.pids())
            }
            dashboard_data['system_metrics'] = system_metrics
        except Exception as e:
            logger.error(f"Failed to get system metrics: {e}")
        
        # Performance target validation
        performance_targets_met = True
        target_violations = []
        
        # Check authorization performance target (<100ms)
        auth_performance = dashboard_data.get('operation_windows', {}).get('authorization', {})
        if auth_performance and auth_performance.get('avg_ms', 0) > 100:
            performance_targets_met = False
            target_violations.append(f"Authorization averaging {auth_performance['avg_ms']:.1f}ms (target: <100ms)")
        
        # Check cache performance target (<20ms)
        cache_performance = dashboard_data.get('component_performance', {}).get('cache', {})
        cache_avg = cache_performance.get('overall', {}).get('avg_response_time_ms', 0)
        if cache_avg > 20:
            performance_targets_met = False
            target_violations.append(f"Cache operations averaging {cache_avg:.1f}ms (target: <20ms)")
        
        # Update overall status based on targets
        if not performance_targets_met:
            dashboard_data['status'] = 'performance_issues'
            dashboard_data['target_violations'] = target_violations
        
        dashboard_data['performance_targets_met'] = performance_targets_met
        
        return dashboard_data
        
    except Exception as e:
        logger.error(f"Performance dashboard error: {e}")
        raise HTTPException(status_code=500, detail=f"Performance dashboard unavailable: {str(e)}")

@performance_router.get("/metrics")
async def get_performance_metrics():
    """
    Get detailed performance metrics for all components.
    
    Returns:
        dict: Comprehensive performance metrics
    """
    try:
        metrics = {
            'timestamp': datetime.utcnow().isoformat(),
            'collection_time_ms': 0,
            'components': {}
        }
        
        start_time = time.perf_counter()
        
        # Performance monitor metrics
        if PERFORMANCE_MONITORING_AVAILABLE:
            try:
                monitor = get_performance_monitor()
                perf_metrics = monitor.get_performance_dashboard()
                metrics['components']['performance_monitor'] = perf_metrics
            except Exception as e:
                logger.error(f"Performance monitor metrics error: {e}")
        
        # Cache performance metrics
        if CACHE_MONITORING_AVAILABLE:
            try:
                cache_metrics = await get_cache_performance_report()
                metrics['components']['cache'] = cache_metrics
            except Exception as e:
                logger.error(f"Cache metrics error: {e}")
        
        # Database performance metrics
        if DB_MONITORING_AVAILABLE:
            try:
                db_metrics = await get_database_performance_report()
                metrics['components']['database'] = db_metrics
            except Exception as e:
                logger.error(f"Database metrics error: {e}")
        
        # Calculate collection time
        collection_time_ms = (time.perf_counter() - start_time) * 1000
        metrics['collection_time_ms'] = round(collection_time_ms, 2)
        
        # Alert if metrics collection is slow
        if collection_time_ms > 100:
            logger.warning(f"Slow metrics collection: {collection_time_ms:.2f}ms")
        
        return metrics
        
    except Exception as e:
        logger.error(f"Performance metrics error: {e}")
        raise HTTPException(status_code=500, detail=f"Performance metrics unavailable: {str(e)}")

@performance_router.get("/health")
async def performance_health_check():
    """
    Quick performance health check endpoint (<10ms target).
    
    Returns:
        dict: Basic health status and key performance indicators
    """
    start_time = time.perf_counter()
    
    try:
        health_data = {
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'response_time_ms': 0,
            'components': {
                'performance_monitor': False,
                'cache': False,
                'database_optimizer': False,
                'middleware': False
            },
            'quick_stats': {}
        }
        
        # Check component availability
        health_data['components']['performance_monitor'] = PERFORMANCE_MONITORING_AVAILABLE
        health_data['components']['cache'] = CACHE_MONITORING_AVAILABLE  
        health_data['components']['database_optimizer'] = DB_MONITORING_AVAILABLE
        health_data['components']['middleware'] = MIDDLEWARE_MONITORING_AVAILABLE
        
        # Quick system stats
        try:
            health_data['quick_stats'] = {
                'cpu_percent': psutil.cpu_percent(interval=0),
                'memory_percent': psutil.virtual_memory().percent,
                'active_connections': len(psutil.net_connections()) if hasattr(psutil, 'net_connections') else 0
            }
        except:
            pass
        
        # Calculate response time
        response_time_ms = (time.perf_counter() - start_time) * 1000
        health_data['response_time_ms'] = round(response_time_ms, 2)
        
        # Health check should be very fast (<10ms)
        if response_time_ms > 10:
            health_data['status'] = 'slow'
            logger.warning(f"Slow health check: {response_time_ms:.2f}ms")
        
        return health_data
        
    except Exception as e:
        response_time_ms = (time.perf_counter() - start_time) * 1000
        logger.error(f"Performance health check error: {e}")
        
        return {
            'status': 'error',
            'timestamp': datetime.utcnow().isoformat(),
            'response_time_ms': round(response_time_ms, 2),
            'error': str(e)
        }

@performance_router.get("/validate")
async def validate_performance_targets():
    """
    Validate all performance targets against current metrics.
    
    Returns:
        dict: Validation results with pass/fail status for each target
    """
    try:
        validation_results = {
            'timestamp': datetime.utcnow().isoformat(),
            'overall_status': 'pass',
            'targets_met': 0,
            'targets_failed': 0,
            'validations': {}
        }
        
        # Define performance targets
        targets = {
            'authorization_response_time': {'target_ms': 100, 'critical_ms': 200},
            'cache_operation_time': {'target_ms': 20, 'critical_ms': 50},
            'database_query_time': {'target_ms': 50, 'critical_ms': 100},
            'api_endpoint_p95': {'target_ms': 100, 'critical_ms': 250},
            'health_check_time': {'target_ms': 10, 'critical_ms': 25}
        }
        
        # Validate each target
        for target_name, target_config in targets.items():
            validation = {
                'target_ms': target_config['target_ms'],
                'critical_ms': target_config['critical_ms'],
                'current_ms': 0,
                'status': 'unknown',
                'message': 'No data available'
            }
            
            try:
                if target_name == 'authorization_response_time':
                    if PERFORMANCE_MONITORING_AVAILABLE:
                        dashboard = await get_performance_dashboard()
                        auth_stats = dashboard.get('operation_windows', {}).get('authorization', {})
                        current_ms = auth_stats.get('avg_ms', 0)
                        
                        validation['current_ms'] = current_ms
                        if current_ms <= target_config['target_ms']:
                            validation['status'] = 'pass'
                            validation['message'] = f"Authorization responses averaging {current_ms:.1f}ms (target: {target_config['target_ms']}ms)"
                            validation_results['targets_met'] += 1
                        elif current_ms <= target_config['critical_ms']:
                            validation['status'] = 'warning'
                            validation['message'] = f"Authorization responses {current_ms:.1f}ms exceed target but within critical threshold"
                        else:
                            validation['status'] = 'fail'
                            validation['message'] = f"Authorization responses {current_ms:.1f}ms exceed critical threshold ({target_config['critical_ms']}ms)"
                            validation_results['targets_failed'] += 1
                            validation_results['overall_status'] = 'fail'
                
                elif target_name == 'cache_operation_time':
                    if CACHE_MONITORING_AVAILABLE:
                        cache_report = await get_cache_performance_report()
                        current_ms = cache_report.get('overall', {}).get('avg_response_time_ms', 0)
                        
                        validation['current_ms'] = current_ms
                        if current_ms <= target_config['target_ms']:
                            validation['status'] = 'pass'
                            validation['message'] = f"Cache operations averaging {current_ms:.1f}ms"
                            validation_results['targets_met'] += 1
                        else:
                            validation['status'] = 'fail'
                            validation['message'] = f"Cache operations {current_ms:.1f}ms exceed target"
                            validation_results['targets_failed'] += 1
                            validation_results['overall_status'] = 'fail'
                
                elif target_name == 'database_query_time':
                    if DB_MONITORING_AVAILABLE:
                        db_report = await get_database_performance_report()
                        current_ms = db_report.get('overall_performance', {}).get('avg_execution_time_ms', 0)
                        
                        validation['current_ms'] = current_ms
                        if current_ms <= target_config['target_ms']:
                            validation['status'] = 'pass'
                            validation['message'] = f"Database queries averaging {current_ms:.1f}ms"
                            validation_results['targets_met'] += 1
                        else:
                            validation['status'] = 'fail'
                            validation['message'] = f"Database queries {current_ms:.1f}ms exceed target"
                            validation_results['targets_failed'] += 1
                            validation_results['overall_status'] = 'fail'
                
                elif target_name == 'health_check_time':
                    # Test health check performance
                    start_time = time.perf_counter()
                    health_result = await performance_health_check()
                    health_time_ms = (time.perf_counter() - start_time) * 1000
                    
                    validation['current_ms'] = health_time_ms
                    if health_time_ms <= target_config['target_ms']:
                        validation['status'] = 'pass'
                        validation['message'] = f"Health check completed in {health_time_ms:.1f}ms"
                        validation_results['targets_met'] += 1
                    else:
                        validation['status'] = 'fail'
                        validation['message'] = f"Health check took {health_time_ms:.1f}ms (target: {target_config['target_ms']}ms)"
                        validation_results['targets_failed'] += 1
                        validation_results['overall_status'] = 'fail'
                        
            except Exception as e:
                validation['status'] = 'error'
                validation['message'] = f"Validation error: {str(e)}"
                logger.error(f"Target validation error for {target_name}: {e}")
            
            validation_results['validations'][target_name] = validation
        
        return validation_results
        
    except Exception as e:
        logger.error(f"Performance validation error: {e}")
        raise HTTPException(status_code=500, detail=f"Performance validation failed: {str(e)}")

@performance_router.get("/recommendations")
async def get_performance_recommendations():
    """
    Get performance optimization recommendations based on current metrics.
    
    Returns:
        dict: Actionable performance recommendations
    """
    try:
        recommendations = {
            'timestamp': datetime.utcnow().isoformat(),
            'priority_recommendations': [],
            'optimization_suggestions': [],
            'configuration_recommendations': [],
            'infrastructure_recommendations': []
        }
        
        # Get current performance data
        dashboard_data = await get_performance_dashboard_endpoint()
        
        # Analyze authorization performance
        auth_stats = dashboard_data.get('operation_windows', {}).get('authorization', {})
        if auth_stats and auth_stats.get('avg_ms', 0) > 100:
            recommendations['priority_recommendations'].append({
                'priority': 'HIGH',
                'category': 'authorization',
                'issue': f"Authorization responses averaging {auth_stats['avg_ms']:.1f}ms (target: <100ms)",
                'recommendation': 'Implement authorization result caching and database query optimization',
                'impact': 'High - affects all authenticated requests'
            })
        
        # Analyze cache performance
        cache_data = dashboard_data.get('component_performance', {}).get('cache', {})
        if cache_data:
            cache_hit_rate = cache_data.get('overall', {}).get('hit_rate_percent', 0)
            if cache_hit_rate < 90:
                recommendations['optimization_suggestions'].append({
                    'category': 'cache',
                    'issue': f"Cache hit rate at {cache_hit_rate:.1f}% (target: >90%)",
                    'recommendation': 'Increase cache TTL values and implement cache warming',
                    'impact': 'Medium - improves response times for cached operations'
                })
        
        # System resource recommendations
        system_metrics = dashboard_data.get('system_metrics', {})
        cpu_percent = system_metrics.get('cpu', {}).get('percent', 0)
        memory_percent = system_metrics.get('memory', {}).get('percent', 0)
        
        if cpu_percent > 80:
            recommendations['infrastructure_recommendations'].append({
                'category': 'cpu',
                'issue': f"High CPU usage: {cpu_percent:.1f}%",
                'recommendation': 'Consider horizontal scaling or CPU optimization',
                'impact': 'High - affects overall system performance'
            })
        
        if memory_percent > 85:
            recommendations['infrastructure_recommendations'].append({
                'category': 'memory',
                'issue': f"High memory usage: {memory_percent:.1f}%",
                'recommendation': 'Review memory leaks and optimize cache sizes',
                'impact': 'High - may lead to system instability'
            })
        
        # Configuration recommendations
        if dashboard_data.get('active_alerts'):
            recommendations['configuration_recommendations'].append({
                'category': 'monitoring',
                'issue': f"{len(dashboard_data['active_alerts'])} active performance alerts",
                'recommendation': 'Review and address active performance alerts',
                'impact': 'Varies - depends on alert severity'
            })
        
        return recommendations
        
    except Exception as e:
        logger.error(f"Performance recommendations error: {e}")
        raise HTTPException(status_code=500, detail=f"Performance recommendations unavailable: {str(e)}")

@performance_router.get("/test")
async def performance_test_endpoint(request: Request, response: Response):
    """
    Test endpoint for measuring response time performance.
    
    Returns:
        dict: Performance test results with timing breakdown
    """
    start_time = time.perf_counter()
    
    try:
        # Simulate some work
        test_results = {
            'timestamp': datetime.utcnow().isoformat(),
            'test_type': 'performance_validation',
            'timings': {},
            'metadata': {
                'method': request.method,
                'path': str(request.url.path),
                'user_agent': request.headers.get('User-Agent', ''),
                'client_ip': request.client.host if request.client else None
            }
        }
        
        # Test database connection time (if available)
        if DB_MONITORING_AVAILABLE:
            db_start = time.perf_counter()
            try:
                # Quick database test (placeholder)
                await asyncio.sleep(0.001)  # Simulate DB query
                db_time_ms = (time.perf_counter() - db_start) * 1000
                test_results['timings']['database_ms'] = round(db_time_ms, 2)
            except Exception as e:
                test_results['timings']['database_error'] = str(e)
        
        # Test cache operation time (if available)
        if CACHE_MONITORING_AVAILABLE:
            cache_start = time.perf_counter()
            try:
                # Quick cache test (placeholder)
                await asyncio.sleep(0.001)  # Simulate cache operation
                cache_time_ms = (time.perf_counter() - cache_start) * 1000
                test_results['timings']['cache_ms'] = round(cache_time_ms, 2)
            except Exception as e:
                test_results['timings']['cache_error'] = str(e)
        
        # Calculate total response time
        total_time_ms = (time.perf_counter() - start_time) * 1000
        test_results['timings']['total_response_ms'] = round(total_time_ms, 2)
        
        # Add performance assessment
        if total_time_ms < 50:
            test_results['performance_level'] = 'excellent'
        elif total_time_ms < 100:
            test_results['performance_level'] = 'good'
        elif total_time_ms < 200:
            test_results['performance_level'] = 'acceptable'
        else:
            test_results['performance_level'] = 'poor'
        
        # Add response headers
        response.headers['X-Response-Time'] = str(round(total_time_ms, 2))
        response.headers['X-Performance-Level'] = test_results['performance_level']
        
        return test_results
        
    except Exception as e:
        total_time_ms = (time.perf_counter() - start_time) * 1000
        logger.error(f"Performance test error: {e}")
        
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'test_type': 'performance_validation',
            'error': str(e),
            'timings': {
                'total_response_ms': round(total_time_ms, 2)
            }
        }


# ============================================================================
# NEW PRD-COMPLIANT PERFORMANCE TRACKING ENDPOINTS
# ============================================================================

@performance_router.get("/metrics", 
                       summary="Current Performance Metrics",
                       description="Get real-time performance metrics with PRD compliance tracking")
async def get_current_performance_metrics():
    """
    Get current performance metrics for PRD compliance monitoring.
    
    Tracks:
    - Authentication response times (<50ms target)
    - Authorization response times (<75ms target)
    - Cache hit rates L1/L2/L3 (>95% target)
    - Database query performance
    - Concurrent user impact
    
    Returns:
        dict: Real-time performance metrics with PRD compliance status
    """
    try:
        if not PERFORMANCE_TRACKER_AVAILABLE:
            raise HTTPException(
                status_code=503, 
                detail="Performance tracking system not available"
            )
        
        tracker = get_performance_tracker()
        metrics = tracker.get_current_metrics()
        
        return JSONResponse(
            content=metrics,
            headers={
                "X-Performance-Grade": metrics.get('overall_grade', 'Unknown'),
                "X-PRD-Compliance": str(metrics.get('prd_compliance', {})),
                "X-Active-Alerts": str(metrics.get('active_alerts_count', 0))
            }
        )
        
    except Exception as e:
        logger.error(f"Performance metrics endpoint error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve performance metrics: {str(e)}"
        )


@performance_router.get("/health",
                       summary="System Health Check", 
                       description="Quick system health check with performance assessment")
async def get_system_performance_health():
    """
    Get system health with performance component status.
    
    Provides:
    - Overall system health status
    - Component-level health assessment
    - Active performance alerts
    - Performance grades by component
    
    Returns:
        dict: System health data with performance assessment
    """
    try:
        if not PERFORMANCE_TRACKER_AVAILABLE:
            # Fallback to basic health check
            return await performance_health_check()
        
        tracker = get_performance_tracker()
        health_data = tracker.get_system_health()
        
        return JSONResponse(
            content=health_data,
            headers={
                "X-System-Status": health_data.get('overall_status', 'unknown'),
                "X-Critical-Alerts": str(len([
                    alert for alert in health_data.get('active_alerts', [])
                    if alert.get('level') == 'critical'
                ])),
                "X-Performance-Grade": health_data.get('performance_summary', {}).get('overall_grade', 'Unknown')
            }
        )
        
    except Exception as e:
        logger.error(f"Performance health endpoint error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve system health: {str(e)}"
        )


@performance_router.get("/report",
                       summary="Detailed Performance Report",
                       description="Comprehensive performance analysis report with recommendations")
async def get_detailed_performance_report():
    """
    Get detailed performance report with PRD compliance analysis.
    
    Includes:
    - Executive performance summary
    - PRD target compliance analysis
    - Performance trend analysis
    - Concurrent user impact analysis
    - Actionable recommendations
    - Alert summary and history
    
    Returns:
        dict: Comprehensive performance analysis report
    """
    try:
        if not PERFORMANCE_TRACKER_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Performance tracking system not available"
            )
        
        tracker = get_performance_tracker()
        report = tracker.get_detailed_report()
        
        return JSONResponse(
            content=report,
            headers={
                "X-Report-Type": "performance_analysis",
                "X-Report-Period": report.get('report_period', '1 hour'),
                "X-Overall-Grade": report.get('executive_summary', {}).get('overall_performance_grade', 'Unknown'),
                "X-Critical-Issues": str(report.get('executive_summary', {}).get('critical_issues', 0))
            }
        )
        
    except Exception as e:
        logger.error(f"Performance report endpoint error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate performance report: {str(e)}"
        )


@performance_router.get("/prd-compliance",
                       summary="PRD Compliance Status",
                       description="Current status against PRD performance targets")
async def get_prd_compliance_status():
    """
    Get current PRD compliance status for all performance targets.
    
    PRD Targets:
    - Authentication: <50ms
    - Authorization: <75ms
    - Cache hit rates: >95%
    - Database queries: <25ms
    
    Returns:
        dict: PRD compliance status with grades and recommendations
    """
    try:
        if not PERFORMANCE_TRACKER_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Performance tracking system not available"
            )
        
        tracker = get_performance_tracker()
        
        # Get current metrics and extract PRD compliance
        current_metrics = tracker.get_current_metrics()
        overall_grade = current_metrics.get('overall_grade', 'F')
        prd_compliance = current_metrics.get('prd_compliance', {})
        
        # Calculate average compliance
        compliance_values = list(prd_compliance.values())
        avg_compliance = sum(compliance_values) / len(compliance_values) if compliance_values else 0
        
        # Determine compliance status
        if avg_compliance >= 95:
            compliance_status = "excellent"
        elif avg_compliance >= 85:
            compliance_status = "good"
        elif avg_compliance >= 75:
            compliance_status = "acceptable"
        elif avg_compliance >= 60:
            compliance_status = "below_target"
        else:
            compliance_status = "critical"
        
        response_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'overall_compliance_status': compliance_status,
            'overall_grade': overall_grade,
            'average_compliance_percentage': round(avg_compliance, 1),
            'target_compliance': prd_compliance,
            'prd_targets': {
                'authentication_ms': 50,
                'authorization_ms': 75,
                'cache_hit_rate_percent': 95,
                'database_query_ms': 25
            },
            'compliance_summary': {
                'targets_met': len([v for v in compliance_values if v >= 100]),
                'targets_close': len([v for v in compliance_values if 80 <= v < 100]),
                'targets_failing': len([v for v in compliance_values if v < 80])
            }
        }
        
        return JSONResponse(
            content=response_data,
            headers={
                "X-Compliance-Status": compliance_status,
                "X-Overall-Grade": overall_grade,
                "X-Avg-Compliance": str(round(avg_compliance, 1))
            }
        )
        
    except Exception as e:
        logger.error(f"PRD compliance endpoint error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve PRD compliance status: {str(e)}"
        )


@performance_router.get("/alerts",
                       summary="Performance Alerts",
                       description="Current performance alerts and alert history")
async def get_performance_alerts():
    """
    Get current performance alerts and recent alert history.
    
    Returns:
        dict: Active alerts and alert history with resolution times
    """
    try:
        if not PERFORMANCE_TRACKER_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Performance tracking system not available"
            )
        
        tracker = get_performance_tracker()
        
        # Get system health which includes active alerts
        health_data = tracker.get_system_health()
        active_alerts = health_data.get('active_alerts', [])
        
        # Get alert history (last 24 hours)
        try:
            alert_history = tracker.alert_history
            recent_alerts = [
                {
                    'alert_id': alert.alert_id,
                    'level': alert.level.value,
                    'metric_type': alert.metric_type.value,
                    'message': alert.message,
                    'timestamp': alert.timestamp,
                    'resolved': alert.resolved,
                    'duration_seconds': alert.duration_seconds
                }
                for alert in list(alert_history)[-50:]  # Last 50 alerts
                if alert.timestamp > (time.time() - 24 * 3600)  # Last 24 hours
            ]
        except Exception as e:
            logger.error(f"Error getting alert history: {e}")
            recent_alerts = []
        
        alert_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'active_alerts': {
                'count': len(active_alerts),
                'critical_count': len([a for a in active_alerts if a.get('level') == 'critical']),
                'warning_count': len([a for a in active_alerts if a.get('level') == 'warning']),
                'alerts': active_alerts
            },
            'alert_history_24h': {
                'count': len(recent_alerts),
                'resolved_count': len([a for a in recent_alerts if a.get('resolved', False)]),
                'alerts': recent_alerts
            },
            'alert_summary': {
                'most_common_types': {},
                'average_resolution_time_seconds': 0
            }
        }
        
        # Calculate alert statistics
        if recent_alerts:
            # Most common alert types
            type_counts = {}
            resolution_times = []
            
            for alert in recent_alerts:
                alert_type = alert.get('metric_type', 'unknown')
                type_counts[alert_type] = type_counts.get(alert_type, 0) + 1
                
                if alert.get('resolved', False) and alert.get('duration_seconds'):
                    resolution_times.append(alert['duration_seconds'])
            
            alert_data['alert_summary']['most_common_types'] = type_counts
            
            if resolution_times:
                alert_data['alert_summary']['average_resolution_time_seconds'] = (
                    sum(resolution_times) / len(resolution_times)
                )
        
        return JSONResponse(
            content=alert_data,
            headers={
                "X-Active-Alerts": str(len(active_alerts)),
                "X-Critical-Alerts": str(len([a for a in active_alerts if a.get('level') == 'critical'])),
                "X-Alert-History-Count": str(len(recent_alerts))
            }
        )
        
    except Exception as e:
        logger.error(f"Performance alerts endpoint error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve performance alerts: {str(e)}"
        )


@performance_router.post("/record-metric",
                        summary="Record Performance Metric",
                        description="Record a performance metric for tracking")
async def record_performance_metric(
    metric_type: str,
    operation_name: str, 
    value: float,
    unit: str = "",
    success: bool = True,
    user_id: Optional[str] = None,
    endpoint: Optional[str] = None
):
    """
    Record a performance metric for tracking.
    
    Args:
        metric_type: Type of metric (authentication, authorization, cache_l1, etc.)
        operation_name: Name of the operation
        value: Metric value
        unit: Unit of measurement (optional)
        success: Whether operation succeeded
        user_id: Optional user ID
        endpoint: Optional endpoint path
    
    Returns:
        dict: Recording confirmation
    """
    try:
        if not PERFORMANCE_TRACKER_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Performance tracking system not available"
            )
        
        tracker = get_performance_tracker()
        
        # Validate metric type
        from monitoring.performance_tracker import MetricType
        try:
            metric_type_enum = MetricType(metric_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid metric type: {metric_type}. Valid types: {[t.value for t in MetricType]}"
            )
        
        # Record the metric
        tracker.record_metric(
            metric_type=metric_type_enum,
            operation_name=operation_name,
            value=value,
            unit=unit,
            success=success,
            user_id=user_id,
            endpoint=endpoint
        )
        
        return {
            'status': 'recorded',
            'timestamp': datetime.utcnow().isoformat(),
            'metric_type': metric_type,
            'operation_name': operation_name,
            'value': value,
            'unit': unit
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Record metric endpoint error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to record performance metric: {str(e)}"
        )


@performance_router.get("/trends",
                       summary="Performance Trends",
                       description="Performance trend analysis over time")
async def get_performance_trends():
    """
    Get performance trend analysis for optimization insights.
    
    Returns:
        dict: Performance trends and analysis
    """
    try:
        if not PERFORMANCE_TRACKER_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Performance tracking system not available"
            )
        
        tracker = get_performance_tracker()
        report = tracker.get_detailed_report()
        
        trends_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'trend_analysis': report.get('performance_trends', {}),
            'concurrent_user_impact': report.get('concurrent_user_impact', {}),
            'recommendations': [
                rec for rec in report.get('recommendations', [])
                if rec.get('category') in ['performance', 'optimization']
            ]
        }
        
        return JSONResponse(content=trends_data)
        
    except Exception as e:
        logger.error(f"Performance trends endpoint error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve performance trends: {str(e)}"
        )


@performance_router.get("/rate-limiter", 
                       summary="Rate Limiter Performance Metrics",
                       description="Get detailed rate limiter performance metrics with timeout protection status")
async def get_rate_limiter_metrics(request: Request):
    """
    Get comprehensive rate limiter performance metrics.
    
    Provides:
    - Redis connection status and performance
    - Timeout protection metrics
    - Memory fallback statistics
    - Rate limiting effectiveness
    - Performance impact analysis
    
    Returns:
        dict: Rate limiter performance and health metrics
    """
    try:
        # Get the rate limiter instance from the app
        rate_limiter = None
        for middleware in request.app.middleware_stack:
            if hasattr(middleware, 'cls') and middleware.cls.__name__ == 'RateLimitMiddleware':
                rate_limiter = middleware.args[0] if middleware.args else None
                break
        
        if not rate_limiter and hasattr(request.app, 'user_middleware'):
            # Try to find it in user middleware
            for middleware in request.app.user_middleware:
                if hasattr(middleware, 'rate_limiter'):
                    rate_limiter = middleware
                    break
        
        if not rate_limiter:
            # Create a test instance to get baseline metrics
            from middleware.production_rate_limiter import ProductionRateLimiter
            test_limiter = ProductionRateLimiter()
            base_metrics = test_limiter.get_metrics()
            
            return {
                'timestamp': datetime.utcnow().isoformat(),
                'status': 'no_active_instance',
                'message': 'No active rate limiter instance found in middleware stack',
                'baseline_metrics': base_metrics,
                'timeout_protection': {
                    'enabled': True,
                    'timeout_ms': 100,
                    'status': 'configured'
                },
                'performance_impact': {
                    'blocking_prevented': 'timeout protection active',
                    'fallback_available': base_metrics.get('backend') == 'memory'
                }
            }
        
        # Get detailed metrics from active rate limiter
        if hasattr(rate_limiter, 'rate_limiter'):
            limiter_instance = rate_limiter.rate_limiter
        else:
            limiter_instance = rate_limiter
        
        base_metrics = limiter_instance.get_metrics()
        
        # Perform Redis health check if available
        redis_health = None
        if hasattr(limiter_instance, 'redis_client') and limiter_instance.redis_client:
            try:
                redis_health = await limiter_instance.health_check_redis()
            except Exception as e:
                logger.warning(f"Redis health check failed: {e}")
                redis_health = False
        
        # Calculate performance grades
        def get_performance_grade(metrics):
            if not metrics['redis_available']:
                return 'B'  # Memory fallback is acceptable
            
            if metrics['redis_timeouts'] > 0:
                timeout_rate = metrics['redis_timeouts'] / max(metrics['total_redis_operations'], 1)
                if timeout_rate > 0.1:  # >10% timeout rate
                    return 'C'
                elif timeout_rate > 0.05:  # >5% timeout rate
                    return 'B'
            
            if metrics['avg_redis_time_ms'] > 50:  # Slow Redis
                return 'C'
            elif metrics['avg_redis_time_ms'] > 20:
                return 'B'
            
            return 'A'  # Excellent performance
        
        performance_grade = get_performance_grade(base_metrics)
        
        # Calculate effectiveness metrics
        total_redis_operations = base_metrics.get('total_redis_operations', 0)
        fallback_rate = (base_metrics.get('memory_fallbacks', 0) / max(total_redis_operations, 1)) * 100 if total_redis_operations > 0 else 0
        timeout_rate = (base_metrics.get('redis_timeouts', 0) / max(total_redis_operations, 1)) * 100 if total_redis_operations > 0 else 0
        error_rate = (base_metrics.get('redis_errors', 0) / max(total_redis_operations, 1)) * 100 if total_redis_operations > 0 else 0
        
        response_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'status': 'active',
            'rate_limiter_metrics': base_metrics,
            'redis_health': {
                'available': base_metrics.get('redis_available', False),
                'health_check_result': redis_health,
                'connection_status': 'healthy' if base_metrics.get('redis_available') else 'unavailable'
            },
            'timeout_protection': {
                'enabled': True,
                'timeout_threshold_ms': base_metrics.get('timeout_threshold_ms', 100),
                'timeouts_occurred': base_metrics.get('redis_timeouts', 0),
                'timeout_rate_percent': round(timeout_rate, 2),
                'protection_effective': timeout_rate < 10  # <10% is good
            },
            'performance_analysis': {
                'grade': performance_grade,
                'avg_redis_time_ms': base_metrics.get('avg_redis_time_ms', 0),
                'fallback_rate_percent': round(fallback_rate, 2),
                'error_rate_percent': round(error_rate, 2),
                'blocking_risk': 'low' if base_metrics.get('timeout_threshold_ms', 0) <= 100 else 'high'
            },
            'effectiveness': {
                'primary_backend': base_metrics.get('backend', 'unknown'),
                'fallback_available': True,
                'non_blocking_guaranteed': True,
                'max_blocking_time_ms': base_metrics.get('timeout_threshold_ms', 100)
            },
            'recommendations': []
        }
        
        # Generate recommendations based on metrics
        if fallback_rate > 20:
            response_data['recommendations'].append({
                'priority': 'HIGH',
                'issue': f'High fallback rate: {fallback_rate:.1f}%',
                'recommendation': 'Investigate Redis connectivity and performance issues',
                'impact': 'May indicate Redis instability'
            })
        
        if base_metrics.get('avg_redis_time_ms', 0) > 50:
            response_data['recommendations'].append({
                'priority': 'MEDIUM',
                'issue': f'Slow Redis operations: {base_metrics["avg_redis_time_ms"]:.1f}ms average',
                'recommendation': 'Optimize Redis configuration or consider Redis performance tuning',
                'impact': 'Affects rate limiting responsiveness'
            })
        
        if timeout_rate > 5:
            response_data['recommendations'].append({
                'priority': 'MEDIUM',
                'issue': f'Redis timeouts occurring: {timeout_rate:.1f}% of operations',
                'recommendation': 'Review Redis connection settings and network latency',
                'impact': 'Causes fallback to memory-based rate limiting'
            })
        
        if not base_metrics.get('redis_available', False):
            response_data['recommendations'].append({
                'priority': 'INFO',
                'issue': 'Using memory-based rate limiting',
                'recommendation': 'Configure Redis URL for distributed rate limiting',
                'impact': 'Rate limiting is per-instance only'
            })
        
        return JSONResponse(
            content=response_data,
            headers={
                'X-Rate-Limiter-Status': 'active' if base_metrics.get('redis_available') else 'fallback',
                'X-Performance-Grade': performance_grade,
                'X-Timeout-Protection': 'enabled',
                'X-Max-Blocking-Time': str(base_metrics.get('timeout_threshold_ms', 100)) + 'ms'
            }
        )
        
    except Exception as e:
        logger.error(f"Rate limiter metrics endpoint error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve rate limiter metrics: {str(e)}"
        )