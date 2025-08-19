#!/usr/bin/env python3
"""
Direct database investigation to understand why the Cola project shows 13 generations
but the API returns 0 generations.
"""
import asyncio
import os
import sys
import logging
from typing import Optional
from datetime import datetime, timedelta

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SupabaseClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Test data
USER_ID = "23f370b8-5d53-4640-8c36-8b5f499abe70"
PROJECT_ID = "18c021d8-b530-4a46-a9b0-f61fe309c146"  # Cola project

async def investigate_generations():
    """Direct database investigation."""
    logger.info("🔍 Starting direct database investigation...")
    
    db_client = SupabaseClient()
    
    try:
        # Test 1: Check if any generations exist for this user (using service key)
        logger.info("📋 Test 1: Check all generations for user (service key)...")
        try:
            all_generations = db_client.execute_query(
                "generations",
                "select",
                filters={"user_id": USER_ID},
                use_service_key=True
            )
            logger.info(f"✅ Service key found {len(all_generations)} total generations for user")
            
            # Show sample records
            for i, gen in enumerate(all_generations[:3]):
                logger.info(f"🔍 Generation {i}: id={gen.get('id')[:8]}..., project_id={gen.get('project_id')}, status={gen.get('status')}")
                
        except Exception as e:
            logger.error(f"❌ Service key test failed: {e}")
        
        # Test 2: Check without service key (anon client)
        logger.info("📋 Test 2: Check all generations for user (anon client)...")
        try:
            anon_generations = db_client.execute_query(
                "generations",
                "select",
                filters={"user_id": USER_ID},
                use_service_key=False
            )
            logger.info(f"✅ Anon client found {len(anon_generations)} total generations for user")
            
        except Exception as e:
            logger.error(f"❌ Anon client test failed: {e}")
        
        # Test 3: Check generations with project filter (service key)
        logger.info("📋 Test 3: Check Cola project generations (service key)...")
        try:
            cola_generations_service = db_client.execute_query(
                "generations",
                "select",
                filters={"user_id": USER_ID, "project_id": PROJECT_ID},
                use_service_key=True
            )
            logger.info(f"✅ Service key found {len(cola_generations_service)} Cola project generations")
            
            for gen in cola_generations_service:
                logger.info(f"🔍 Cola generation: id={gen.get('id')[:8]}..., created_at={gen.get('created_at')}, status={gen.get('status')}")
                
        except Exception as e:
            logger.error(f"❌ Service key Cola project test failed: {e}")
        
        # Test 4: Check generations with project filter (anon client)
        logger.info("📋 Test 4: Check Cola project generations (anon client)...")
        try:
            cola_generations_anon = db_client.execute_query(
                "generations",
                "select",
                filters={"user_id": USER_ID, "project_id": PROJECT_ID},
                use_service_key=False
            )
            logger.info(f"✅ Anon client found {len(cola_generations_anon)} Cola project generations")
            
        except Exception as e:
            logger.error(f"❌ Anon client Cola project test failed: {e}")
        
        # Test 5: Raw SQL check to bypass all filters
        logger.info("📋 Test 5: Raw SQL check...")
        try:
            raw_query = f"""
            SELECT id, user_id, project_id, status, created_at, model_id
            FROM generations 
            WHERE user_id = '{USER_ID}'
            ORDER BY created_at DESC
            LIMIT 10;
            """
            
            # Using the supabase client directly
            result = db_client.service_client.table('generations').select('id,user_id,project_id,status,created_at,model_id').eq('user_id', USER_ID).limit(10).execute()
            
            logger.info(f"✅ Raw query found {len(result.data)} generations")
            for gen in result.data:
                logger.info(f"🔍 Raw generation: id={gen.get('id')[:8]}..., project_id={gen.get('project_id')}, status={gen.get('status')}")
            
        except Exception as e:
            logger.error(f"❌ Raw SQL test failed: {e}")
        
        # Test 6: Check specific generation ID that was mentioned in the logs
        logger.info("📋 Test 6: Check specific generation ID...")
        specific_id = "cb6025b7-5cac-4905-b567-621c925a2617"
        try:
            specific_gen = db_client.execute_query(
                "generations",
                "select",
                filters={"id": specific_id},
                use_service_key=True,
                single=True
            )
            if specific_gen:
                logger.info(f"✅ Found specific generation: user_id={specific_gen.get('user_id')}, project_id={specific_gen.get('project_id')}")
            else:
                logger.warning(f"⚠️ Specific generation {specific_id} not found")
                
        except Exception as e:
            logger.error(f"❌ Specific generation test failed: {e}")
        
        # Test 7: Check RLS policies
        logger.info("📋 Test 7: Check RLS policies...")
        try:
            # Try to see if RLS is causing issues
            policies_query = """
            SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
            FROM pg_policies 
            WHERE tablename = 'generations';
            """
            
            policies_result = db_client.service_client.rpc('exec_sql', {'query': policies_query}).execute()
            logger.info(f"✅ Found {len(policies_result.data) if policies_result.data else 0} RLS policies for generations table")
            
            for policy in (policies_result.data or []):
                logger.info(f"🔍 Policy: {policy.get('policyname')} - {policy.get('cmd')} - {policy.get('qual')}")
                
        except Exception as e:
            logger.error(f"❌ RLS policies check failed: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Investigation failed: {e}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    success = asyncio.run(investigate_generations())
    sys.exit(0 if success else 1)