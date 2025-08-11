#!/usr/bin/env python3
"""
Find actual Cola project generations with FAL URLs
=================================================

This script searches the database to find the actual generations
for the Cola project that contain FAL URLs.
"""

import asyncio
import json
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Cola project specifics
COLA_USER_ID = "23f370b8-5d53-4640-8c36-8b5f499abe70"
COLA_PROJECT_ID = "18c021d8-b530-4a46-a9b0-f61fe309c146"

async def find_cola_fal_generations():
    """Find all generations with FAL URLs for the Cola project."""
    try:
        # Import database
        from database import get_database
        db = await get_database()
        
        logger.info("✅ Database connection established")
        logger.info(f"🔍 Searching for generations with FAL URLs...")
        logger.info(f"   - User ID: {COLA_USER_ID}")
        logger.info(f"   - Project ID: {COLA_PROJECT_ID}")
        
        # First, find all generations for this user
        logger.info("🔍 Step 1: Finding all generations for user...")
        all_generations = db.execute_query(
            table="generations",
            operation="select",
            filters={"user_id": COLA_USER_ID},
            use_service_key=True,
            limit=100
        )
        
        logger.info(f"📊 Found {len(all_generations)} total generations for user {COLA_USER_ID}")
        
        if not all_generations:
            logger.warning("⚠️ No generations found for this user")
            return
        
        # Check each generation for FAL URLs
        fal_generations = []
        
        for generation in all_generations:
            generation_id = generation.get('id')
            media_url = generation.get('media_url')
            output_urls = generation.get('output_urls', [])
            project_id = generation.get('project_id')
            
            fal_urls_found = []
            
            # Check media_url
            if media_url and 'fal.media' in media_url:
                fal_urls_found.append(media_url)
            
            # Check output_urls
            if output_urls:
                for url in output_urls:
                    if url and 'fal.media' in url:
                        fal_urls_found.append(url)
            
            if fal_urls_found:
                generation_info = {
                    'id': generation_id,
                    'user_id': generation.get('user_id'),
                    'project_id': project_id,
                    'status': generation.get('status'),
                    'created_at': generation.get('created_at'),
                    'prompt_text': generation.get('prompt_text', '')[:100],
                    'media_url': media_url,
                    'output_urls': output_urls,
                    'fal_urls_found': fal_urls_found,
                    'fal_url_count': len(fal_urls_found)
                }
                fal_generations.append(generation_info)
                
                logger.info(f"🎯 Found generation with FAL URLs:")
                logger.info(f"   - ID: {generation_id}")
                logger.info(f"   - Project ID: {project_id}")
                logger.info(f"   - Status: {generation.get('status')}")
                logger.info(f"   - FAL URLs: {len(fal_urls_found)}")
                for i, url in enumerate(fal_urls_found):
                    logger.info(f"     {i+1}. {url[:100]}...")
        
        # Save results
        report = {
            'timestamp': datetime.utcnow().isoformat(),
            'search_criteria': {
                'user_id': COLA_USER_ID,
                'project_id': COLA_PROJECT_ID
            },
            'total_generations_found': len(all_generations),
            'fal_generations_found': len(fal_generations),
            'generations_with_fal_urls': fal_generations
        }
        
        report_file = f'cola_fal_generations_found_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"📋 Report saved to: {report_file}")
        
        # Summary
        logger.info("📊 SEARCH SUMMARY:")
        logger.info(f"   - Total generations for user: {len(all_generations)}")
        logger.info(f"   - Generations with FAL URLs: {len(fal_generations)}")
        
        if fal_generations:
            logger.info("🎯 GENERATIONS TO MIGRATE:")
            for gen in fal_generations:
                logger.info(f"   - {gen['id']} ({gen['fal_url_count']} FAL URLs)")
        else:
            logger.warning("⚠️ No FAL URLs found for this user")
        
        return fal_generations
        
    except Exception as e:
        logger.error(f"❌ Failed to search for FAL generations: {e}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        return []

if __name__ == "__main__":
    asyncio.run(find_cola_fal_generations())