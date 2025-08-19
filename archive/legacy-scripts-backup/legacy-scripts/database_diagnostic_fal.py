#!/usr/bin/env python3
"""
Database Diagnostic for FAL URL Migration
========================================

This script diagnoses database connectivity and checks for generations
to understand why the FAL migration script is not finding any data.
"""

import asyncio
import logging
import sys
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    from database import get_database
    from config import settings
    logger.info("✅ Successfully imported backend services")
except ImportError as e:
    logger.error(f"❌ Failed to import backend services: {e}")
    sys.exit(1)


async def diagnostic_check():
    """Run comprehensive database diagnostic."""
    
    print("🔧 DATABASE DIAGNOSTIC FOR FAL URL MIGRATION")
    print("=" * 60)
    
    try:
        # Step 1: Initialize database
        logger.info("🔧 Initializing database connection...")
        db = await get_database()
        logger.info("✅ Database initialized successfully")
        
        # Step 2: Check database configuration
        print(f"\n📊 DATABASE CONFIGURATION:")
        print(f"   Supabase URL: {settings.supabase_url}")
        print(f"   Anon Key Length: {len(settings.supabase_anon_key)}")
        print(f"   Service Key Length: {len(settings.supabase_service_role_key) if settings.supabase_service_role_key else 0}")
        print(f"   Service Key Valid: {db._service_key_valid}")
        
        # Step 3: Check database availability
        is_available = db.is_available()
        print(f"   Database Available: {is_available}")
        
        if not is_available:
            print("❌ Database is not available - stopping diagnostic")
            return
        
        # Step 4: Test basic queries with different access methods
        print(f"\n🔍 TESTING DATABASE ACCESS:")
        
        # Try with service key
        try:
            logger.info("Testing service key access...")
            result_service = db.execute_query(
                table="generations",
                operation="select",
                use_service_key=True,
                limit=5
            )
            print(f"   Service Key Access: ✅ Found {len(result_service)} generations")
            
            if result_service:
                sample = result_service[0]
                print(f"   Sample Generation ID: {sample.get('id', 'N/A')}")
                print(f"   Sample User ID: {sample.get('user_id', 'N/A')}")
                print(f"   Sample Project ID: {sample.get('project_id', 'N/A')}")
                print(f"   Sample Media URL: {sample.get('media_url', 'N/A')[:100]}...")
                print(f"   Sample Output URLs: {len(sample.get('output_urls', []))} URLs")
                
        except Exception as e:
            print(f"   Service Key Access: ❌ Failed - {e}")
            
        # Try with anon key
        try:
            logger.info("Testing anon key access...")
            result_anon = db.execute_query(
                table="generations",
                operation="select",
                use_service_key=False,
                limit=5
            )
            print(f"   Anon Key Access: ✅ Found {len(result_anon)} generations")
        except Exception as e:
            print(f"   Anon Key Access: ❌ Failed - {e}")
        
        # Step 5: Check for FAL URLs specifically
        print(f"\n🔍 CHECKING FOR FAL URLs:")
        
        try:
            # Get all generations and check for FAL URLs
            all_generations = db.execute_query(
                table="generations",
                operation="select",
                use_service_key=True,
                order_by="created_at:desc",
                limit=100
            )
            
            print(f"   Total Generations Found: {len(all_generations)}")
            
            fal_count = 0
            fal_examples = []
            project_ids = set()
            
            for gen in all_generations:
                project_ids.add(gen.get('project_id'))
                
                has_fal = False
                if gen.get('media_url') and 'fal.media' in gen.get('media_url'):
                    has_fal = True
                    fal_examples.append(gen.get('media_url'))
                
                if gen.get('output_urls'):
                    for url in gen.get('output_urls', []):
                        if url and 'fal.media' in url:
                            has_fal = True
                            fal_examples.append(url)
                
                if has_fal:
                    fal_count += 1
            
            print(f"   Generations with FAL URLs: {fal_count}")
            print(f"   Unique Project IDs: {len(project_ids)}")
            print(f"   Project IDs: {list(project_ids)[:10]}")  # Show first 10
            
            if fal_examples:
                print(f"   Example FAL URLs found:")
                for i, url in enumerate(fal_examples[:5], 1):
                    print(f"      {i}. {url}")
            
        except Exception as e:
            print(f"   FAL URL Check: ❌ Failed - {e}")
        
        # Step 6: Check Cola project specifically
        print(f"\n🥤 COLA PROJECT SPECIFIC CHECK:")
        cola_project_id = "18c021d8-b530-4a46-a9b0-f61fe309c146"
        
        try:
            cola_generations = db.execute_query(
                table="generations",
                operation="select",
                filters={"project_id": cola_project_id},
                use_service_key=True,
                limit=10
            )
            
            print(f"   Cola Project Generations: {len(cola_generations)}")
            
            if cola_generations:
                for i, gen in enumerate(cola_generations, 1):
                    media_url = gen.get('media_url', '')
                    output_urls = gen.get('output_urls', [])
                    has_fal = 'fal.media' in media_url or any('fal.media' in url for url in output_urls if url)
                    
                    print(f"   Gen {i}: ID={gen.get('id')}, FAL URLs={has_fal}")
                    if has_fal:
                        if 'fal.media' in media_url:
                            print(f"      Media URL: {media_url}")
                        for url in output_urls:
                            if url and 'fal.media' in url:
                                print(f"      Output URL: {url}")
            
        except Exception as e:
            print(f"   Cola Project Check: ❌ Failed - {e}")
        
        # Step 7: Check other tables
        print(f"\n📊 OTHER TABLE CHECKS:")
        
        for table in ['users', 'projects', 'credit_transactions']:
            try:
                result = db.execute_query(
                    table=table,
                    operation="select",
                    use_service_key=True,
                    limit=1
                )
                print(f"   Table '{table}': ✅ {len(result)} records")
            except Exception as e:
                print(f"   Table '{table}': ❌ {e}")
        
        print(f"\n🎉 DATABASE DIAGNOSTIC COMPLETED")
        
    except Exception as e:
        logger.error(f"❌ Diagnostic failed: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Main diagnostic function."""
    await diagnostic_check()


if __name__ == "__main__":
    asyncio.run(main())