#!/usr/bin/env python3
"""
DATABASE PROFILE LOOKUP DEBUGGING SCRIPT
Test the exact database query path that's failing in the generation service.
"""

import asyncio
import logging
import sys
from datetime import datetime
import json

# Configure detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('debug_profile_lookup_database.log')
    ]
)
logger = logging.getLogger(__name__)

# Import the actual services and repositories
from database import get_database
from repositories.user_repository import UserRepository
from services.credit_transaction_service import credit_transaction_service, CreditTransaction
from models.credit import TransactionType

# Test data from the failing case
USER_ID = "22cb3917-57f6-49c6-ac96-ec266570081b"
JWT_TOKEN = "eyJhbGciOiJIUzI1NiIsImtpZCI6IjFLZVFoMGxkV3paZjBKaU"  # First 50 chars from log
CREDITS_REQUIRED = 45  # For fal-ai/imagen4/preview/ultra

async def test_database_operations():
    """Test the exact database operations that are failing."""
    logger.info("🔍 TESTING DATABASE OPERATIONS FOR PROFILE LOOKUP ERROR")
    logger.info(f"Testing User ID: {USER_ID}")
    logger.info(f"JWT Token (partial): {JWT_TOKEN}...")
    
    results = {}
    
    try:
        # Initialize database
        logger.info("\n1. 🗃️ INITIALIZING DATABASE CONNECTION")
        db = await get_database()
        user_repo = UserRepository(db)
        logger.info(f"✅ Database initialized: {db.is_available()}")
        
        # Test 1: Direct SQL query to check if user exists
        logger.info("\n2. 🔍 TESTING DIRECT SQL QUERY FOR USER")
        try:
            # This should work since we confirmed the user exists
            from database import db as global_db
            result = global_db.execute_query(
                "users",
                "select",
                filters={"id": USER_ID},
                use_service_key=True,
                single=False
            )
            logger.info(f"✅ Direct SQL result: {len(result) if result else 0} records")
            if result:
                logger.info(f"   User data: {result[0]}")
                results['direct_sql'] = 'SUCCESS'
            else:
                logger.error("❌ No user found with direct SQL")
                results['direct_sql'] = 'NO_USER_FOUND'
        except Exception as e:
            logger.error(f"❌ Direct SQL failed: {e}")
            results['direct_sql'] = f'ERROR: {e}'
        
        # Test 2: UserRepository.get_user_by_id with service key
        logger.info("\n3. 🔑 TESTING USER REPOSITORY WITH SERVICE KEY (NO JWT)")
        try:
            user = await user_repo.get_user_by_id(USER_ID, auth_token=None)
            if user:
                logger.info(f"✅ Service key lookup: User found with {user.credits_balance} credits")
                results['service_key_lookup'] = 'SUCCESS'
            else:
                logger.error("❌ Service key lookup: User not found")
                results['service_key_lookup'] = 'NO_USER_FOUND'
        except Exception as e:
            logger.error(f"❌ Service key lookup failed: {e}")
            results['service_key_lookup'] = f'ERROR: {e}'
        
        # Test 3: UserRepository.get_user_by_id with JWT token
        logger.info("\n4. 🔐 TESTING USER REPOSITORY WITH JWT TOKEN")
        try:
            # Use the full JWT token from the test script
            full_jwt = "eyJhbGciOiJIUzI1NiIsImtpZCI6IjFLZVFoMGxkV3paZjBKaUUiLCJ0eXAiOiJKV1QifQ.eyJpc3MiOiJodHRwczovL2x0c3Buc2R1emlwbHB1cXhjenZ5LnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiIyMmNiMzkxNy01N2Y2LTQ5YzYtYWM5Ni1lYzI2NjU3MDA4MWIiLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzU0MTIwNDg5LCJpYXQiOjE3NTQxMTY4ODksImVtYWlsIjoiZGVtb0B2ZWxyby5hcHAiLCJwaG9uZSI6IiIsImFwcF9tZXRhZGF0YSI6eyJwcm92aWRlciI6ImVtYWlsIiwicHJvdmlkZXJzIjpbImVtYWlsIl19LCJ1c2VyX21ldGFkYXRhIjp7ImVtYWlsIjoiZGVtb0B2ZWxyby5hcHAiLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwicGhvbmVfdmVyaWZpZWQiOmZhbHNlLCJzdWIiOiIyMmNiMzkxNy01N2Y2LTQ5YzYtYWM5Ni1lYzI2NjU3MDA4MWIifSwicm9sZSI6ImF1dGhlbnRpY2F0ZWQiLCJhYWwiOiJhYWwxIiwiYW1yIjpbeyJtZXRob2QiOiJwYXNzd29yZCIsInRpbWVzdGFtcCI6MTc1NDExNjg4OX1dLCJzZXNzaW9uX2lkIjoiYzJiYTVjYmItOWI4OC00MjNhLTg0MWEtN2I5OWZkYjQyNzU5IiwiaXNfYW5vbnltb3VzIjpmYWxzZX0.PlDMZjyiJbpWlqd1AB_H-V_zcvaGXE5kCIbh2vPNU_Q"
            
            user = await user_repo.get_user_by_id(USER_ID, auth_token=full_jwt)
            if user:
                logger.info(f"✅ JWT lookup: User found with {user.credits_balance} credits")
                results['jwt_lookup'] = 'SUCCESS'
            else:
                logger.error("❌ JWT lookup: User not found")
                results['jwt_lookup'] = 'NO_USER_FOUND'
        except Exception as e:
            logger.error(f"❌ JWT lookup failed: {e}")
            results['jwt_lookup'] = f'ERROR: {e}'
        
        # Test 4: UserRepository.get_user_credits (the method used in credit validation)
        logger.info("\n5. 💳 TESTING GET_USER_CREDITS (CREDIT VALIDATION PATH)")
        try:
            credits = await user_repo.get_user_credits(USER_ID, auth_token=None)
            logger.info(f"✅ Get credits (service key): {credits} credits")
            results['get_credits_service'] = f'SUCCESS: {credits}'
        except Exception as e:
            logger.error(f"❌ Get credits (service key) failed: {e}")
            results['get_credits_service'] = f'ERROR: {e}'
        
        # Test 5: UserRepository.get_user_credits with JWT
        logger.info("\n6. 💳 TESTING GET_USER_CREDITS WITH JWT (GENERATION FLOW PATH)")
        try:
            full_jwt = "eyJhbGciOiJIUzI1NiIsImtpZCI6IjFLZVFoMGxkV3paZjBKaUUiLCJ0eXAiOiJKV1QifQ.eyJpc3MiOiJodHRwczovL2x0c3Buc2R1emlwbHB1cXhjenZ5LnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiIyMmNiMzkxNy01N2Y2LTQ5YzYtYWM5Ni1lYzI2NjU3MDA4MWIiLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzU0MTIwNDg5LCJpYXQiOjE3NTQxMTY4ODksImVtYWlsIjoiZGVtb0B2ZWxyby5hcHAiLCJwaG9uZSI6IiIsImFwcF9tZXRhZGF0YSI6eyJwcm92aWRlciI6ImVtYWlsIiwicHJvdmlkZXJzIjpbImVtYWlsIl19LCJ1c2VyX21ldGFkYXRhIjp7ImVtYWlsIjoiZGVtb0B2ZWxyby5hcHAiLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwicGhvbmVfdmVyaWZpZWQiOmZhbHNlLCJzdWIiOiIyMmNiMzkxNy01N2Y2LTQ5YzYtYWM5Ni1lYzI2NjU3MDA4MWIifSwicm9sZSI6ImF1dGhlbnRpY2F0ZWQiLCJhYWwiOiJhYWwxIiwiYW1yIjpbeyJtZXRob2QiOiJwYXNzd29yZCIsInRpbWVzdGFtcCI6MTc1NDExNjg4OX1dLCJzZXNzaW9uX2lkIjoiYzJiYTVjYmItOWI4OC00MjNhLTg0MWEtN2I5OWZkYjQyNzU5IiwiaXNfYW5vbnltb3VzIjpmYWxzZX0.PlDMZjyiJbpWlqd1AB_H-V_zcvaGXE5kCIbh2vPNU_Q"
            
            credits = await user_repo.get_user_credits(USER_ID, auth_token=full_jwt)
            logger.info(f"✅ Get credits (JWT): {credits} credits")
            results['get_credits_jwt'] = f'SUCCESS: {credits}'
        except Exception as e:
            logger.error(f"❌ Get credits (JWT) failed: {e}")
            results['get_credits_jwt'] = f'ERROR: {e}'
        
        # Test 6: Credit Transaction Service (the exact failing path)
        logger.info("\n7. 🔄 TESTING CREDIT TRANSACTION SERVICE (EXACT GENERATION FLOW)")
        try:
            # Test the validate_credit_transaction method
            validation_result = await credit_transaction_service.validate_credit_transaction(
                user_id=USER_ID,
                required_amount=CREDITS_REQUIRED,
                auth_token=full_jwt
            )
            
            if validation_result.valid:
                logger.info(f"✅ Credit validation: PASSED - {validation_result.message}")
                results['credit_validation'] = 'SUCCESS'
            else:
                logger.error(f"❌ Credit validation: FAILED - {validation_result.message}")
                results['credit_validation'] = f'VALIDATION_FAILED: {validation_result.message}'
        except Exception as e:
            logger.error(f"❌ Credit validation failed: {e}")
            results['credit_validation'] = f'ERROR: {e}'
        
        # Test 7: Atomic Credit Deduction (the failing operation)
        logger.info("\n8. 💥 TESTING ATOMIC CREDIT DEDUCTION (EXACT FAILURE POINT)")
        try:
            # Create the exact transaction that's failing
            transaction = CreditTransaction(
                user_id=USER_ID,
                amount=CREDITS_REQUIRED,
                transaction_type=TransactionType.USAGE,
                generation_id="test-generation-id",
                model_name="fal-ai/imagen4/preview/ultra",
                description="Test credit deduction for debugging",
                auth_token=full_jwt,
                metadata={
                    "auth_token": full_jwt,
                    "generation_model": "fal-ai/imagen4/preview/ultra",
                    "credit_deduction": True,
                    "service_key_available": True,
                    "operation_context": "generation_credit_deduction"
                }
            )
            
            logger.info("🚨 WARNING: This will actually deduct credits! Comment out if not wanted.")
            # Uncomment the next line to test the actual deduction
            # updated_user = await credit_transaction_service.atomic_credit_deduction(transaction)
            # logger.info(f"✅ Atomic deduction: SUCCESS - New balance: {updated_user.credits_balance}")
            # results['atomic_deduction'] = f'SUCCESS: {updated_user.credits_balance}'
            
            logger.info("⚠️ Atomic deduction test SKIPPED to avoid credit loss")
            results['atomic_deduction'] = 'SKIPPED_TO_AVOID_CREDIT_LOSS'
            
        except Exception as e:
            logger.error(f"❌ Atomic deduction failed: {e}")
            results['atomic_deduction'] = f'ERROR: {e}'
        
    except Exception as e:
        logger.error(f"❌ Critical error in database testing: {e}")
        results['critical_error'] = str(e)
    
    # Summary
    logger.info("\n" + "="*80)
    logger.info("📋 DATABASE OPERATION TEST RESULTS")
    logger.info("="*80)
    
    for test_name, result in results.items():
        status = "✅" if result.startswith('SUCCESS') else "❌"
        logger.info(f"{status} {test_name}: {result}")
    
    # Save detailed results
    debug_report = {
        "timestamp": datetime.utcnow().isoformat(),
        "user_id": USER_ID,
        "test_results": results,
        "user_exists_in_database": True,  # We confirmed this
        "jwt_token_format": "valid_supabase_jwt",
        "credits_required": CREDITS_REQUIRED
    }
    
    with open('database_debug_results.json', 'w') as f:
        json.dump(debug_report, f, indent=2)
    
    logger.info("💾 Debug report saved to: database_debug_results.json")
    
    # Identify the failure point
    if results.get('service_key_lookup', '').startswith('ERROR'):
        logger.error("🎯 FAILURE POINT: Service key is invalid - all operations fallback to JWT")
        logger.error("🔧 SOLUTION: Fix SUPABASE_SERVICE_ROLE_KEY in Railway environment")
    
    if results.get('jwt_lookup', '').startswith('ERROR') and results.get('get_credits_jwt', '').startswith('ERROR'):
        logger.error("🎯 FAILURE POINT: JWT authentication is failing")
        logger.error("🔧 SOLUTION: Check JWT token format and RLS policies")
    
    if results.get('credit_validation', '').startswith('ERROR'):
        logger.error("🎯 FAILURE POINT: Credit transaction service is failing")
        logger.error("🔧 SOLUTION: Check credit transaction service implementation")

async def main():
    """Main execution."""
    await test_database_operations()

if __name__ == "__main__":
    asyncio.run(main())