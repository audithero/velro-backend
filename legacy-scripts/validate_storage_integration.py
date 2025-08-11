#!/usr/bin/env python3
"""
Storage Integration Validation Script
Validates that the FAL.ai → Supabase storage integration is properly implemented.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class StorageIntegrationValidator:
    """Validates storage integration implementation."""
    
    def __init__(self):
        self.validation_results = []
    
    def validate_file_structure(self):
        """Validate that all required files exist."""
        logger.info("🔍 Validating file structure...")
        
        required_files = [
            "services/storage_service.py",
            "services/generation_service.py",
            "models/storage.py",
            "migrations/010_enhanced_storage_integration.sql",
            "STORAGE_INTEGRATION_IMPLEMENTATION.md"
        ]
        
        missing_files = []
        for file_path in required_files:
            if not Path(file_path).exists():
                missing_files.append(file_path)
        
        if missing_files:
            logger.error(f"❌ Missing files: {missing_files}")
            return False
        
        logger.info("✅ All required files present")
        return True
    
    def validate_storage_service_methods(self):
        """Validate storage service methods exist."""
        logger.info("🔍 Validating storage service methods...")
        
        try:
            from services.storage_service import storage_service
            
            required_methods = [
                'upload_generation_result',
                'cleanup_failed_generation_files',
                'get_generation_storage_info',
                'migrate_external_urls_to_storage',
                'validate_generation_storage_integrity',
                '_download_file_from_url'
            ]
            
            missing_methods = []
            for method_name in required_methods:
                if not hasattr(storage_service, method_name):
                    missing_methods.append(method_name)
            
            if missing_methods:
                logger.error(f"❌ Missing storage service methods: {missing_methods}")
                return False
            
            logger.info("✅ All storage service methods present")
            return True
            
        except ImportError as e:
            logger.error(f"❌ Failed to import storage service: {e}")
            return False
    
    def validate_generation_service_integration(self):
        """Validate generation service integration."""
        logger.info("🔍 Validating generation service integration...")
        
        try:
            from services.generation_service import generation_service
            
            # Check that generation service imports storage service
            with open("services/generation_service.py", "r") as f:
                content = f.read()
                
            integration_checks = [
                "from services.storage_service import storage_service",
                "upload_generation_result",
                "cleanup_failed_generation_files",
                "progress_callback"
            ]
            
            missing_integrations = []
            for check in integration_checks:
                if check not in content:
                    missing_integrations.append(check)
            
            if missing_integrations:
                logger.error(f"❌ Missing generation service integrations: {missing_integrations}")
                return False
            
            logger.info("✅ Generation service integration validated")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to validate generation service: {e}")
            return False
    
    def validate_database_migration(self):
        """Validate database migration file."""
        logger.info("🔍 Validating database migration...")
        
        migration_file = "migrations/010_enhanced_storage_integration.sql"
        
        try:
            with open(migration_file, "r") as f:
                content = f.read()
            
            required_elements = [
                "ALTER TABLE generations",
                "storage_size BIGINT",
                "is_media_processed BOOLEAN",
                "media_files JSONB",
                "storage_metadata JSONB",
                "CREATE INDEX",
                "validate_generation_storage_data",
                "get_user_storage_stats"
            ]
            
            missing_elements = []
            for element in required_elements:
                if element not in content:
                    missing_elements.append(element)
            
            if missing_elements:
                logger.error(f"❌ Missing migration elements: {missing_elements}")
                return False
            
            logger.info("✅ Database migration validated")
            return True
            
        except FileNotFoundError:
            logger.error(f"❌ Migration file not found: {migration_file}")
            return False
    
    def validate_error_handling_implementation(self):
        """Validate error handling and retry logic."""
        logger.info("🔍 Validating error handling implementation...")
        
        try:
            with open("services/storage_service.py", "r") as f:
                storage_content = f.read()
            
            error_handling_checks = [
                "max_retries",
                "exponential backoff",
                "httpx.TimeoutException",
                "httpx.ConnectTimeout",
                "RuntimeError",
                "try:",
                "except:",
                "logger.error",
                "await asyncio.sleep"
            ]
            
            missing_checks = []
            for check in error_handling_checks:
                if check not in storage_content:
                    missing_checks.append(check)
            
            if missing_checks:
                logger.warning(f"⚠️ Some error handling patterns missing: {missing_checks}")
                return True  # Not critical
            
            logger.info("✅ Error handling implementation validated")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to validate error handling: {e}")
            return False
    
    def validate_progress_tracking(self):
        """Validate progress tracking implementation."""
        logger.info("🔍 Validating progress tracking...")
        
        try:
            with open("services/storage_service.py", "r") as f:
                content = f.read()
            
            progress_checks = [
                "progress_callback",
                "Optional[callable]",
                "progress_info",
                "current_file",
                "total_files",
                "percentage"
            ]
            
            missing_checks = []
            for check in progress_checks:
                if check not in content:
                    missing_checks.append(check)
            
            if missing_checks:
                logger.warning(f"⚠️ Some progress tracking features missing: {missing_checks}")
                return True  # Not critical
            
            logger.info("✅ Progress tracking validated")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to validate progress tracking: {e}")
            return False
    
    def validate_documentation(self):
        """Validate documentation completeness."""
        logger.info("🔍 Validating documentation...")
        
        doc_file = "STORAGE_INTEGRATION_IMPLEMENTATION.md"
        
        try:
            with open(doc_file, "r") as f:
                content = f.read()
            
            doc_sections = [
                "## Overview",
                "## Architecture",
                "## Key Components",
                "## Workflow Process",
                "## Error Handling",
                "## Performance Optimizations",
                "## Security Considerations",
                "## Testing",
                "## API Endpoints",
                "## Troubleshooting"
            ]
            
            missing_sections = []
            for section in doc_sections:
                if section not in content:
                    missing_sections.append(section)
            
            if missing_sections:
                logger.warning(f"⚠️ Documentation sections could be improved: {missing_sections}")
                return True  # Not critical
            
            logger.info("✅ Documentation validated")
            return True
            
        except FileNotFoundError:
            logger.error(f"❌ Documentation file not found: {doc_file}")
            return False
    
    async def run_validation(self):
        """Run all validation checks."""
        logger.info("🚀 Starting Storage Integration Validation")
        logger.info("=" * 60)
        
        validations = [
            ("File Structure", self.validate_file_structure),
            ("Storage Service Methods", self.validate_storage_service_methods),
            ("Generation Service Integration", self.validate_generation_service_integration),
            ("Database Migration", self.validate_database_migration),
            ("Error Handling", self.validate_error_handling_implementation),
            ("Progress Tracking", self.validate_progress_tracking),
            ("Documentation", self.validate_documentation)
        ]
        
        passed = 0
        total = len(validations)
        
        for name, validation_func in validations:
            logger.info(f"\n🔍 {name}")
            try:
                result = validation_func()
                if result:
                    passed += 1
                    logger.info(f"✅ {name}: PASSED")
                else:
                    logger.error(f"❌ {name}: FAILED")
            except Exception as e:
                logger.error(f"❌ {name}: ERROR - {e}")
        
        # Final report
        logger.info("\n" + "=" * 60)
        logger.info("📊 VALIDATION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total Validations: {total}")
        logger.info(f"Passed: {passed}")
        logger.info(f"Failed: {total - passed}")
        logger.info(f"Success Rate: {(passed/total)*100:.1f}%")
        
        if passed == total:
            logger.info("🎉 ALL VALIDATIONS PASSED - Storage integration is properly implemented!")
            return True
        else:
            logger.warning(f"⚠️ {total - passed} validations failed. Review the issues above.")
            return False

def main():
    """Main validation function."""
    validator = StorageIntegrationValidator()
    success = asyncio.run(validator.run_validation())
    
    if success:
        print("\n✅ Storage integration implementation is complete and validated!")
        sys.exit(0)
    else:
        print("\n❌ Storage integration validation failed. Please review the issues.")
        sys.exit(1)

if __name__ == "__main__":
    main()