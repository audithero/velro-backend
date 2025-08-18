#!/usr/bin/env python3
"""
Run Background Migration Once

Simple script to run a one-time background migration for existing generations
that need Fal URL to Supabase Storage migration.
"""
import asyncio
import sys
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('background_migration.log')
    ]
)
logger = logging.getLogger(__name__)

async def run_migration():
    """Run one-time background migration"""
    try:
        # Import here to avoid circular imports
        sys.path.append('/Users/apostle_mbp/Dropbox/0xAPOSTLE/00.WINDSURF/Claudecurrent/velro-003/velro-backend')
        from services.background_storage_migration import run_migration_once
        
        logger.info("🚀 [MIGRATION] Starting one-time background migration...")
        
        # Run migration with a larger batch size for one-time cleanup
        results = await run_migration_once(batch_size=25)
        
        logger.info(f"📊 [MIGRATION] Migration completed:")
        logger.info(f"   - Processed: {results.get('processed', 0)} generations")
        logger.info(f"   - Successful: {results.get('successful', 0)} migrations")
        logger.info(f"   - Failed: {results.get('failed', 0)} migrations")
        
        if 'error' in results:
            logger.error(f"❌ [MIGRATION] Error occurred: {results['error']}")
            return False
        
        if results.get('processed', 0) == 0:
            logger.info("✨ [MIGRATION] No generations found needing migration - system is clean!")
            return True
        
        success_rate = 0
        if results.get('processed', 0) > 0:
            success_rate = (results.get('successful', 0) / results.get('processed', 0)) * 100
        
        logger.info(f"📈 [MIGRATION] Success rate: {success_rate:.1f}%")
        
        if success_rate >= 80:
            logger.info("✅ [MIGRATION] Migration completed successfully!")
            return True
        else:
            logger.warning("⚠️  [MIGRATION] Some migrations failed - may need retry")
            return False
        
    except ImportError as e:
        logger.error(f"❌ [MIGRATION] Import error - check if services are available: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ [MIGRATION] Unexpected error: {e}")
        import traceback
        logger.error(f"❌ [MIGRATION] Traceback: {traceback.format_exc()}")
        return False

def main():
    """Main execution"""
    print("🚨 [EMERGENCY] Starting Background Migration for Existing Generations")
    print("=" * 70)
    print("This will migrate existing generations with temporary Fal URLs")
    print("to permanent Supabase Storage URLs.")
    print("=" * 70)
    
    try:
        success = asyncio.run(run_migration())
        
        print("\n" + "=" * 70)
        if success:
            print("✅ BACKGROUND MIGRATION: COMPLETED SUCCESSFULLY")
            print("   - Existing problematic generations have been processed")
            print("   - Fal URLs migrated to Supabase Storage where possible")
            print("   - System is ready for normal operation")
        else:
            print("⚠️  BACKGROUND MIGRATION: COMPLETED WITH ISSUES")  
            print("   - Some migrations may have failed")
            print("   - Check logs for details")
            print("   - Consider running again or investigating failures")
        print("=" * 70)
        
        return success
        
    except KeyboardInterrupt:
        print("\n🛑 Migration interrupted by user")
        return False
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)