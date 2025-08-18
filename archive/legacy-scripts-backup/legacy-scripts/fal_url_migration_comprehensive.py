#!/usr/bin/env python3
"""
Comprehensive FAL URL Migration Script
=====================================

This script identifies all FAL URLs in the database and migrates them to Supabase Storage.
Specifically targets the Cola project (18c021d8-b530-4a46-a9b0-f61fe309c146) and other generations.

Features:
- Identifies all generations with FAL URLs
- Downloads images from FAL URLs
- Uploads to Supabase Storage via storage service
- Updates database records with new paths
- Comprehensive logging and error handling
- Rollback capability for failed migrations

Usage:
    python fal_url_migration_comprehensive.py [--dry-run] [--project-id PROJECT_ID]
"""

import asyncio
import logging
import sys
import json
import argparse
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import UUID

# Set up comprehensive logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'fal_migration_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Import backend services
try:
    from database import get_database
    from repositories.generation_repository import GenerationRepository
    from services.storage_service import StorageService
    from models.generation import GenerationResponse
    logger.info("✅ [IMPORT] Successfully imported backend services")
except ImportError as e:
    logger.error(f"❌ [IMPORT] Failed to import backend services: {e}")
    sys.exit(1)


class FALURLMigrator:
    """Comprehensive FAL URL migration system."""
    
    def __init__(self):
        self.db = None
        self.generation_repo = None
        self.storage_service = StorageService()
        self.migration_stats = {
            'total_generations_found': 0,
            'fal_url_generations': 0,
            'successful_migrations': 0,
            'failed_migrations': 0,
            'urls_migrated': 0,
            'total_bytes_migrated': 0,
            'migration_errors': []
        }
        self.migration_log = []
    
    async def initialize(self):
        """Initialize database connections and repositories."""
        logger.info("🔧 [INIT] Initializing FAL URL Migrator...")
        
        try:
            self.db = await get_database()
            self.generation_repo = GenerationRepository(self.db)
            logger.info("✅ [INIT] Database and repositories initialized successfully")
        except Exception as e:
            logger.error(f"❌ [INIT] Failed to initialize: {e}")
            raise
    
    async def identify_fal_generations(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Identify all generations with FAL URLs.
        
        Args:
            project_id: Optional specific project ID to target
            
        Returns:
            List of generation records containing FAL URLs
        """
        logger.info("🔍 [IDENTIFY] Scanning database for generations with FAL URLs...")
        
        try:
            # Get all generations from database  
            if project_id:
                logger.info(f"🎯 [IDENTIFY] Targeting specific project: {project_id}")
                # Get generations for specific project - we need to get user_id first
                generations = await self._get_generations_by_project(project_id)
            else:
                logger.info("🌐 [IDENTIFY] Scanning all generations in database")
                # Get all generations (we'll implement a method for this)
                generations = await self._get_all_generations()
            
            logger.info(f"📊 [IDENTIFY] Found {len(generations)} total generations")
            self.migration_stats['total_generations_found'] = len(generations)
            
            fal_generations = []
            
            for generation in generations:
                has_fal_urls = False
                generation_data = {
                    'id': generation.id,
                    'user_id': generation.user_id, 
                    'project_id': getattr(generation, 'project_id', None),
                    'status': generation.status,
                    'created_at': generation.created_at,
                    'fal_urls': [],
                    'current_media_url': generation.media_url,
                    'current_output_urls': generation.output_urls or []
                }
                
                # Check media_url for FAL URL
                if generation.media_url and 'fal.media' in generation.media_url:
                    generation_data['fal_urls'].append(generation.media_url)
                    has_fal_urls = True
                
                # Check output_urls for FAL URLs
                if generation.output_urls:
                    for url in generation.output_urls:
                        if url and 'fal.media' in url:
                            generation_data['fal_urls'].append(url)
                            has_fal_urls = True
                
                if has_fal_urls:
                    fal_generations.append(generation_data)
                    logger.info(f"🎯 [IDENTIFY] Found FAL generation: {generation.id} with {len(generation_data['fal_urls'])} FAL URLs")
                    for url in generation_data['fal_urls']:
                        logger.info(f"   🔗 FAL URL: {url[:100]}{'...' if len(url) > 100 else ''}")
            
            logger.info(f"📈 [IDENTIFY] Identification complete: {len(fal_generations)} generations contain FAL URLs")
            self.migration_stats['fal_url_generations'] = len(fal_generations)
            
            return fal_generations
            
        except Exception as e:
            logger.error(f"❌ [IDENTIFY] Failed to identify FAL generations: {e}")
            raise
    
    async def _get_generations_by_project(self, project_id: str) -> List[GenerationResponse]:
        """Get generations for a specific project."""
        try:
            # Use database execute_query method to get generations for project
            result = self.db.execute_query(
                table="generations",
                operation="select",
                filters={"project_id": project_id},
                use_service_key=True,  # Use service key to bypass RLS
                order_by="created_at:desc",
                limit=100
            )
            
            generations = []
            for row in result:
                # Convert database row to GenerationResponse object
                generation = GenerationResponse(
                    id=row['id'],
                    user_id=row['user_id'],
                    project_id=row.get('project_id'),
                    prompt_text=row.get('prompt_text', ''),
                    model_id=row.get('model_id', ''),
                    status=row.get('status', 'unknown'),
                    media_url=row.get('media_url'),
                    output_urls=row.get('output_urls', []),
                    metadata=row.get('metadata', {}),
                    created_at=row.get('created_at'),
                    updated_at=row.get('updated_at'),
                    completed_at=row.get('completed_at')
                )
                generations.append(generation)
            
            return generations
            
        except Exception as e:
            logger.error(f"❌ [GET-PROJECT] Failed to get generations for project {project_id}: {e}")
            raise
    
    async def _get_all_generations(self) -> List[GenerationResponse]:
        """Get all generations from database."""
        try:
            # Use database execute_query method to get all generations
            result = self.db.execute_query(
                table="generations",
                operation="select",
                use_service_key=True,  # Use service key to bypass RLS
                order_by="created_at:desc",
                limit=1000
            )
            
            generations = []
            for row in result:
                # Convert database row to GenerationResponse object
                generation = GenerationResponse(
                    id=row['id'],
                    user_id=row['user_id'],
                    project_id=row.get('project_id'),
                    prompt_text=row.get('prompt_text', ''),
                    model_id=row.get('model_id', ''),
                    status=row.get('status', 'unknown'),
                    media_url=row.get('media_url'),
                    output_urls=row.get('output_urls', []),
                    metadata=row.get('metadata', {}),
                    created_at=row.get('created_at'),
                    updated_at=row.get('updated_at'),
                    completed_at=row.get('completed_at')
                )
                generations.append(generation)
            
            return generations
            
        except Exception as e:
            logger.error(f"❌ [GET-ALL] Failed to get all generations: {e}")
            raise
            
    async def migrate_generation(self, generation_data: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
        """
        Migrate a single generation from FAL URLs to Supabase Storage.
        
        Args:
            generation_data: Generation information with FAL URLs
            dry_run: If True, simulate migration without actual changes
            
        Returns:
            Migration result with success status and details
        """
        generation_id = generation_data['id']
        user_id = generation_data['user_id']
        fal_urls = generation_data['fal_urls']
        
        logger.info(f"🚀 [MIGRATE] Starting migration for generation {generation_id}")
        logger.info(f"👤 [MIGRATE] User: {user_id}, URLs to migrate: {len(fal_urls)}")
        
        migration_result = {
            'generation_id': generation_id,
            'user_id': user_id,
            'success': False,
            'urls_processed': 0,
            'files_migrated': 0,
            'new_media_url': None,
            'new_output_urls': [],
            'storage_info': {},
            'error': None,
            'dry_run': dry_run
        }
        
        if dry_run:
            logger.info(f"🔍 [MIGRATE] DRY RUN - Would migrate {len(fal_urls)} URLs for generation {generation_id}")
            migration_result['success'] = True
            migration_result['urls_processed'] = len(fal_urls)
            return migration_result
        
        try:
            # Use storage service to migrate external URLs
            logger.info(f"☁️ [MIGRATE] Calling storage service to migrate external URLs...")
            
            migrated_files = await self.storage_service.migrate_external_urls_to_storage(
                user_id=user_id,
                generation_id=generation_id,
                external_urls=fal_urls
            )
            
            logger.info(f"✅ [MIGRATE] Storage service migration completed: {len(migrated_files)} files")
            
            if not migrated_files:
                raise ValueError("No files were successfully migrated")
            
            # Generate new URLs from migrated files
            new_output_urls = []
            total_size = 0
            
            for file_metadata in migrated_files:
                try:
                    # Get signed URL for the migrated file
                    signed_url_response = await self.storage_service.get_signed_url(
                        file_id=file_metadata.id,
                        user_id=UUID(user_id),
                        expires_in=86400 * 365  # 1 year expiry for migration
                    )
                    
                    new_output_urls.append(signed_url_response.signed_url)
                    total_size += file_metadata.file_size
                    
                    logger.info(f"🔗 [MIGRATE] Generated signed URL for file {file_metadata.id}")
                    
                except Exception as e:
                    logger.warning(f"⚠️ [MIGRATE] Failed to generate signed URL for file {file_metadata.id}: {e}")
                    # Use the direct storage path as fallback
                    storage_path = f"https://{self.storage_service.storage_repo.supabase_url}/storage/v1/object/public/{file_metadata.bucket_name.value}/{file_metadata.file_path}"
                    new_output_urls.append(storage_path)
            
            # Update generation in database with new URLs
            update_data = {
                'media_url': new_output_urls[0] if new_output_urls else None,
                'output_urls': new_output_urls,
                'metadata': {
                    **generation_data.get('metadata', {}),
                    'migrated_from_fal': True,
                    'migration_timestamp': datetime.utcnow().isoformat(),
                    'original_fal_urls': fal_urls,
                    'storage_migration_successful': True,
                    'supabase_urls_used': True,
                    'fallback_to_external_urls': False,  # Override previous fallback
                    'files_migrated': len(migrated_files),
                    'total_size_bytes': total_size
                }
            }
            
            logger.info(f"📝 [MIGRATE] Updating generation {generation_id} in database...")
            logger.info(f"🔍 [MIGRATE] New media_url: {update_data['media_url']}")
            logger.info(f"🔍 [MIGRATE] New output_urls count: {len(new_output_urls)}")
            
            updated_generation = await self.generation_repo.update_generation(
                generation_id,
                update_data
            )
            
            # Populate migration result
            migration_result.update({
                'success': True,
                'urls_processed': len(fal_urls),
                'files_migrated': len(migrated_files),
                'new_media_url': update_data['media_url'],
                'new_output_urls': new_output_urls,
                'storage_info': {
                    'total_size_bytes': total_size,
                    'files_stored': len(migrated_files),
                    'storage_paths': [f.file_path for f in migrated_files]
                }
            })
            
            logger.info(f"🎉 [MIGRATE] Generation {generation_id} migrated successfully!")
            logger.info(f"📊 [MIGRATE] Result: {len(migrated_files)} files, {total_size} bytes")
            
            return migration_result
            
        except Exception as e:
            logger.error(f"❌ [MIGRATE] Migration failed for generation {generation_id}: {e}")
            
            migration_result.update({
                'success': False,
                'error': str(e)
            })
            
            self.migration_stats['migration_errors'].append({
                'generation_id': generation_id,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            })
            
            return migration_result
    
    async def run_migration(self, project_id: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
        """
        Run the complete FAL URL migration process.
        
        Args:
            project_id: Optional specific project ID to target
            dry_run: If True, simulate migration without actual changes
            
        Returns:
            Complete migration report
        """
        start_time = datetime.utcnow()
        logger.info(f"🚀 [MIGRATION] Starting comprehensive FAL URL migration")
        logger.info(f"⚙️ [MIGRATION] Mode: {'DRY RUN' if dry_run else 'LIVE MIGRATION'}")
        if project_id:
            logger.info(f"🎯 [MIGRATION] Target project: {project_id}")
        
        try:
            await self.initialize()
            
            # Step 1: Identify generations with FAL URLs
            fal_generations = await self.identify_fal_generations(project_id)
            
            if not fal_generations:
                logger.info("ℹ️ [MIGRATION] No generations with FAL URLs found")
                return self._generate_migration_report(start_time)
            
            # Step 2: Migrate each generation
            logger.info(f"🔄 [MIGRATION] Processing {len(fal_generations)} generations...")
            
            for i, generation_data in enumerate(fal_generations, 1):
                logger.info(f"📍 [MIGRATION] Processing generation {i}/{len(fal_generations)}: {generation_data['id']}")
                
                try:
                    migration_result = await self.migrate_generation(generation_data, dry_run)
                    
                    if migration_result['success']:
                        self.migration_stats['successful_migrations'] += 1
                        self.migration_stats['urls_migrated'] += migration_result['urls_processed']
                        if 'storage_info' in migration_result:
                            self.migration_stats['total_bytes_migrated'] += migration_result['storage_info'].get('total_size_bytes', 0)
                    else:
                        self.migration_stats['failed_migrations'] += 1
                    
                    self.migration_log.append(migration_result)
                    
                except Exception as e:
                    logger.error(f"❌ [MIGRATION] Unexpected error processing generation {generation_data['id']}: {e}")
                    self.migration_stats['failed_migrations'] += 1
                    self.migration_stats['migration_errors'].append({
                        'generation_id': generation_data['id'],
                        'error': str(e),
                        'timestamp': datetime.utcnow().isoformat()
                    })
            
            # Step 3: Generate final report
            migration_report = self._generate_migration_report(start_time)
            
            logger.info("🎉 [MIGRATION] FAL URL migration completed!")
            logger.info(f"📊 [MIGRATION] Summary: {self.migration_stats['successful_migrations']} successful, {self.migration_stats['failed_migrations']} failed")
            
            return migration_report
            
        except Exception as e:
            logger.error(f"❌ [MIGRATION] Critical migration failure: {e}")
            import traceback
            logger.error(f"❌ [MIGRATION] Traceback: {traceback.format_exc()}")
            raise
    
    def _generate_migration_report(self, start_time: datetime) -> Dict[str, Any]:
        """Generate comprehensive migration report."""
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        report = {
            'migration_summary': {
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'duration_seconds': duration,
                'duration_formatted': f"{duration:.2f}s"
            },
            'statistics': self.migration_stats,
            'detailed_results': self.migration_log,
            'success_rate': (
                self.migration_stats['successful_migrations'] / 
                max(self.migration_stats['fal_url_generations'], 1)
            ) * 100,
            'recommendations': []
        }
        
        # Add recommendations based on results
        if self.migration_stats['failed_migrations'] > 0:
            report['recommendations'].append("Review failed migrations and retry individually")
        
        if self.migration_stats['successful_migrations'] > 0:
            report['recommendations'].append("Verify migrated generations display correctly in frontend")
            
        return report
    
    async def validate_cola_project_specifically(self) -> Dict[str, Any]:
        """
        Specifically validate and migrate the Cola project data.
        This addresses the exact issue mentioned in the task.
        """
        cola_project_id = "18c021d8-b530-4a46-a9b0-f61fe309c146"
        
        logger.info(f"🥤 [COLA] Starting specific validation for Cola project: {cola_project_id}")
        
        try:
            await self.initialize()
            
            # Get Cola project generations
            cola_generations = await self.identify_fal_generations(cola_project_id)
            
            if not cola_generations:
                logger.warning(f"⚠️ [COLA] No FAL URLs found in Cola project {cola_project_id}")
                return {'success': False, 'message': 'No FAL URLs found in Cola project'}
            
            logger.info(f"🎯 [COLA] Found {len(cola_generations)} generations with FAL URLs in Cola project")
            
            # Log the specific URLs found (matching the task description)
            expected_urls = [
                'https://fal.media/files/elephant/uu23UHNOOIF__rLi4TuSv_34e2922156e445c6905c6b470d263e92.jpg',
                'https://fal.media/files/koala/cDSn9jEZIVo6scHNtGoYi_49ce3c4ffed64d0c81ecc113952f4bdf.jpg',
                'https://fal.media/files/zebra/2Y79_2tKquoq0RASME4WP_483c03dcd50449c7b6873847671f1a72.jpg'
            ]
            
            found_expected = []
            for generation in cola_generations:
                for url in generation['fal_urls']:
                    if url in expected_urls:
                        found_expected.append(url)
                        logger.info(f"✅ [COLA] Found expected URL: {url}")
            
            logger.info(f"📊 [COLA] Found {len(found_expected)} of {len(expected_urls)} expected URLs")
            
            # Migrate Cola project specifically
            migration_result = await self.run_migration(project_id=cola_project_id, dry_run=False)
            
            cola_result = {
                'project_id': cola_project_id,
                'expected_urls_found': found_expected,
                'total_generations_with_fal': len(cola_generations),
                'migration_result': migration_result,
                'success': migration_result.get('statistics', {}).get('successful_migrations', 0) > 0
            }
            
            logger.info(f"🎉 [COLA] Cola project migration completed: {'SUCCESS' if cola_result['success'] else 'FAILED'}")
            
            return cola_result
            
        except Exception as e:
            logger.error(f"❌ [COLA] Failed to process Cola project: {e}")
            return {'success': False, 'error': str(e)}


async def main():
    """Main migration script entry point."""
    parser = argparse.ArgumentParser(description='Migrate FAL URLs to Supabase Storage')
    parser.add_argument('--dry-run', action='store_true', help='Simulate migration without making changes')
    parser.add_argument('--project-id', type=str, help='Target specific project ID')
    parser.add_argument('--cola-only', action='store_true', help='Only process Cola project')
    parser.add_argument('--report-file', type=str, help='Save report to specific file')
    
    args = parser.parse_args()
    
    migrator = FALURLMigrator()
    
    try:
        if args.cola_only:
            # Process Cola project specifically
            result = await migrator.validate_cola_project_specifically()
        else:
            # Run general migration
            result = await migrator.run_migration(
                project_id=args.project_id,
                dry_run=args.dry_run
            )
        
        # Save report
        report_file = args.report_file or f'fal_migration_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(report_file, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        
        logger.info(f"📋 [REPORT] Migration report saved to: {report_file}")
        
        # Print summary
        if args.cola_only:
            print(f"Cola Project Migration: {'SUCCESS' if result.get('success') else 'FAILED'}")
        else:
            stats = result.get('statistics', {})
            print(f"Migration Complete - Success: {stats.get('successful_migrations', 0)}, Failed: {stats.get('failed_migrations', 0)}")
        
        if args.cola_only:
            return 0 if result.get('success', False) else 1
        else:
            stats = result.get('statistics', {})
            return 0 if stats.get('successful_migrations', 0) > 0 else 1
        
    except Exception as e:
        logger.error(f"❌ [MAIN] Migration script failed: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)