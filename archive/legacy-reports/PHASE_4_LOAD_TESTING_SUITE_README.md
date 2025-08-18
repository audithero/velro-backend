# PHASE 4: Comprehensive Load Testing Suite for 10,000+ Users

## Overview

This comprehensive load testing suite validates that Velro's backend infrastructure meets PRD requirements for 10,000+ concurrent users with enterprise-grade performance targets.

### PRD Requirements Validated

From `docs/PRD.MD` (lines 369-373):
- **Concurrent Users**: 10,000+ simultaneous users
- **Database Connections**: 200+ optimized connections
- **Cache Hit Rate**: 95%+ for authorization operations  
- **Throughput**: 1,000+ requests/second sustained
- **Response Time**: <50ms authentication, <75ms authorization

## Architecture

### Core Components

1. **Load Test Engine** (`scripts/load_test_10k_users.py`)
   - Real API endpoint testing with authentication
   - Progressive user ramp-up (0 → 10,000 users)
   - Comprehensive metrics collection (P50, P95, P99)
   - System resource monitoring
   - Cache performance validation

2. **Test Scenarios** (`config/load_test_scenarios.yaml`)
   - 6 progressive test phases
   - Realistic user behavior patterns
   - Configurable targets and thresholds
   - Advanced testing features (circuit breakers, failover)

3. **Performance Analysis** (`scripts/performance_validation_report.py`)
   - PRD compliance validation
   - Bottleneck identification
   - Performance regression detection
   - Multi-format reporting (JSON, HTML, CSV)

4. **Execution Framework** (`scripts/run_10k_load_test_suite.sh`)
   - Automated test execution
   - Environment validation
   - System optimization
   - Results compilation

## Test Scenarios

### Phase 1: Warm-up Baseline (500 Users)
- **Duration**: 2 minutes
- **Purpose**: Establish baseline performance
- **Targets**: 100 RPS, 75ms P95, 85% cache hit rate

### Phase 2: Intermediate Scaling (2,500 Users)
- **Duration**: 5 minutes  
- **Purpose**: Test system stability at moderate scale
- **Targets**: 500 RPS, 75ms P95, 90% cache hit rate

### Phase 3: Large Scale Validation (5,000 Users)
- **Duration**: 7.5 minutes
- **Purpose**: Pre-PRD validation
- **Targets**: 800 RPS, 75ms P95, 93% cache hit rate

### Phase 4: PRD Compliance Validation (10,000 Users) ⭐
- **Duration**: 10 minutes sustained load
- **Purpose**: Official PRD compliance test
- **Targets**: 1,000 RPS, 75ms P95, 95% cache hit rate
- **Validation**: All PRD requirements

### Phase 5: Stress Test (15,000 Users)
- **Duration**: 5 minutes
- **Purpose**: Find system limits beyond PRD
- **Targets**: 1,200 RPS, 100ms P95, 90% cache hit rate

### Phase 6: Endurance Test (8,000 Users)
- **Duration**: 30 minutes
- **Purpose**: Long-term stability validation
- **Targets**: 800 RPS, 75ms P95, 93% cache hit rate

## Installation & Setup

### Prerequisites

```bash
# Python 3.8+ with required packages
pip install aiohttp numpy pandas psutil jinja2 pyyaml

# System requirements (recommended)
- CPU: 4+ cores
- Memory: 8+ GB RAM
- Network: Stable internet connection
- OS: Linux/macOS (Windows with WSL2)
```

### Environment Variables

```bash
# Required
export SUPABASE_SERVICE_KEY="your_supabase_service_key"

# Optional
export VELRO_API_URL="https://velro-backend-production.up.railway.app"
export REDIS_URL="redis://localhost:6379"
```

### Quick Start

```bash
# Clone and navigate to backend directory
cd velro-backend

# Set environment variables
export SUPABASE_SERVICE_KEY="your_key_here"

# Execute comprehensive load test suite
./scripts/run_10k_load_test_suite.sh
```

## Usage

### Basic Execution

```bash
# Standard comprehensive test (30-60 minutes)
./scripts/run_10k_load_test_suite.sh

# Dry run for validation
./scripts/run_10k_load_test_suite.sh --dry-run

# Quick test (abbreviated scenarios)
./scripts/run_10k_load_test_suite.sh --quick-test

# Verbose logging
./scripts/run_10k_load_test_suite.sh --verbose
```

### Direct Script Execution

```bash
# Run load test directly
cd scripts
python3 load_test_10k_users.py

# Generate reports from existing results
python3 performance_validation_report.py results.json --formats json html csv
```

## Configuration

### Test Scenarios (`config/load_test_scenarios.yaml`)

```yaml
# Customize scenarios
scenarios:
  prd_compliance_validation:
    concurrent_users: 10000
    test_duration_seconds: 600
    targets:
      requests_per_second: 1000.0
      p95_response_time_ms: 75.0
      cache_hit_rate: 95.0
```

### Request Patterns

```yaml
# Realistic user behavior
request_patterns:
  authentication_check: 1.0    # 100% authenticated
  authorization_check: 0.95    # 95% check authorization
  generation_list: 0.85        # 85% list generations
  model_access: 0.6            # 60% access models
  generation_create: 0.25      # 25% create generations
  media_url_access: 0.4        # 40% access media URLs
```

## Monitoring & Metrics

### Real-time Metrics Collection

- **Response Times**: P50, P95, P99 percentiles
- **Throughput**: Requests per second, peak RPS
- **Cache Performance**: Hit rates by cache layer
- **System Resources**: CPU, memory, connections
- **Error Analysis**: Error rates, status code distribution

### Performance Targets

