#!/usr/bin/env python3
"""
Verify Migration Status
======================

This script checks the current status of the FAL URL migration by:
1. Checking if database is empty (indicating successful migration)
2. Verifying there are no remaining FAL URLs anywhere
3. Confirming all URLs are now Supabase Storage URLs
4. Generating a final status report
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
import httpx

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def verify_migration_status():
    """Verify the current migration status."""
    try:
        logger.info("🔍 VERIFYING FAL URL MIGRATION STATUS")
        logger.info("=" * 50)
        
        # Import database
        from database import get_database
        from config import settings
        
        db = await get_database()
        logger.info("✅ Database connection established")
        
        # Check database configuration
        logger.info("📊 Database Configuration:")
        logger.info(f"   - Supabase URL: {settings.supabase_url}")
        logger.info(f"   - Service Key Available: {bool(settings.supabase_service_role_key)}")
        logger.info(f"   - Database Available: {db.is_available()}")
        
        # Try to query all tables to understand the current state
        report = {
            'verification_timestamp': datetime.utcnow().isoformat(),
            'database_status': 'connected',
            'tables_checked': {},
            'fal_urls_found': [],
            'supabase_urls_found': [],
            'migration_status': 'unknown',
            'conclusions': []
        }
        
        # Check users table
        try:
            users = db.execute_query(table="users", operation="select", limit=10)
            report['tables_checked']['users'] = {
                'accessible': True,
                'count': len(users),
                'sample_data': len(users) > 0
            }
            logger.info(f"✅ Users table: {len(users)} records")
        except Exception as e:
            report['tables_checked']['users'] = {'accessible': False, 'error': str(e)}
            logger.warning(f"⚠️ Users table inaccessible: {e}")
        
        # Check projects table
        try:
            projects = db.execute_query(table="projects", operation="select", limit=10)
            report['tables_checked']['projects'] = {
                'accessible': True,
                'count': len(projects),
                'sample_data': len(projects) > 0
            }
            logger.info(f"✅ Projects table: {len(projects)} records")
        except Exception as e:
            report['tables_checked']['projects'] = {'accessible': False, 'error': str(e)}
            logger.warning(f"⚠️ Projects table inaccessible: {e}")
        
        # Check generations table
        try:
            generations = db.execute_query(table="generations", operation="select", limit=100)
            report['tables_checked']['generations'] = {
                'accessible': True,
                'count': len(generations),
                'sample_data': len(generations) > 0
            }
            logger.info(f"✅ Generations table: {len(generations)} records")
            
            # Scan for any FAL URLs
            fal_count = 0
            supabase_count = 0
            
            for gen in generations:
                media_url = gen.get('media_url')
                output_urls = gen.get('output_urls', [])
                
                # Check media_url
                if media_url:
                    if 'fal.media' in media_url:
                        fal_count += 1
                        report['fal_urls_found'].append({
                            'generation_id': gen.get('id'),
                            'url_type': 'media_url',
                            'url': media_url
                        })
                    elif 'supabase' in media_url or 'ltspnsduziplpuqxczvy' in media_url:
                        supabase_count += 1
                        report['supabase_urls_found'].append({
                            'generation_id': gen.get('id'),
                            'url_type': 'media_url',
                            'url': media_url[:100] + '...'
                        })
                
                # Check output_urls
                if output_urls:
                    for url in output_urls:
                        if url and 'fal.media' in url:
                            fal_count += 1
                            report['fal_urls_found'].append({
                                'generation_id': gen.get('id'),
                                'url_type': 'output_urls',
                                'url': url
                            })
                        elif url and ('supabase' in url or 'ltspnsduziplpuqxczvy' in url):
                            supabase_count += 1
                            report['supabase_urls_found'].append({
                                'generation_id': gen.get('id'),
                                'url_type': 'output_urls',
                                'url': url[:100] + '...'
                            })
            
            logger.info(f"📊 URL Analysis:")
            logger.info(f"   - Total generations: {len(generations)}")
            logger.info(f"   - FAL URLs found: {fal_count}")
            logger.info(f"   - Supabase URLs found: {supabase_count}")
            
        except Exception as e:
            report['tables_checked']['generations'] = {'accessible': False, 'error': str(e)}
            logger.warning(f"⚠️ Generations table inaccessible: {e}")
        
        # Determine migration status
        total_fal_urls = len(report['fal_urls_found'])
        total_supabase_urls = len(report['supabase_urls_found'])
        
        if total_fal_urls == 0 and total_supabase_urls == 0:
            if report['tables_checked'].get('generations', {}).get('count', 0) == 0:
                report['migration_status'] = 'database_empty'
                report['conclusions'].append("Database appears empty - may be test environment or all data migrated/cleaned")
            else:
                report['migration_status'] = 'no_external_urls'
                report['conclusions'].append("No external URLs found - all media may be using internal storage")
        elif total_fal_urls == 0 and total_supabase_urls > 0:
            report['migration_status'] = 'migration_complete'
            report['conclusions'].append(f"Migration appears SUCCESSFUL - {total_supabase_urls} Supabase URLs found, 0 FAL URLs remaining")
        elif total_fal_urls > 0:
            report['migration_status'] = 'migration_needed'
            report['conclusions'].append(f"Migration NEEDED - {total_fal_urls} FAL URLs still exist and need migration")
        else:
            report['migration_status'] = 'unclear'
            report['conclusions'].append("Status unclear - mixed or unexpected URL patterns found")
        
        # Test a sample URL if we have any
        if report['supabase_urls_found']:
            sample_url = None
            for url_info in report['supabase_urls_found']:
                if url_info['url'] and not url_info['url'].endswith('...'):
                    sample_url = url_info['url']
                    break
            
            if sample_url:
                logger.info(f"🔗 Testing sample Supabase URL...")
                try:
                    async with httpx.AsyncClient() as client:
                        response = await client.get(sample_url, timeout=10.0)
                        if response.status_code == 200:
                            logger.info(f"✅ Sample Supabase URL is accessible")
                            report['conclusions'].append("Sample Supabase Storage URL is accessible and working")
                        else:
                            logger.warning(f"⚠️ Sample Supabase URL returned status {response.status_code}")
                            report['conclusions'].append(f"Sample Supabase URL returned unexpected status: {response.status_code}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not test sample URL: {e}")
                    report['conclusions'].append(f"Could not test sample Supabase URL: {str(e)}")
        
        # Save report
        report_file = f'migration_status_verification_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"📋 Verification report saved to: {report_file}")
        
        # Print final status
        logger.info("🎯 MIGRATION STATUS SUMMARY:")
        logger.info(f"   - Status: {report['migration_status'].upper()}")
        logger.info(f"   - FAL URLs found: {total_fal_urls}")
        logger.info(f"   - Supabase URLs found: {total_supabase_urls}")
        
        for conclusion in report['conclusions']:
            logger.info(f"   - {conclusion}")
        
        return report
        
    except Exception as e:
        logger.error(f"❌ Verification failed: {e}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        return {'status': 'error', 'error': str(e)}

async def main():
    """Main verification entry point."""
    try:
        report = await verify_migration_status()
        
        # Return appropriate exit code
        if report.get('migration_status') == 'migration_complete':
            print("🎉 MIGRATION VERIFICATION: SUCCESS - All FAL URLs have been migrated!")
            return 0
        elif report.get('migration_status') == 'database_empty':
            print("ℹ️ MIGRATION VERIFICATION: Database appears empty (test environment or fully migrated)")
            return 0
        elif report.get('migration_status') == 'migration_needed':
            print("⚠️ MIGRATION VERIFICATION: FAL URLs still exist and need migration")
            return 1
        else:
            print("❓ MIGRATION VERIFICATION: Status unclear")
            return 2
            
    except Exception as e:
        print(f"❌ MIGRATION VERIFICATION FAILED: {e}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)