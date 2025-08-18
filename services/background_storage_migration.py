"""
Background Storage Migration Service

Handles migration of generations with temporary Fal URLs to permanent Supabase Storage.
This service runs independently to avoid blocking user-facing generation creation.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import aiohttp
import json
from uuid import UUID

from models.generation import GenerationStatus
from repositories.generation_repository import GenerationRepository
from services.storage_service import StorageService
from database import get_database, SupabaseClient

logger = logging.getLogger(__name__)

class BackgroundStorageMigration:
    """Background service for migrating Fal URLs to Supabase Storage"""
    
    def __init__(self):
        self.db_client = get_database()
        self.generation_repo = GenerationRepository(self.db_client)
        self.storage_service = StorageService()
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def find_generations_needing_migration(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Find generations that need background storage migration"""
        try:
            # Use Supabase client to query generations needing migration
            response = (
                self.db_client.service_client
                .table('generations')
                .select('id, user_id, project_id, output_urls, metadata, media_url')
                .eq('status', 'COMPLETED')
                .eq('metadata->>storage_retry_needed', 'true')
                .eq('metadata->>fal_urls_temporary', 'true')
                .order('created_at', desc=True)
                .limit(limit)
                .execute()
            )
            
            generations = []
            if response.data:
                for row in response.data:
                    generations.append({
                        'id': str(row['id']),
                        'user_id': str(row['user_id']),
                        'project_id': str(row['project_id']) if row.get('project_id') else None,
                        'output_urls': row.get('output_urls', []),
                        'metadata': row.get('metadata', {}),
                        'media_url': row.get('media_url')
                    })
            
            logger.info(f"🔍 [MIGRATION] Found {len(generations)} generations needing storage migration")
            return generations
            
        except Exception as e:
            logger.error(f"❌ [MIGRATION] Error finding generations for migration: {e}")
            return []
    
    async def download_file_from_url(self, url: str) -> Optional[bytes]:
        """Download file content from Fal URL"""
        try:
            if not self.session:
                raise ValueError("Session not initialized")
                
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    content = await response.read()
                    logger.info(f"✅ [MIGRATION] Downloaded {len(content)} bytes from {url[:50]}...")
                    return content
                else:
                    logger.error(f"❌ [MIGRATION] Failed to download from {url}: HTTP {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"❌ [MIGRATION] Error downloading from {url}: {e}")
            return None
    
    async def migrate_generation_storage(self, generation: Dict[str, Any]) -> bool:
        """Migrate a single generation from Fal URLs to Supabase Storage"""
        generation_id = generation['id']
        user_id = generation['user_id']
        output_urls = generation.get('output_urls', [])
        
        if not output_urls:
            logger.warning(f"⚠️  [MIGRATION] No output URLs found for generation {generation_id}")
            return False
        
        try:
            logger.info(f"🔄 [MIGRATION] Starting migration for generation {generation_id}")
            
            migrated_urls = []
            migrated_files = []
            total_size = 0
            
            for i, fal_url in enumerate(output_urls):
                if not fal_url:
                    continue
                    
                # Download file from Fal URL
                file_content = await self.download_file_from_url(fal_url)
                if not file_content:
                    logger.error(f"❌ [MIGRATION] Failed to download file {i} for generation {generation_id}")
                    continue
                
                # Determine file extension from URL or default to png
                file_extension = 'png'
                if '.' in fal_url.split('/')[-1]:
                    file_extension = fal_url.split('/')[-1].split('.')[-1].lower()
                
                # Generate storage path
                file_name = f"generation_{generation_id}_{i}.{file_extension}"
                
                # Upload to Supabase Storage
                try:
                    storage_path = await self.storage_service.upload_file(
                        file_content=file_content,
                        file_name=file_name,
                        content_type=f'image/{file_extension}',
                        user_id=UUID(user_id)
                    )
                    
                    if storage_path:
                        # Get public URL
                        public_url = await self.storage_service.get_public_url(storage_path)
                        if public_url:
                            migrated_urls.append(public_url)
                            migrated_files.append({
                                'original_url': fal_url,
                                'storage_path': storage_path,
                                'public_url': public_url,
                                'size': len(file_content)
                            })
                            total_size += len(file_content)
                            logger.info(f"✅ [MIGRATION] Migrated file {i} to {storage_path}")
                        else:
                            logger.error(f"❌ [MIGRATION] Failed to get public URL for {storage_path}")
                    else:
                        logger.error(f"❌ [MIGRATION] Failed to upload file {i} to storage")
                        
                except Exception as upload_error:
                    logger.error(f"❌ [MIGRATION] Upload error for file {i}: {upload_error}")
                    continue
            
            if not migrated_urls:
                logger.error(f"❌ [MIGRATION] No files successfully migrated for generation {generation_id}")
                return False
            
            # Update generation with migrated URLs
            update_data = {
                "output_urls": migrated_urls,
                "media_url": migrated_urls[0] if migrated_urls else None,
                "metadata": {
                    **generation.get('metadata', {}),
                    "storage_retry_needed": False,
                    "fal_urls_temporary": False,
                    "storage_successful": True,
                    "supabase_urls_used": True,
                    "migration_completed_at": datetime.utcnow().isoformat(),
                    "migrated_files": migrated_files,
                    "total_migrated_size": total_size,
                    "migration_file_count": len(migrated_files)
                }
            }
            
            updated_generation = await self.generation_repo.update_generation(
                UUID(generation_id),
                update_data
            )
            
            logger.info(f"✅ [MIGRATION] Successfully migrated generation {generation_id}")
            logger.info(f"📊 [MIGRATION] Migrated {len(migrated_files)} files, {total_size} bytes total")
            return True
            
        except Exception as e:
            logger.error(f"❌ [MIGRATION] Failed to migrate generation {generation_id}: {e}")
            
            # Mark migration as failed in metadata
            try:
                update_data = {
                    "metadata": {
                        **generation.get('metadata', {}),
                        "migration_failed": True,
                        "migration_error": str(e),
                        "migration_failed_at": datetime.utcnow().isoformat()
                    }
                }
                await self.generation_repo.update_generation(UUID(generation_id), update_data)
            except Exception as meta_error:
                logger.error(f"❌ [MIGRATION] Failed to update migration failure metadata: {meta_error}")
            
            return False
    
    async def run_migration_batch(self, batch_size: int = 10) -> Dict[str, int]:
        """Run a batch of storage migrations"""
        try:
            generations = await self.find_generations_needing_migration(batch_size)
            
            if not generations:
                logger.info("🔍 [MIGRATION] No generations found needing migration")
                return {"processed": 0, "successful": 0, "failed": 0}
            
            successful = 0
            failed = 0
            
            # Process migrations with concurrency limit
            semaphore = asyncio.Semaphore(3)  # Limit concurrent migrations
            
            async def migrate_with_semaphore(generation):
                async with semaphore:
                    return await self.migrate_generation_storage(generation)
            
            # Run migrations concurrently
            results = await asyncio.gather(
                *[migrate_with_semaphore(gen) for gen in generations],
                return_exceptions=True
            )
            
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"❌ [MIGRATION] Migration exception: {result}")
                    failed += 1
                elif result:
                    successful += 1
                else:
                    failed += 1
            
            logger.info(f"📊 [MIGRATION] Batch complete: {successful} successful, {failed} failed")
            return {"processed": len(generations), "successful": successful, "failed": failed}
            
        except Exception as e:
            logger.error(f"❌ [MIGRATION] Error running migration batch: {e}")
            return {"processed": 0, "successful": 0, "failed": 0, "error": str(e)}
    
    async def run_continuous_migration(self, interval_seconds: int = 300, batch_size: int = 10):
        """Run continuous background migration with specified interval"""
        logger.info(f"🚀 [MIGRATION] Starting continuous migration service (interval: {interval_seconds}s)")
        
        while True:
            try:
                async with self:  # Use context manager for session handling
                    results = await self.run_migration_batch(batch_size)
                    
                    if results["processed"] > 0:
                        logger.info(f"✅ [MIGRATION] Processed {results['processed']} generations")
                    else:
                        logger.debug("🔍 [MIGRATION] No migrations needed, sleeping...")
                
                # Wait before next batch
                await asyncio.sleep(interval_seconds)
                
            except KeyboardInterrupt:
                logger.info("🛑 [MIGRATION] Migration service stopped by user")
                break
            except Exception as e:
                logger.error(f"❌ [MIGRATION] Error in continuous migration: {e}")
                await asyncio.sleep(interval_seconds)  # Wait before retry


# Standalone function for one-time migration
async def run_migration_once(batch_size: int = 50) -> Dict[str, int]:
    """Run migration once and return results"""
    async with BackgroundStorageMigration() as migration_service:
        return await migration_service.run_migration_batch(batch_size)


# CLI entry point
if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Background Storage Migration Service")
    parser.add_argument("--continuous", action="store_true", help="Run continuous migration")
    parser.add_argument("--interval", type=int, default=300, help="Interval between batches (seconds)")
    parser.add_argument("--batch-size", type=int, default=10, help="Number of generations per batch")
    parser.add_argument("--once", action="store_true", help="Run migration once and exit")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    async def main():
        if args.once:
            logger.info("🚀 [MIGRATION] Running one-time migration")
            results = await run_migration_once(args.batch_size)
            logger.info(f"📊 [MIGRATION] Results: {results}")
        elif args.continuous:
            migration_service = BackgroundStorageMigration()
            await migration_service.run_continuous_migration(args.interval, args.batch_size)
        else:
            print("Use --continuous for continuous migration or --once for one-time migration")
            sys.exit(1)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 [MIGRATION] Migration service terminated")