| Metric | Target | Critical Threshold |
|--------|--------|-------------------|
| P95 Response Time | <75ms | <100ms |
| Throughput | 1,000+ RPS | 800+ RPS |
| Cache Hit Rate | 95%+ | 90%+ |
| Error Rate | <1% | <5% |
| Concurrent Users | 10,000+ | 8,000+ |

## Results & Reporting

### Output Files

```
load_test_results/
├── load_test_10k_users_results_[timestamp].json    # Raw metrics
├── performance_validation_report_[timestamp].json  # Analysis
├── performance_validation_report_[timestamp].html  # Visual report
├── performance_validation_report_[timestamp].csv   # Summary
├── executive_summary_[timestamp].json              # Stakeholder summary
└── load_test_execution.log                         # Execution log
```

### Report Contents

1. **Executive Summary**
   - PRD compliance status
   - Key performance indicators
   - Business impact assessment
   - Production readiness verdict

2. **Detailed Performance Analysis**
   - Response time distribution
   - Throughput analysis
   - Cache performance breakdown
   - System resource utilization
   - Error pattern analysis

3. **Bottleneck Identification**
   - Performance bottlenecks
   - Resource constraints
   - Optimization recommendations
   - Capacity planning insights

4. **PRD Compliance Report**
   - Requirement-by-requirement validation
   - Compliance scoring
   - Gap analysis
   - Remediation recommendations

## Interpretation Guide

### PRD Compliance Scoring

- **95-100%**: Excellent - Production ready
- **85-94%**: Good - Minor optimizations needed
- **70-84%**: Acceptable - Moderate improvements required
- **<70%**: Needs Work - Significant optimization required

### Performance Classifications

| Classification | P95 Response Time | Throughput | Cache Hit Rate |
|---------------|------------------|------------|----------------|
| Excellent | <50ms | 1200+ RPS | 95%+ |
| Good | <75ms | 1000+ RPS | 90%+ |
| Acceptable | <100ms | 800+ RPS | 85%+ |
| Needs Work | >100ms | <800 RPS | <85% |

### Common Issues & Solutions

#### High Response Times
- **Cause**: Database query inefficiency, insufficient caching
- **Solution**: Optimize queries, increase cache warming, add indexes

#### Low Throughput  
- **Cause**: Connection pool limits, CPU bottlenecks
- **Solution**: Increase connection pools, optimize code, scale horizontally

#### Poor Cache Performance
- **Cause**: Insufficient cache warming, low TTL values
- **Solution**: Implement predictive caching, increase TTLs, optimize cache keys

#### High Error Rates
- **Cause**: System overload, insufficient resources
- **Solution**: Implement circuit breakers, increase resources, optimize error handling

## Advanced Features

### Circuit Breaker Testing
- Simulates service failures
- Tests graceful degradation
- Validates recovery mechanisms

### Cache Invalidation Testing
- Tests cache consistency
- Validates invalidation patterns
- Measures performance impact

### Resource Monitoring
- Real-time system metrics
- Memory leak detection
- Connection pool monitoring

### Regression Detection
- Historical performance comparison
- Trend analysis
- Performance degradation alerts

## Production Deployment Validation

### Pre-deployment Checklist

- [ ] All test scenarios pass
- [ ] PRD compliance score >90%
- [ ] No critical bottlenecks identified
- [ ] Error rate <1%
- [ ] System resources within limits
- [ ] Cache performance optimal
- [ ] Database connections optimized

### Success Criteria

✅ **10,000+ concurrent users supported**
✅ **Response times <75ms P95**
✅ **Throughput 1,000+ RPS sustained**
✅ **Cache hit rate 95%+**
✅ **Error rate <1%**
✅ **System stability maintained**

## Troubleshooting

### Common Issues

1. **Connection Refused Errors**
   ```bash
   # Check API availability
   curl -I $VELRO_API_URL/health
   
   # Verify service key
   echo $SUPABASE_SERVICE_KEY
   ```

2. **Memory Errors**
   ```bash
   # Increase system limits
   ulimit -n 65536
   
   # Monitor memory usage
   python3 -c "import psutil; print(f'Memory: {psutil.virtual_memory().percent}%')"
   ```

3. **Test Failures**
   ```bash
   # Check logs
   tail -f load_test_results/load_test_execution.log
   
   # Validate environment
   ./scripts/run_10k_load_test_suite.sh --dry-run
   ```

### Performance Debugging

```bash
# System resource monitoring during test
htop  # CPU/Memory monitoring
iotop # Disk I/O monitoring  
netstat -i  # Network monitoring

# Database connection monitoring
psql -c "SELECT count(*) FROM pg_stat_activity;"

# Redis monitoring
redis-cli info stats
```

## Contributing

### Adding New Test Scenarios

1. Edit `config/load_test_scenarios.yaml`
2. Add scenario configuration
3. Update request patterns
4. Set performance targets
5. Test with dry run

### Custom Metrics

1. Extend `LoadTestMetrics` class
2. Add collection logic in test execution
3. Update report generation
4. Include in analysis

### Report Customization

1. Modify HTML template in `performance_validation_report.py`
2. Add new analysis functions
3. Update executive summary format
4. Test report generation

## License

This load testing suite is part of the Velro backend infrastructure and follows the same licensing terms as the main project.

## Support

For issues or questions regarding the load testing suite:

1. Check the troubleshooting guide above
2. Review execution logs in `load_test_results/`
3. Validate environment setup with dry run
4. Contact the development team with detailed error information

---

**Note**: This load testing suite is designed to validate production readiness. Always run tests in a controlled environment and ensure you have appropriate permissions before testing against production systems.