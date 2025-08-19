#!/usr/bin/env python3
"""
URGENT Cola Project FAL URL Migration
====================================

This script immediately migrates the 6 specific Cola project generations 
with Fal URLs to Supabase Storage as identified in the task.

Targets:
- User: 23f370b8-5d53-4640-8c36-8b5f499abe70 (demo@example.com)
- Project: 18c021d8-b530-4a46-a9b0-f61fe309c146 (cola)
- 6 specific generations with Fal URLs

Usage:
    python3 cola_migration_urgent.py
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from typing import List, Dict, Any
import httpx

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'cola_migration_urgent_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Cola project specifics from the task
COLA_USER_ID = "23f370b8-5d53-4640-8c36-8b5f499abe70"
COLA_PROJECT_ID = "18c021d8-b530-4a46-a9b0-f61fe309c146"

# Specific generation IDs to migrate
COLA_GENERATIONS = [
    "6200b390-20d9-47ac-9499-9a9feb8b2ad0",  # lion image
    "4dc5f615-1c30-49e6-860b-93c3208002c8",  # elephant image  
    "8cf2aab8-1724-4c3f-8fae-bc079ae79dac",  # zebra image
    "13f98a40-c24d-441f-9f3f-c613f9a7e684",  # elephant image
    "6b61dcf5-7313-44a1-9e98-563d012d59f2",  # koala image
    "26e28951-0b19-46b1-bd12-18813742fa93"   # zebra image
]

class ColaUrgentMigrator:
    """Urgent migration tool for Cola project FAL URLs."""
    
    def __init__(self):
        self.db = None
        self.results = {
            'migration_timestamp': datetime.utcnow().isoformat(),
            'target_user_id': COLA_USER_ID,
            'target_project_id': COLA_PROJECT_ID,
            'target_generations': COLA_GENERATIONS,
            'generations_processed': 0,
            'generations_migrated': 0,
            'total_fal_urls_found': 0,
            'total_files_migrated': 0,
            'migration_details': [],
            'errors': []
        }
    
    async def initialize_database(self):
        """Initialize database connection."""
        try:
            from database import get_database
            self.db = await get_database()
            logger.info("✅ Database connection established")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize database: {e}")
            self.results['errors'].append(f"Database initialization failed: {str(e)}")
            return False
    
    async def get_generation_with_fal_urls(self, generation_id: str) -> Dict[str, Any]:
        """Get a specific generation and check for FAL URLs."""
        try:
            logger.info(f"🔍 Checking generation {generation_id} for FAL URLs...")
            
            # Query the generation from database
            result = self.db.execute_query(
                table="generations",
                operation="select",
                filters={"id": generation_id, "user_id": COLA_USER_ID},
                use_service_key=True,
                limit=1
            )
            
            if not result:
                logger.warning(f"⚠️ Generation {generation_id} not found")
                return None
            
            generation_data = result[0]
            fal_urls = []
            
            # Check media_url for FAL URL
            if generation_data.get('media_url') and 'fal.media' in generation_data['media_url']:
                fal_urls.append(generation_data['media_url'])
                logger.info(f"📸 Found FAL URL in media_url: {generation_data['media_url'][:100]}...")
            
            # Check output_urls for FAL URLs
            if generation_data.get('output_urls'):
                for url in generation_data['output_urls']:
                    if url and 'fal.media' in url:
                        fal_urls.append(url)
                        logger.info(f"📸 Found FAL URL in output_urls: {url[:100]}...")
            
            if fal_urls:
                logger.info(f"🎯 Generation {generation_id} has {len(fal_urls)} FAL URLs to migrate")
                return {
                    'id': generation_id,
                    'user_id': COLA_USER_ID,
                    'project_id': COLA_PROJECT_ID,
                    'fal_urls': fal_urls,
                    'current_media_url': generation_data.get('media_url'),
                    'current_output_urls': generation_data.get('output_urls', []),
                    'status': generation_data.get('status'),
                    'prompt_text': generation_data.get('prompt_text', '')[:100]
                }
            else:
                logger.info(f"ℹ️ Generation {generation_id} has no FAL URLs")
                return None
                
        except Exception as e:
            logger.error(f"❌ Failed to get generation {generation_id}: {e}")
            self.results['errors'].append(f"Failed to get generation {generation_id}: {str(e)}")
            return None
    
    async def download_fal_url(self, url: str) -> bytes:
        """Download image from FAL URL."""
        try:
            logger.info(f"⬇️ Downloading from FAL: {url[:100]}...")
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    timeout=60.0,
                    follow_redirects=True,
                    headers={
                        'User-Agent': 'Velro-Migration/1.0',
                        'Accept': 'image/*'
                    }
                )
                response.raise_for_status()
                
                content = response.content
                logger.info(f"✅ Downloaded {len(content)} bytes from FAL")
                
                # Validate minimum file size
                if len(content) < 1000:  # Less than 1KB is suspicious
                    raise ValueError(f"Downloaded file is too small ({len(content)} bytes)")
                
                return content
                
        except Exception as e:
            logger.error(f"❌ Failed to download from FAL URL {url}: {e}")
            raise
    
    async def upload_to_supabase_storage(self, generation_id: str, file_data: bytes, original_url: str) -> str:
        """Upload file to Supabase Storage and return the signed URL."""
        try:
            logger.info(f"☁️ Uploading to Supabase Storage for generation {generation_id}...")
            
            # Import storage service
            from services.storage_service import StorageService
            from models.storage import FileUploadRequest, StorageBucket, ContentType
            from uuid import UUID
            
            storage_service = StorageService()
            
            # Detect file type
            if file_data.startswith(b'\xff\xd8\xff'):
                content_type = ContentType.JPEG
                extension = "jpg"
            elif file_data.startswith(b'\x89PNG'):
                content_type = ContentType.PNG
                extension = "png"
            else:
                content_type = ContentType.JPEG  # Default
                extension = "jpg"
            
            # Create upload request
            filename = f"migration_{generation_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{extension}"
            
            upload_request = FileUploadRequest(
                bucket_name=StorageBucket.GENERATIONS,
                filename=filename,
                content_type=content_type,
                file_size=len(file_data),
                generation_id=UUID(generation_id),
                project_id=UUID(COLA_PROJECT_ID),
                metadata={
                    "source": "fal_migration",
                    "original_fal_url": original_url,
                    "migration_timestamp": datetime.utcnow().isoformat(),
                    "project_id": COLA_PROJECT_ID,
                    "is_migrated": True
                }
            )
            
            # Upload file
            file_metadata = await storage_service.upload_file(
                user_id=UUID(COLA_USER_ID),
                file_data=file_data,
                upload_request=upload_request,
                generation_id=UUID(generation_id)
            )
            
            # Generate signed URL
            signed_url_response = await storage_service.get_signed_url(
                file_id=file_metadata.id,
                user_id=UUID(COLA_USER_ID),
                expires_in=86400 * 365  # 1 year for long-term access
            )
            
            logger.info(f"✅ File uploaded to Supabase Storage: {file_metadata.file_path}")
            logger.info(f"🔗 Generated signed URL: {signed_url_response.signed_url[:100]}...")
            
            return signed_url_response.signed_url
            
        except Exception as e:
            logger.error(f"❌ Failed to upload to Supabase Storage: {e}")
            raise
    
    async def update_generation_urls(self, generation_id: str, new_urls: List[str]):
        """Update generation record with new Supabase Storage URLs."""
        try:
            logger.info(f"📝 Updating generation {generation_id} with new URLs...")
            
            # Update the generation record
            update_data = {
                'media_url': new_urls[0] if new_urls else None,
                'output_urls': new_urls,
                'metadata': {
                    'migrated_from_fal': True,
                    'migration_timestamp': datetime.utcnow().isoformat(),
                    'migration_status': 'completed',
                    'storage_type': 'supabase',
                    'files_migrated': len(new_urls)
                }
            }
            
            # Use repository to update
            from repositories.generation_repository import GenerationRepository
            generation_repo = GenerationRepository(self.db)
            
            await generation_repo.update_generation(generation_id, update_data)
            
            logger.info(f"✅ Generation {generation_id} updated with {len(new_urls)} new URLs")
            
        except Exception as e:
            logger.error(f"❌ Failed to update generation {generation_id}: {e}")
            raise
    
    async def migrate_generation(self, generation_data: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate a single generation from FAL URLs to Supabase Storage."""
        generation_id = generation_data['id']
        fal_urls = generation_data['fal_urls']
        
        logger.info(f"🚀 Starting migration for generation {generation_id}")
        logger.info(f"📊 Processing {len(fal_urls)} FAL URLs")
        
        migration_result = {
            'generation_id': generation_id,
            'original_fal_urls': fal_urls,
            'new_supabase_urls': [],
            'files_migrated': 0,
            'success': False,
            'error': None
        }
        
        try:
            new_urls = []
            
            for i, fal_url in enumerate(fal_urls):
                logger.info(f"📥 Processing FAL URL {i+1}/{len(fal_urls)}: {fal_url[:100]}...")
                
                try:
                    # Download from FAL
                    file_data = await self.download_fal_url(fal_url)
                    
                    # Upload to Supabase Storage
                    supabase_url = await self.upload_to_supabase_storage(generation_id, file_data, fal_url)
                    
                    new_urls.append(supabase_url)
                    migration_result['files_migrated'] += 1
                    
                    logger.info(f"✅ Successfully migrated URL {i+1}: FAL -> Supabase")
                    
                except Exception as e:
                    logger.error(f"❌ Failed to migrate URL {fal_url}: {e}")
                    continue
            
            if new_urls:
                # Update generation with new URLs
                await self.update_generation_urls(generation_id, new_urls)
                
                migration_result.update({
                    'new_supabase_urls': new_urls,
                    'success': True
                })
                
                logger.info(f"🎉 Migration completed for generation {generation_id}: {len(new_urls)} files migrated")
            else:
                migration_result['error'] = "No files were successfully migrated"
                logger.error(f"❌ Migration failed for generation {generation_id}: No files migrated")
            
            return migration_result
            
        except Exception as e:
            error_msg = f"Migration failed for generation {generation_id}: {str(e)}"
            logger.error(f"❌ {error_msg}")
            migration_result.update({
                'success': False,
                'error': error_msg
            })
            return migration_result
    
    async def run_urgent_migration(self) -> Dict[str, Any]:
        """Run the urgent migration for all Cola project generations."""
        logger.info("🚨 STARTING URGENT COLA PROJECT MIGRATION")
        logger.info(f"🎯 Target User: {COLA_USER_ID}")
        logger.info(f"🎯 Target Project: {COLA_PROJECT_ID}")
        logger.info(f"🎯 Target Generations: {len(COLA_GENERATIONS)}")
        
        try:
            # Initialize database
            if not await self.initialize_database():
                return self.results
            
            # Process each generation
            for generation_id in COLA_GENERATIONS:
                logger.info(f"📍 Processing generation {generation_id}...")
                
                try:
                    # Get generation data with FAL URLs
                    generation_data = await self.get_generation_with_fal_urls(generation_id)
                    
                    if not generation_data:
                        logger.info(f"⏭️ Skipping generation {generation_id} (no FAL URLs)")
                        continue
                    
                    self.results['generations_processed'] += 1
                    self.results['total_fal_urls_found'] += len(generation_data['fal_urls'])
                    
                    # Migrate the generation
                    migration_result = await self.migrate_generation(generation_data)
                    self.results['migration_details'].append(migration_result)
                    
                    if migration_result['success']:
                        self.results['generations_migrated'] += 1
                        self.results['total_files_migrated'] += migration_result['files_migrated']
                        logger.info(f"✅ Generation {generation_id} migration completed successfully")
                    else:
                        logger.error(f"❌ Generation {generation_id} migration failed")
                        self.results['errors'].append(migration_result['error'])
                    
                except Exception as e:
                    error_msg = f"Failed to process generation {generation_id}: {str(e)}"
                    logger.error(f"❌ {error_msg}")
                    self.results['errors'].append(error_msg)
                    continue
            
            # Final results
            logger.info("🎉 URGENT COLA PROJECT MIGRATION COMPLETED")
            logger.info(f"📊 Summary:")
            logger.info(f"   - Generations processed: {self.results['generations_processed']}")
            logger.info(f"   - Generations migrated: {self.results['generations_migrated']}")
            logger.info(f"   - Total FAL URLs found: {self.results['total_fal_urls_found']}")
            logger.info(f"   - Total files migrated: {self.results['total_files_migrated']}")
            logger.info(f"   - Errors: {len(self.results['errors'])}")
            
            self.results['success'] = self.results['generations_migrated'] > 0
            return self.results
            
        except Exception as e:
            error_msg = f"Critical migration failure: {str(e)}"
            logger.error(f"❌ {error_msg}")
            self.results['errors'].append(error_msg)
            self.results['success'] = False
            return self.results


async def main():
    """Main migration entry point."""
    migrator = ColaUrgentMigrator()
    
    try:
        # Run the urgent migration
        results = await migrator.run_urgent_migration()
        
        # Save results
        report_file = f'cola_migration_urgent_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(report_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        logger.info(f"📋 Migration report saved to: {report_file}")
        
        # Print final status
        if results.get('success', False):
            print("🎉 COLA PROJECT MIGRATION SUCCESSFUL!")
            print(f"   - {results['generations_migrated']} generations migrated")
            print(f"   - {results['total_files_migrated']} files moved to Supabase Storage")
        else:
            print("❌ COLA PROJECT MIGRATION FAILED!")
            print(f"   - {len(results['errors'])} errors occurred")
        
        return 0 if results.get('success', False) else 1
        
    except Exception as e:
        logger.error(f"❌ Script execution failed: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)