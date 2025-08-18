#!/usr/bin/env python3
"""
Debug script to reproduce and analyze the "User profile not found for credit processing" error.
This script tests the complete user profile creation and credit processing flow.
"""

import asyncio
import logging
import sys
import os
from datetime import datetime
from uuid import uuid4

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SupabaseClient, get_database
from services.auth_service import AuthService
from services.user_service import UserService, user_service
from services.generation_service import GenerationService, generation_service
from services.credit_transaction_service import CreditTransactionService, credit_transaction_service
from repositories.user_repository import UserRepository
from models.user import UserCreate, UserLogin
from models.generation import GenerationCreate
from config import settings

# Configure detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('debug_profile_error.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class ProfileErrorDebugger:
    """Debug the user profile not found error."""
    
    def __init__(self):
        self.db_client = None
        self.auth_service = None
        self.user_service = None
        self.generation_service = None
        self.test_user_id = None
        self.test_token = None
        
    async def initialize(self):
        """Initialize services and connections."""
        logger.info("🔧 Initializing debug environment...")
        
        # Initialize database client
        self.db_client = await get_database()
        logger.info(f"📊 Database available: {self.db_client.is_available()}")
        
        # Initialize services
        self.auth_service = AuthService(self.db_client)
        self.user_service = user_service
        self.generation_service = generation_service
        
        logger.info("✅ Services initialized successfully")
        
    async def test_database_connectivity(self):
        """Test basic database connectivity and permissions."""
        logger.info("\n" + "="*50)
        logger.info("🔍 TESTING DATABASE CONNECTIVITY")
        logger.info("="*50)
        
        try:
            # Test anon client
            logger.info("📡 Testing anon client connectivity...")
            result = self.db_client.client.table("users").select("id").limit(1).execute()
            logger.info(f"✅ Anon client test: {len(result.data) if result.data else 0} rows returned")
            
            # Test service client  
            logger.info("🔑 Testing service client connectivity...")
            result = self.db_client.service_client.table("users").select("id").limit(1).execute()
            logger.info(f"✅ Service client test: {len(result.data) if result.data else 0} rows returned")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Database connectivity test failed: {e}")
            return False
    
    async def test_user_profile_creation_flow(self):
        """Test the complete user profile creation flow."""
        logger.info("\n" + "="*50)
        logger.info("👤 TESTING USER PROFILE CREATION FLOW")
        logger.info("="*50)
        
        # Generate test user data
        test_email = f"test-{uuid4()}@debug.com"
        test_user_id = str(uuid4())
        
        logger.info(f"🧪 Test user: {test_email}, ID: {test_user_id}")
        
        try:
            # Step 1: Test profile creation via user repository
            logger.info("📝 Step 1: Testing direct profile creation...")
            user_repo = UserRepository(self.db_client)
            
            profile_data = {
                "id": test_user_id,
                "email": test_email,
                "display_name": "Debug Test User",
                "credits_balance": 100,
                "role": "viewer"
            }
            
            try:
                created_user = await user_repo.create_user(profile_data)
                logger.info(f"✅ Profile created successfully: {created_user.id}")
                self.test_user_id = test_user_id
                
                # Step 2: Test profile retrieval
                logger.info("🔍 Step 2: Testing profile retrieval...")
                retrieved_user = await user_repo.get_user_by_id(test_user_id)
                if retrieved_user:
                    logger.info(f"✅ Profile retrieved: ID={retrieved_user.id}, Credits={retrieved_user.credits_balance}")
                else:
                    logger.error("❌ Profile retrieval failed - user not found")
                    return False
                
                # Step 3: Test credit balance retrieval
                logger.info("💳 Step 3: Testing credit balance retrieval...")
                credits = await user_repo.get_user_credits(test_user_id)
                logger.info(f"✅ Credits retrieved: {credits}")
                
                # Step 4: Test user service credit operations
                logger.info("🏪 Step 4: Testing user service credit operations...")
                service_credits = await self.user_service.get_user_credits(test_user_id)
                logger.info(f"✅ Service credits retrieved: {service_credits}")
                
                # Step 5: Test credit affordability check
                logger.info("💰 Step 5: Testing affordability check...")
                can_afford = await self.user_service.can_afford_generation(test_user_id, 10)
                logger.info(f"✅ Affordability check (10 credits): {can_afford}")
                
                return True
                
            except Exception as create_error:
                logger.error(f"❌ Profile creation failed: {create_error}")
                logger.error(f"   Error type: {type(create_error).__name__}")
                return False
                
        except Exception as e:
            logger.error(f"❌ User profile creation flow test failed: {e}")
            return False
    
    async def test_credit_processing_flow(self):
        """Test the credit processing flow that's failing."""
        logger.info("\n" + "="*50)
        logger.info("💳 TESTING CREDIT PROCESSING FLOW")
        logger.info("="*50)
        
        if not self.test_user_id:
            logger.error("❌ No test user available for credit processing test")
            return False
        
        try:
            # Step 1: Test credit transaction service validation
            logger.info("🔍 Step 1: Testing credit validation...")
            validation_result = await credit_transaction_service.validate_credit_transaction(
                user_id=self.test_user_id,
                required_amount=10,
                auth_token=None
            )
            logger.info(f"✅ Credit validation: {validation_result.valid}, Message: {validation_result.message}")
            
            if not validation_result.valid:
                logger.error("❌ Credit validation failed - this indicates the core issue")
                return False
            
            # Step 2: Test credit deduction simulation (without actual deduction)
            logger.info("💸 Step 2: Testing credit deduction simulation...")
            current_balance = await self.user_service.get_user_credits(self.test_user_id)
            logger.info(f"📊 Current balance before deduction: {current_balance}")
            
            if current_balance >= 10:
                logger.info("✅ User has sufficient credits for deduction")
            else:
                logger.error(f"❌ Insufficient credits: need 10, have {current_balance}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Credit processing flow test failed: {e}")
            logger.error(f"   Error type: {type(e).__name__}")
            logger.error(f"   Error details: {str(e)}")
            return False
    
    async def test_generation_creation_flow(self):
        """Test the generation creation flow where the error occurs."""
        logger.info("\n" + "="*50)
        logger.info("🎨 TESTING GENERATION CREATION FLOW")
        logger.info("="*50)
        
        if not self.test_user_id:
            logger.error("❌ No test user available for generation test")
            return False
        
        try:
            # Create a minimal generation request
            generation_data = GenerationCreate(
                prompt="A simple test image",
                model_id="fal-ai/flux-pro",  # Use a valid model
                project_id=None,
                negative_prompt=None,
                reference_image_url=None,
                parameters={}
            )
            
            logger.info(f"🎨 Creating generation for user {self.test_user_id}")
            logger.info(f"📝 Prompt: {generation_data.prompt}")
            logger.info(f"🤖 Model: {generation_data.model_id}")
            
            # Test the generation creation (this is where the error should occur)
            try:
                generation = await self.generation_service.create_generation(
                    user_id=self.test_user_id,
                    generation_data=generation_data,
                    reference_image_file=None,
                    reference_image_filename=None,
                    auth_token=None
                )
                
                logger.info(f"✅ Generation created successfully: {generation.id}")
                logger.info(f"📊 Generation status: {generation.status}")
                logger.info(f"💰 Generation cost: {generation.cost}")
                
                return True
                
            except ValueError as ve:
                error_msg = str(ve)
                if "User profile not found for credit processing" in error_msg:
                    logger.error("🎯 FOUND THE ERROR! 'User profile not found for credit processing'")
                    logger.error(f"   This confirms the issue is in credit processing during generation")
                    return False
                else:
                    logger.error(f"❌ Different ValueError in generation: {error_msg}")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Generation creation flow test failed: {e}")
            logger.error(f"   Error type: {type(e).__name__}")
            return False
    
    async def test_rls_permissions(self):
        """Test RLS permissions and JWT token handling."""
        logger.info("\n" + "="*50)
        logger.info("🔐 TESTING RLS PERMISSIONS AND JWT HANDLING")
        logger.info("="*50)
        
        if not self.test_user_id:
            logger.error("❌ No test user available for RLS test")
            return False
        
        try:
            # Test 1: Query with anon client (should be subject to RLS)
            logger.info("🔓 Test 1: Anon client query (subject to RLS)...")
            try:
                result = self.db_client.execute_query(
                    table="users",
                    operation="select",
                    filters={"id": self.test_user_id},
                    use_service_key=False
                )
                logger.info(f"✅ Anon client query successful: {len(result) if result else 0} records")
            except Exception as anon_error:
                logger.error(f"❌ Anon client query failed: {anon_error}")
            
            # Test 2: Query with service client (bypasses RLS)
            logger.info("🔑 Test 2: Service client query (bypasses RLS)...")
            try:
                result = self.db_client.execute_query(
                    table="users",
                    operation="select",
                    filters={"id": self.test_user_id},
                    use_service_key=True
                )
                logger.info(f"✅ Service client query successful: {len(result) if result else 0} records")
            except Exception as service_error:
                logger.error(f"❌ Service client query failed: {service_error}")
            
            # Test 3: Query with JWT token context
            logger.info("🎫 Test 3: JWT token context query...")
            try:
                # Create a mock JWT token for testing
                mock_token = f"supabase_token_{self.test_user_id}"
                result = self.db_client.execute_query(
                    table="users",
                    operation="select",
                    filters={"id": self.test_user_id},
                    use_service_key=False,
                    user_id=self.test_user_id,
                    auth_token=mock_token
                )
                logger.info(f"✅ JWT context query successful: {len(result) if result else 0} records")
            except Exception as jwt_error:
                logger.error(f"❌ JWT context query failed: {jwt_error}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ RLS permissions test failed: {e}")
            return False
    
    async def cleanup_test_data(self):
        """Clean up test data."""
        logger.info("\n" + "="*50)
        logger.info("🧹 CLEANING UP TEST DATA")
        logger.info("="*50)
        
        if self.test_user_id:
            try:
                # Delete test user using service client to bypass RLS
                result = self.db_client.execute_query(
                    table="users",
                    operation="delete",
                    filters={"id": self.test_user_id},
                    use_service_key=True
                )
                logger.info(f"✅ Test user deleted: {self.test_user_id}")
            except Exception as e:
                logger.error(f"❌ Failed to delete test user: {e}")
    
    async def run_debug_session(self):
        """Run the complete debug session."""
        logger.info("\n" + "🔬" + "="*48 + "🔬")
        logger.info("🔬 VELRO PROFILE ERROR DEBUG SESSION STARTED 🔬")
        logger.info("🔬" + "="*48 + "🔬")
        
        try:
            await self.initialize()
            
            # Run all debug tests
            tests = [
                ("Database Connectivity", self.test_database_connectivity),
                ("User Profile Creation", self.test_user_profile_creation_flow),
                ("Credit Processing", self.test_credit_processing_flow),
                ("Generation Creation", self.test_generation_creation_flow),
                ("RLS Permissions", self.test_rls_permissions)
            ]
            
            results = {}
            
            for test_name, test_func in tests:
                logger.info(f"\n⏱️  Running {test_name} test...")
                try:
                    result = await test_func()
                    results[test_name] = result
                    status = "✅ PASSED" if result else "❌ FAILED"
                    logger.info(f"📊 {test_name}: {status}")
                except Exception as e:
                    results[test_name] = False
                    logger.error(f"💥 {test_name}: CRASHED - {e}")
            
            # Summary
            logger.info("\n" + "📊" + "="*48 + "📊")
            logger.info("📊 DEBUG SESSION SUMMARY")
            logger.info("📊" + "="*48 + "📊")
            
            passed = sum(1 for result in results.values() if result)
            total = len(results)
            
            for test_name, result in results.items():
                status = "✅ PASSED" if result else "❌ FAILED"
                logger.info(f"   {test_name}: {status}")
            
            logger.info(f"\n📈 Overall: {passed}/{total} tests passed")
            
            if passed < total:
                logger.error("🚨 ISSUES DETECTED - Check the logs above for details")
            else:
                logger.info("🎉 ALL TESTS PASSED - Profile error may be intermittent")
            
        except Exception as e:
            logger.error(f"💥 Debug session crashed: {e}")
        finally:
            await self.cleanup_test_data()
            logger.info("\n🏁 Debug session completed")

async def main():
    """Main entry point."""
    debugger = ProfileErrorDebugger()
    await debugger.run_debug_session()

if __name__ == "__main__":
    asyncio.run(main())