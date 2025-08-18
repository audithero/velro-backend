#!/usr/bin/env python3
"""
Configuration validation script for Railway deployment.
Validates all configuration files, environment variables, and dependencies.
"""

import os
import sys
import json
import toml
from pathlib import Path
from typing import Dict, List, Any, Optional
import re

class ConfigValidator:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.backend_dir = Path(__file__).parent
        
    def add_error(self, message: str, details: Optional[Dict] = None):
        """Add validation error."""
        self.errors.append({"message": message, "details": details or {}})
        print(f"❌ ERROR: {message}")
        if details:
            for key, value in details.items():
                print(f"   {key}: {value}")
    
    def add_warning(self, message: str, details: Optional[Dict] = None):
        """Add validation warning."""
        self.warnings.append({"message": message, "details": details or {}})
        print(f"⚠️  WARNING: {message}")
        if details:
            for key, value in details.items():
                print(f"   {key}: {value}")
    
    def validate_nixpacks_config(self) -> bool:
        """Validate nixpacks.toml configuration."""
        print("\n📦 Validating nixpacks.toml...")
        
        nixpacks_file = self.backend_dir / "nixpacks.toml"
        if not nixpacks_file.exists():
            self.add_error("nixpacks.toml not found")
            return False
        
        try:
            config = toml.load(nixpacks_file)
            
            # Validate start section
            if "start" not in config:
                self.add_error("Missing [start] section in nixpacks.toml")
                return False
            
            start_cmd = config["start"].get("cmd", "")
            if not start_cmd:
                self.add_error("Missing start command in nixpacks.toml")
                return False
            
            # Check for proper uvicorn command
            required_patterns = [
                r"uvicorn\s+main:app",
                r"--host\s+0\.0\.0\.0",
                r"--port\s+\$PORT"
            ]
            
            for pattern in required_patterns:
                if not re.search(pattern, start_cmd):
                    self.add_error(f"Start command missing pattern: {pattern}")
            
            # Validate variables section
            if "variables" not in config:
                self.add_warning("Missing [variables] section in nixpacks.toml")
            else:
                variables = config["variables"]
                if "PORT" not in variables:
                    self.add_warning("PORT variable not set in nixpacks.toml")
                elif variables["PORT"] != "8000":
                    self.add_warning(f"PORT set to {variables['PORT']}, expected 8000")
            
            # Validate build section
            if "build" not in config:
                self.add_warning("Missing [build] section in nixpacks.toml")
            else:
                build_cmd = config["build"].get("buildCommand", "")
                if "pip install -r requirements.txt" not in build_cmd:
                    self.add_warning("Build command doesn't install requirements.txt")
            
            print("✅ nixpacks.toml validation passed")
            return len(self.errors) == 0
            
        except Exception as e:
            self.add_error(f"Failed to parse nixpacks.toml: {str(e)}")
            return False
    
    def validate_requirements(self) -> bool:
        """Validate requirements.txt."""
        print("\n📋 Validating requirements.txt...")
        
        requirements_file = self.backend_dir / "requirements.txt"
        if not requirements_file.exists():
            self.add_error("requirements.txt not found")
            return False
        
        try:
            content = requirements_file.read_text()
            lines = [line.strip() for line in content.split('\n') if line.strip() and not line.startswith('#')]
            
            # Critical dependencies
            critical_deps = {
                "fastapi": r"fastapi[>=0.100.0]",
                "uvicorn": r"uvicorn.*",
                "supabase": r"supabase.*",
                "pydantic": r"pydantic.*",
                "python-jose": r"python-jose.*"
            }
            
            found_deps = {}
            for line in lines:
                for dep_name in critical_deps:
                    if line.lower().startswith(dep_name.lower()):
                        found_deps[dep_name] = line
                        break
            
            # Check for missing critical dependencies
            missing_deps = set(critical_deps.keys()) - set(found_deps.keys())
            if missing_deps:
                self.add_error("Missing critical dependencies", {"missing": list(missing_deps)})
            
            # Check for version compatibility issues
            compatibility_warnings = []
            
            # Check FastAPI version
            if "fastapi" in found_deps:
                if "0.104" not in found_deps["fastapi"]:
                    compatibility_warnings.append("FastAPI version may not be optimal for deployment")
            
            # Check Supabase version
            if "supabase" in found_deps:
                if "1.2.0" not in found_deps["supabase"]:
                    compatibility_warnings.append("Supabase version may have proxy parameter issues")
            
            for warning in compatibility_warnings:
                self.add_warning(warning)
            
            print(f"✅ Found {len(found_deps)} critical dependencies")
            return len(self.errors) == 0
            
        except Exception as e:
            self.add_error(f"Failed to parse requirements.txt: {str(e)}")
            return False
    
    def validate_main_py(self) -> bool:
        """Validate main.py application entry point."""
        print("\n🚀 Validating main.py...")
        
        main_file = self.backend_dir / "main.py"
        if not main_file.exists():
            self.add_error("main.py not found")
            return False
        
        try:
            content = main_file.read_text()
            
            # Check for FastAPI app instance
            if "app = FastAPI(" not in content:
                self.add_error("FastAPI app instance not found in main.py")
            
            # Check for lifespan management
            if "lifespan=" not in content:
                self.add_warning("No lifespan management configured")
            
            # Check for Railway-specific configurations
            railway_patterns = [
                r"Railway",
                r"0\.0\.0\.0",
                r"\$PORT",
                r"health_check"
            ]
            
            missing_patterns = []
            for pattern in railway_patterns:
                if not re.search(pattern, content, re.IGNORECASE):
                    missing_patterns.append(pattern)
            
            if missing_patterns:
                self.add_warning("Missing Railway-specific patterns", {"missing": missing_patterns})
            
            # Check for middleware configuration
            middleware_checks = [
                "CORSMiddleware",
                "AuthMiddleware", 
                "TrustedHostMiddleware"
            ]
            
            missing_middleware = []
            for middleware in middleware_checks:
                if middleware not in content:
                    missing_middleware.append(middleware)
            
            if missing_middleware:
                self.add_warning("Missing middleware", {"missing": missing_middleware})
            
            print("✅ main.py validation passed")
            return len(self.errors) == 0
            
        except Exception as e:
            self.add_error(f"Failed to parse main.py: {str(e)}")
            return False
    
    def validate_environment_vars(self) -> bool:
        """Validate environment variable configuration."""
        print("\n🔧 Validating environment variables...")
        
        # Load from .env if exists
        env_file = self.backend_dir / ".env"
        env_vars = {}
        
        if env_file.exists():
            try:
                content = env_file.read_text()
                for line in content.split('\n'):
                    line = line.strip()
                    if line and '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        env_vars[key.strip()] = value.strip()
            except Exception as e:
                self.add_warning(f"Failed to parse .env file: {str(e)}")
        
        # Add system environment variables
        env_vars.update(os.environ)
        
        # Required environment variables for production
        required_vars = [
            "SUPABASE_URL",
            "SUPABASE_SERVICE_KEY", 
            "JWT_SECRET_KEY"
        ]
        
        # Optional but recommended variables
        recommended_vars = [
            "FAL_KEY",
            "ENVIRONMENT",
            "CORS_ORIGINS"
        ]
        
        missing_required = []
        missing_recommended = []
        
        for var in required_vars:
            if var not in env_vars or not env_vars[var]:
                missing_required.append(var)
        
        for var in recommended_vars:
            if var not in env_vars or not env_vars[var]:
                missing_recommended.append(var)
        
        if missing_required:
            self.add_error("Missing required environment variables", {"missing": missing_required})
        
        if missing_recommended:
            self.add_warning("Missing recommended environment variables", {"missing": missing_recommended})
        
        # Validate environment variable formats
        if "SUPABASE_URL" in env_vars:
            url = env_vars["SUPABASE_URL"]
            if not url.startswith("https://") or "supabase.co" not in url:
                self.add_error("Invalid SUPABASE_URL format")
        
        if "JWT_SECRET_KEY" in env_vars:
            key = env_vars["JWT_SECRET_KEY"]
            if len(key) < 32:
                self.add_warning("JWT_SECRET_KEY should be at least 32 characters")
        
        print(f"✅ Found {len(env_vars)} environment variables")
        return len(self.errors) == 0
    
    def validate_project_structure(self) -> bool:
        """Validate project directory structure."""
        print("\n📁 Validating project structure...")
        
        required_dirs = [
            "models",
            "routers", 
            "services",
            "middleware",
            "repositories"
        ]
        
        required_files = [
            "main.py",
            "config.py",
            "database.py",
            "requirements.txt",
            "nixpacks.toml"
        ]
        
        missing_dirs = []
        missing_files = []
        
        for dir_name in required_dirs:
            dir_path = self.backend_dir / dir_name
            if not dir_path.exists() or not dir_path.is_dir():
                missing_dirs.append(dir_name)
        
        for file_name in required_files:
            file_path = self.backend_dir / file_name
            if not file_path.exists():
                missing_files.append(file_name)
        
        if missing_dirs:
            self.add_error("Missing required directories", {"missing": missing_dirs})
        
        if missing_files:
            self.add_error("Missing required files", {"missing": missing_files})
        
        print(f"✅ Project structure validation completed")
        return len(self.errors) == 0
    
    def validate_railway_config(self) -> bool:
        """Validate Railway-specific configuration."""
        print("\n🚄 Validating Railway configuration...")
        
        # Check for railway.toml (optional)
        railway_file = self.backend_dir / "railway.toml"
        if railway_file.exists():
            try:
                config = toml.load(railway_file)
                print("✅ Found railway.toml configuration")
            except Exception as e:
                self.add_warning(f"Failed to parse railway.toml: {str(e)}")
        
        # Check for Railway-specific environment handling
        config_file = self.backend_dir / "config.py"
        if config_file.exists():
            try:
                content = config_file.read_text()
                
                # Check for environment detection
                if "RAILWAY_" not in content and "is_production" not in content:
                    self.add_warning("No Railway environment detection found")
                
                print("✅ Configuration file validated")
            except Exception as e:
                self.add_warning(f"Failed to validate config.py: {str(e)}")
        
        return True
    
    def run_validation(self) -> Dict[str, Any]:
        """Run complete configuration validation."""
        print("🔍 Starting Configuration Validation")
        print("=" * 50)
        
        # Change to backend directory
        os.chdir(self.backend_dir)
        print(f"📁 Working directory: {self.backend_dir}")
        
        # Run all validations
        validations = [
            ("Project Structure", self.validate_project_structure),
            ("Nixpacks Config", self.validate_nixpacks_config),
            ("Requirements", self.validate_requirements),
            ("Main Application", self.validate_main_py),
            ("Environment Variables", self.validate_environment_vars),
            ("Railway Config", self.validate_railway_config)
        ]
        
        results = {}
        for name, validator in validations:
            try:
                results[name] = validator()
            except Exception as e:
                self.add_error(f"Validation '{name}' failed: {str(e)}")
                results[name] = False
        
        # Generate summary
        total_errors = len(self.errors)
        total_warnings = len(self.warnings)
        
        report = {
            "summary": {
                "total_validations": len(validations),
                "passed_validations": sum(results.values()),
                "failed_validations": len(validations) - sum(results.values()),
                "total_errors": total_errors,
                "total_warnings": total_warnings,
                "validation_passed": total_errors == 0
            },
            "results": results,
            "errors": self.errors,
            "warnings": self.warnings
        }
        
        print("\n" + "=" * 50)
        print("📊 CONFIGURATION VALIDATION SUMMARY")
        print("=" * 50)
        print(f"Validations: {report['summary']['passed_validations']}/{report['summary']['total_validations']} passed")
        print(f"Errors: {total_errors}")
        print(f"Warnings: {total_warnings}")
        
        if report["summary"]["validation_passed"]:
            print("\n✅ CONFIGURATION VALID - Ready for deployment")
        else:
            print("\n❌ CONFIGURATION INVALID - Fix errors before deployment")
        
        return report


def main():
    """Main validation execution."""
    validator = ConfigValidator()
    
    try:
        report = validator.run_validation()
        
        # Save report
        report_file = Path("config_validation_report.json")
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)
        
        print(f"\n📄 Validation report saved to: {report_file}")
        
        # Exit with appropriate code
        if report["summary"]["validation_passed"]:
            sys.exit(0)
        else:
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n⏹️  Validation interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Validation failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()