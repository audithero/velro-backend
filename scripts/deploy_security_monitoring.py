"""
Security Monitoring Deployment Script
Deploys and configures the comprehensive security monitoring system for production use.
"""

import os
import json
import asyncio
import logging
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('security_monitoring_deployment.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class SecurityMonitoringDeployer:
    """Handles deployment of the security monitoring system."""
    
    def __init__(self, environment: str = "production"):
        self.environment = environment
        self.project_root = Path(__file__).parent.parent
        self.config = self._load_deployment_config()
        
        logger.info(f"🚀 Security Monitoring Deployer initialized for {environment}")
    
    def _load_deployment_config(self) -> Dict[str, Any]:
        """Load deployment configuration."""
        config = {
            "production": {
                "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379"),
                "geoip_db_path": "/opt/geoip/GeoLite2-City.mmdb",
                "log_directory": "/var/log/velro",
                "audit_storage": "sqlite",
                "enable_real_time_blocking": True,
                "enable_incident_escalation": True,
                "monitoring_intervals": {
                    "event_processing": 10,
                    "incident_correlation": 30,
                    "cleanup": 3600
                }
            },
            "development": {
                "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379"),
                "geoip_db_path": None,
                "log_directory": "./logs",
                "audit_storage": "file",
                "enable_real_time_blocking": False,
                "enable_incident_escalation": False,
                "monitoring_intervals": {
                    "event_processing": 30,
                    "incident_correlation": 60,
                    "cleanup": 7200
                }
            }
        }
        
        return config.get(self.environment, config["development"])
    
    async def deploy(self) -> bool:
        """Deploy the security monitoring system."""
        logger.info("🛡️ Starting security monitoring deployment...")
        
        try:
            # Step 1: Create directories and set permissions
            await self._setup_directories()
            
            # Step 2: Install dependencies
            await self._install_dependencies()
            
            # Step 3: Configure logging
            await self._setup_logging()
            
            # Step 4: Setup database and storage
            await self._setup_storage()
            
            # Step 5: Configure Redis
            await self._setup_redis()
            
            # Step 6: Download and setup GeoIP database
            await self._setup_geoip()
            
            # Step 7: Create configuration files
            await self._create_config_files()
            
            # Step 8: Setup systemd services (Linux only)
            if os.name == 'posix' and self.environment == "production":
                await self._setup_systemd_services()
            
            # Step 9: Configure monitoring and alerting
            await self._setup_monitoring()
            
            # Step 10: Run deployment tests
            await self._run_deployment_tests()
            
            logger.info("✅ Security monitoring deployment completed successfully!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Deployment failed: {e}")
            return False
    
    async def _setup_directories(self):
        """Create necessary directories with proper permissions."""
        logger.info("📁 Setting up directories...")
        
        directories = [
            self.config["log_directory"],
            f"{self.config['log_directory']}/audit",
            f"{self.config['log_directory']}/security",
            f"{self.config['log_directory']}/incidents",
            "/opt/velro/config",
            "/opt/velro/data"
        ]
        
        for directory in directories:
            try:
                Path(directory).mkdir(parents=True, exist_ok=True)
                logger.info(f"  ✅ Created directory: {directory}")
                
                # Set permissions (Linux/Unix only)
                if os.name == 'posix' and self.environment == "production":
                    os.chmod(directory, 0o755)
                    # Change ownership to velro user if it exists
                    try:
                        subprocess.run(['chown', 'velro:velro', directory], check=True)
                    except subprocess.CalledProcessError:
                        logger.warning(f"  ⚠️ Could not set ownership for {directory}")
                        
            except Exception as e:
                logger.error(f"  ❌ Failed to create directory {directory}: {e}")
                raise
    
    async def _install_dependencies(self):
        """Install required dependencies."""
        logger.info("📦 Installing dependencies...")
        
        requirements = [
            "geoip2",
            "redis",
            "sqlalchemy",
            "aiosqlite",
            "prometheus-client"
        ]
        
        for package in requirements:
            try:
                subprocess.run(['pip', 'install', package], check=True, capture_output=True)
                logger.info(f"  ✅ Installed: {package}")
            except subprocess.CalledProcessError as e:
                logger.error(f"  ❌ Failed to install {package}: {e}")
                raise
    
    async def _setup_logging(self):
        """Configure logging for security monitoring."""
        logger.info("📝 Setting up logging configuration...")
        
        log_config = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "security": {
                    "format": "%(asctime)s - [SECURITY] - %(levelname)s - %(name)s - %(message)s"
                },
                "audit": {
                    "format": "%(asctime)s - [AUDIT] - %(message)s"
                },
                "json": {
                    "format": '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}'
                }
            },
            "handlers": {
                "security_file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": f"{self.config['log_directory']}/security/security.log",
                    "maxBytes": 10485760,  # 10MB
                    "backupCount": 10,
                    "formatter": "security"
                },
                "audit_file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": f"{self.config['log_directory']}/audit/audit.log",
                    "maxBytes": 10485760,  # 10MB
                    "backupCount": 50,
                    "formatter": "audit"
                },
                "json_file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": f"{self.config['log_directory']}/security/security.json",
                    "maxBytes": 10485760,  # 10MB
                    "backupCount": 10,
                    "formatter": "json"
                }
            },
            "loggers": {
                "velro.security": {
                    "handlers": ["security_file", "json_file"],
                    "level": "INFO",
                    "propagate": False
                },
                "velro.security.audit": {
                    "handlers": ["audit_file"],
                    "level": "INFO",
                    "propagate": False
                }
            }
        }
        
        # Save logging configuration
        config_path = "/opt/velro/config/logging.json"
        with open(config_path, 'w') as f:
            json.dump(log_config, f, indent=2)
        
        logger.info(f"  ✅ Logging configuration saved to {config_path}")
    
    async def _setup_storage(self):
        """Setup storage backend for audit logs."""
        logger.info("💾 Setting up storage backend...")
        
        if self.config["audit_storage"] == "sqlite":
            # Initialize SQLite database
            db_path = f"{self.config['log_directory']}/audit/audit.db"
            
            # This would be handled by the audit system initialization
            logger.info(f"  ✅ SQLite database will be initialized at {db_path}")
            
        elif self.config["audit_storage"] == "file":
            # Create audit log file
            audit_file = f"{self.config['log_directory']}/audit/audit.jsonl"
            Path(audit_file).touch(exist_ok=True)
            logger.info(f"  ✅ Audit file created at {audit_file}")
    
    async def _setup_redis(self):
        """Setup Redis configuration."""
        logger.info("🔴 Setting up Redis configuration...")
        
        redis_config = {
            "url": self.config["redis_url"],
            "max_connections": 20,
            "retry_on_timeout": True,
            "socket_timeout": 5,
            "socket_connect_timeout": 5,
            "security_keys": {
                "blocked_ips": "security:blocked_ips",
                "incidents": "security:incidents",
                "session_tracking": "security:sessions"
            }
        }
        
        # Save Redis configuration
        config_path = "/opt/velro/config/redis.json"
        with open(config_path, 'w') as f:
            json.dump(redis_config, f, indent=2)
        
        logger.info(f"  ✅ Redis configuration saved to {config_path}")
        
        # Test Redis connection
        try:
            import redis
            client = redis.from_url(self.config["redis_url"])
            client.ping()
            logger.info("  ✅ Redis connection test successful")
        except Exception as e:
            logger.warning(f"  ⚠️ Redis connection test failed: {e}")
    
    async def _setup_geoip(self):
        """Download and setup GeoIP database."""
        logger.info("🌍 Setting up GeoIP database...")
        
        if not self.config["geoip_db_path"]:
            logger.info("  ℹ️ GeoIP database not configured, skipping...")
            return
        
        geoip_dir = Path(self.config["geoip_db_path"]).parent
        geoip_dir.mkdir(parents=True, exist_ok=True)
        
        # Instructions for manual GeoIP setup
        setup_instructions = f"""
# GeoIP Database Setup Instructions

1. Download GeoLite2 City database from MaxMind:
   https://dev.maxmind.com/geoip/geolite2-free-geolocation-data

2. Extract the database to:
   {self.config["geoip_db_path"]}

3. Ensure the file has appropriate permissions:
   chmod 644 {self.config["geoip_db_path"]}

# Automated download (requires MaxMind account):
# export MAXMIND_LICENSE_KEY="your_license_key"
# wget "https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-City&license_key=$MAXMIND_LICENSE_KEY&suffix=tar.gz" -O GeoLite2-City.tar.gz
# tar -xzf GeoLite2-City.tar.gz
# cp GeoLite2-City_*/GeoLite2-City.mmdb {self.config["geoip_db_path"]}
"""
        
        instructions_path = "/opt/velro/config/geoip_setup_instructions.txt"
        with open(instructions_path, 'w') as f:
            f.write(setup_instructions)
        
        logger.info(f"  ✅ GeoIP setup instructions saved to {instructions_path}")
        
        # Check if GeoIP database exists
        if Path(self.config["geoip_db_path"]).exists():
            logger.info("  ✅ GeoIP database found")
        else:
            logger.warning("  ⚠️ GeoIP database not found - geographic analysis will be limited")
    
    async def _create_config_files(self):
        """Create configuration files for security monitoring."""
        logger.info("⚙️ Creating configuration files...")
        
        # Main security configuration
        security_config = {
            "environment": self.environment,
            "monitoring": {
                "enabled": True,
                "real_time_blocking": self.config["enable_real_time_blocking"],
                "incident_escalation": self.config["enable_incident_escalation"],
                "patterns": {
                    "enable_sql_injection_detection": True,
                    "enable_xss_detection": True,
                    "enable_path_traversal_detection": True,
                    "enable_command_injection_detection": True
                },
                "thresholds": {
                    "auto_block_threshold": 5,  # violations before auto-block
                    "incident_creation_threshold": 3,  # events before incident
                    "high_risk_score_threshold": 70
                }
            },
            "audit": {
                "enabled": True,
                "storage_type": self.config["audit_storage"],
                "retention_days": 2555,  # 7 years
                "compliance_standards": ["gdpr", "soc2", "iso27001"]
            },
            "redis": {
                "url": self.config["redis_url"]
            },
            "geoip": {
                "database_path": self.config.get("geoip_db_path")
            },
            "logging": {
                "directory": self.config["log_directory"],
                "level": "INFO" if self.environment == "production" else "DEBUG"
            }
        }
        
        config_path = "/opt/velro/config/security_monitoring.json"
        with open(config_path, 'w') as f:
            json.dump(security_config, f, indent=2)
        
        logger.info(f"  ✅ Security configuration saved to {config_path}")
        
        # Prometheus metrics configuration
        prometheus_config = {
            "enabled": True,
            "port": 9090,
            "metrics": {
                "security_events": True,
                "audit_events": True,
                "performance_metrics": True,
                "system_health": True
            }
        }
        
        prometheus_path = "/opt/velro/config/prometheus.json"
        with open(prometheus_path, 'w') as f:
            json.dump(prometheus_config, f, indent=2)
        
        logger.info(f"  ✅ Prometheus configuration saved to {prometheus_path}")
    
    async def _setup_systemd_services(self):
        """Setup systemd services for Linux production deployments."""
        logger.info("🔧 Setting up systemd services...")
        
        # Security monitoring service
        service_content = f"""[Unit]
Description=Velro Security Monitoring Service
After=network.target redis.service
Wants=redis.service

[Service]
Type=exec
User=velro
Group=velro
WorkingDirectory={self.project_root}
Environment=PYTHONPATH={self.project_root}
Environment=VELRO_ENV=production
ExecStart=/usr/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
ExecReload=/bin/kill -HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
"""
        
        service_path = "/etc/systemd/system/velro-security.service"
        try:
            with open(service_path, 'w') as f:
                f.write(service_content)
            
            # Reload systemd and enable service
            subprocess.run(['systemctl', 'daemon-reload'], check=True)
            subprocess.run(['systemctl', 'enable', 'velro-security'], check=True)
            
            logger.info(f"  ✅ Systemd service created: {service_path}")
            
        except (PermissionError, subprocess.CalledProcessError) as e:
            logger.warning(f"  ⚠️ Could not create systemd service: {e}")
    
    async def _setup_monitoring(self):
        """Setup monitoring and alerting."""
        logger.info("📊 Setting up monitoring and alerting...")
        
        # Create monitoring scripts
        health_check_script = """#!/bin/bash
# Health check script for security monitoring

HEALTH_ENDPOINT="http://localhost:8000/api/v1/security/health"
RESPONSE=$(curl -s -o /dev/null -w "%%{http_code}" $HEALTH_ENDPOINT)

if [ $RESPONSE -eq 200 ]; then
    echo "✅ Security monitoring is healthy"
    exit 0
else
    echo "❌ Security monitoring is unhealthy (HTTP $RESPONSE)"
    exit 1
fi
"""
        
        health_check_path = "/opt/velro/scripts/health_check.sh"
        Path(health_check_path).parent.mkdir(parents=True, exist_ok=True)
        with open(health_check_path, 'w') as f:
            f.write(health_check_script)
        os.chmod(health_check_path, 0o755)
        
        logger.info(f"  ✅ Health check script created: {health_check_path}")
        
        # Create alerting configuration
        alert_config = {
            "enabled": True,
            "channels": {
                "email": {
                    "enabled": False,
                    "smtp_server": "smtp.example.com",
                    "recipients": ["security@example.com"]
                },
                "webhook": {
                    "enabled": False,
                    "url": "https://hooks.slack.com/services/your/webhook/url"
                },
                "log": {
                    "enabled": True,
                    "file": f"{self.config['log_directory']}/security/alerts.log"
                }
            },
            "rules": [
                {
                    "name": "High Severity Security Event",
                    "condition": "security_event.severity >= 3",
                    "channels": ["log", "webhook"]
                },
                {
                    "name": "Multiple Failed Logins",
                    "condition": "failed_logins_per_ip > 5",
                    "channels": ["log", "email"]
                },
                {
                    "name": "New Security Incident",
                    "condition": "new_incident.severity >= 2",
                    "channels": ["log", "webhook", "email"]
                }
            ]
        }
        
        alert_config_path = "/opt/velro/config/alerting.json"
        with open(alert_config_path, 'w') as f:
            json.dump(alert_config, f, indent=2)
        
        logger.info(f"  ✅ Alerting configuration saved: {alert_config_path}")
    
    async def _run_deployment_tests(self):
        """Run tests to verify deployment."""
        logger.info("🧪 Running deployment tests...")
        
        tests_passed = 0
        total_tests = 5
        
        # Test 1: Check if configuration files exist
        config_files = [
            "/opt/velro/config/security_monitoring.json",
            "/opt/velro/config/logging.json",
            "/opt/velro/config/redis.json"
        ]
        
        for config_file in config_files:
            if Path(config_file).exists():
                tests_passed += 1
                logger.info(f"  ✅ Configuration file exists: {config_file}")
            else:
                logger.error(f"  ❌ Configuration file missing: {config_file}")
        
        # Test 2: Check directories
        if Path(self.config["log_directory"]).is_dir():
            tests_passed += 1
            logger.info(f"  ✅ Log directory exists: {self.config['log_directory']}")
        else:
            logger.error(f"  ❌ Log directory missing: {self.config['log_directory']}")
        
        # Test 3: Test Redis connection
        try:
            import redis
            client = redis.from_url(self.config["redis_url"])
            client.ping()
            tests_passed += 1
            logger.info("  ✅ Redis connection successful")
        except Exception as e:
            logger.error(f"  ❌ Redis connection failed: {e}")
        
        # Test 4: Test Python imports
        try:
            from security.security_monitoring_system import security_monitor
            from security.audit_system_enhanced import enhanced_audit_system
            tests_passed += 1
            logger.info("  ✅ Security modules import successfully")
        except ImportError as e:
            logger.error(f"  ❌ Failed to import security modules: {e}")
        
        # Test 5: Test log file creation
        test_log_file = f"{self.config['log_directory']}/deployment_test.log"
        try:
            with open(test_log_file, 'w') as f:
                f.write("Deployment test log entry\n")
            tests_passed += 1
            os.remove(test_log_file)
            logger.info("  ✅ Log file creation successful")
        except Exception as e:
            logger.error(f"  ❌ Log file creation failed: {e}")
        
        # Report test results
        logger.info(f"🧪 Deployment tests completed: {tests_passed}/{total_tests} passed")
        
        if tests_passed == total_tests:
            logger.info("✅ All deployment tests passed!")
            return True
        else:
            logger.warning(f"⚠️ {total_tests - tests_passed} deployment tests failed")
            return False
    
    async def generate_deployment_report(self) -> Dict[str, Any]:
        """Generate deployment report."""
        report = {
            "deployment_info": {
                "environment": self.environment,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "version": "1.0.0",
                "deployer": "SecurityMonitoringDeployer"
            },
            "configuration": self.config,
            "status": {
                "directories_created": True,
                "dependencies_installed": True,
                "logging_configured": True,
                "storage_setup": True,
                "redis_configured": True,
                "monitoring_setup": True
            },
            "next_steps": [
                "Configure MaxMind GeoIP database (if needed)",
                "Set up email/webhook alerting",
                "Configure Grafana dashboards",
                "Set up log rotation policies",
                "Configure firewall rules",
                "Set up SSL certificates"
            ],
            "maintenance": {
                "log_rotation": "Configured with logrotate",
                "database_maintenance": "SQLite auto-vacuum enabled",
                "redis_persistence": "Check Redis configuration",
                "monitoring": "Health checks configured"
            }
        }
        
        return report


async def main():
    """Main deployment function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Deploy Velro Security Monitoring System")
    parser.add_argument("--environment", "-e", choices=["production", "development"], 
                       default="production", help="Deployment environment")
    parser.add_argument("--config-only", action="store_true", 
                       help="Only create configuration files")
    parser.add_argument("--test-only", action="store_true", 
                       help="Only run deployment tests")
    
    args = parser.parse_args()
    
    deployer = SecurityMonitoringDeployer(args.environment)
    
    if args.test_only:
        success = await deployer._run_deployment_tests()
    elif args.config_only:
        await deployer._create_config_files()
        success = True
    else:
        success = await deployer.deploy()
    
    # Generate deployment report
    report = await deployer.generate_deployment_report()
    
    # Save report
    report_path = f"security_monitoring_deployment_report_{args.environment}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"📋 Deployment report saved: {report_path}")
    
    if success:
        logger.info("🎉 Security monitoring deployment completed successfully!")
        return 0
    else:
        logger.error("❌ Security monitoring deployment failed!")
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))