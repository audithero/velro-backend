#!/usr/bin/env python3
"""
Scan ALL database generations for FAL URLs
==========================================

This script searches the entire database to find ANY generations
that contain FAL URLs, regardless of user.
"""

import asyncio
import json
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def scan_all_fal_urls():
    """Scan all generations in database for FAL URLs."""
    try:
        # Import database
        from database import get_database
        db = await get_database()
        
        logger.info("✅ Database connection established")
        logger.info("🔍 Scanning ALL generations in database for FAL URLs...")
        
        # Get all generations in database (use service key to bypass RLS)
        logger.info("🔍 Querying all generations...")
        
        try:
            # Try with service key first
            all_generations = db.execute_query(
                table="generations",
                operation="select",
                use_service_key=True,
                limit=1000
            )
            logger.info(f"✅ Retrieved {len(all_generations)} generations using service key")
        except Exception as e:
            logger.warning(f"⚠️ Service key failed, trying with anon client: {e}")
            # Fallback to anon client
            all_generations = db.execute_query(
                table="generations",
                operation="select",
                use_service_key=False,
                limit=1000
            )
            logger.info(f"✅ Retrieved {len(all_generations)} generations using anon client")
        
        logger.info(f"📊 Found {len(all_generations)} total generations in database")
        
        if not all_generations:
            logger.warning("⚠️ No generations found in database at all")
            return []
        
        # Check each generation for FAL URLs
        fal_generations = []
        
        for generation in all_generations:
            generation_id = generation.get('id')
            user_id = generation.get('user_id')
            project_id = generation.get('project_id')
            media_url = generation.get('media_url')
            output_urls = generation.get('output_urls', [])
            
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
                    'user_id': user_id,
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
                logger.info(f"   - User ID: {user_id}")
                logger.info(f"   - Project ID: {project_id}")
                logger.info(f"   - Status: {generation.get('status')}")
                logger.info(f"   - FAL URLs: {len(fal_urls_found)}")
                for i, url in enumerate(fal_urls_found):
                    logger.info(f"     {i+1}. {url[:100]}...")
        
        # Also check for users and projects
        logger.info("🔍 Checking users in database...")
        try:
            all_users = db.execute_query(
                table="users",
                operation="select",
                use_service_key=True,
                limit=100
            )
            logger.info(f"📊 Found {len(all_users)} users in database")
            
            # Look for demo@example.com specifically
            demo_users = [u for u in all_users if u.get('email') == 'demo@example.com']
            if demo_users:
                demo_user = demo_users[0]
                logger.info(f"🎯 Found demo user: ID={demo_user.get('id')}, email={demo_user.get('email')}")
            else:
                logger.warning("⚠️ demo@example.com user not found")
            
        except Exception as e:
            logger.warning(f"⚠️ Could not query users: {e}")
        
        logger.info("🔍 Checking projects in database...")
        try:
            all_projects = db.execute_query(
                table="projects",
                operation="select",
                use_service_key=True,
                limit=100
            )
            logger.info(f"📊 Found {len(all_projects)} projects in database")
            
            # Look for cola project specifically
            cola_projects = [p for p in all_projects if p.get('title', '').lower() == 'cola']
            if cola_projects:
                cola_project = cola_projects[0]
                logger.info(f"🎯 Found cola project: ID={cola_project.get('id')}, title={cola_project.get('title')}, user_id={cola_project.get('user_id')}")
            else:
                logger.warning("⚠️ Cola project not found")
        except Exception as e:
            logger.warning(f"⚠️ Could not query projects: {e}")
        
        # Save results
        report = {
            'timestamp': datetime.utcnow().isoformat(),
            'total_generations_scanned': len(all_generations),
            'fal_generations_found': len(fal_generations),
            'generations_with_fal_urls': fal_generations
        }
        
        report_file = f'all_fal_generations_scan_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"📋 Report saved to: {report_file}")
        
        # Summary
        logger.info("📊 SCAN SUMMARY:")
        logger.info(f"   - Total generations scanned: {len(all_generations)}")
        logger.info(f"   - Generations with FAL URLs: {len(fal_generations)}")
        
        if fal_generations:
            logger.info("🎯 GENERATIONS TO MIGRATE:")
            for gen in fal_generations:
                logger.info(f"   - {gen['id']} (User: {gen['user_id']}, Project: {gen['project_id']}, FAL URLs: {gen['fal_url_count']})")
                
            # Group by user
            users_with_fal = {}
            for gen in fal_generations:
                user_id = gen['user_id']
                if user_id not in users_with_fal:
                    users_with_fal[user_id] = []
                users_with_fal[user_id].append(gen)
            
            logger.info("👥 USERS AFFECTED:")
            for user_id, user_generations in users_with_fal.items():
                logger.info(f"   - User {user_id}: {len(user_generations)} generations with FAL URLs")
        else:
            logger.warning("⚠️ No FAL URLs found in any generation")
        
        return fal_generations
        
    except Exception as e:
        logger.error(f"❌ Failed to scan for FAL generations: {e}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        return []

if __name__ == "__main__":
    asyncio.run(scan_all_fal_urls())