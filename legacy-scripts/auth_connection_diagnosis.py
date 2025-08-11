#!/usr/bin/env python3
"""
Authentication Connection Diagnosis Script
Comprehensive diagnosis of Supabase authentication connection issues
"""
import json
import os
import sys
import traceback
from datetime import datetime
from typing import Dict, Any, Optional
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def diagnose_environment() -> Dict[str, Any]:
    """Diagnose environment configuration."""
    logger.info("🔍 [DIAGNOSIS] Checking environment configuration...")
    
    env_data = {
        "timestamp": datetime.now().isoformat(),
        "environment_variables": {},
        "supabase_config": {},
        "issues": []
    }
    
    # Check essential environment variables
    essential_vars = [
        "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_KEY", 
        "SUPABASE_SERVICE_ROLE_KEY", "JWT_SECRET_KEY", "ENVIRONMENT"
    ]
    
    for var in essential_vars:
        value = os.getenv(var)
        if value:
            # Mask sensitive values but show length
            if "key" in var.lower() or "secret" in var.lower():
                env_data["environment_variables"][var] = f"[PRESENT - length: {len(value)}]"
                # Validate JWT format for service keys
                if var in ["SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_ROLE_KEY"]:
                    if not value.startswith(('eyJ', 'sb-')):
                        env_data["issues"].append(f"{var} format may be invalid (doesn't start with eyJ or sb-)")
                    else:
                        logger.info(f"✅ {var} format appears valid")
            else:
                env_data["environment_variables"][var] = value
        else:
            env_data["environment_variables"][var] = "[MISSING]"
            env_data["issues"].append(f"Missing required environment variable: {var}")
    
    # Validate Supabase URL format
    supabase_url = os.getenv("SUPABASE_URL")
    if supabase_url:
        if not supabase_url.startswith("https://") or not supabase_url.endswith(".supabase.co"):
            env_data["issues"].append("SUPABASE_URL format may be invalid")
        else:
            logger.info("✅ SUPABASE_URL format appears valid")
    
    return env_data

def diagnose_supabase_connection() -> Dict[str, Any]:
    """Diagnose Supabase connection and client creation."""
    logger.info("🔍 [DIAGNOSIS] Testing Supabase connection...")
    
    connection_data = {
        "client_creation": {},
        "service_client_creation": {},
        "connection_tests": {},
        "issues": []
    }
    
    try:
        # Test regular client creation
        logger.info("Testing regular Supabase client creation...")
        from database import SupabaseClient
        db_client = SupabaseClient()
        
        # Test client property
        try:
            client = db_client.client
            connection_data["client_creation"] = {
                "status": "success",
                "client_created": True
            }
            logger.info("✅ Regular Supabase client created successfully")
        except Exception as client_error:
            connection_data["client_creation"] = {
                "status": "failed",
                "error": str(client_error),
                "error_type": type(client_error).__name__
            }
            connection_data["issues"].append(f"Regular client creation failed: {client_error}")
            logger.error(f"❌ Regular client creation failed: {client_error}")
        
        # Test service client creation
        try:
            service_client = db_client.service_client
            connection_data["service_client_creation"] = {
                "status": "success",
                "service_client_created": True,
                "service_key_valid": getattr(db_client, '_service_key_valid', None)
            }
            logger.info("✅ Service client created successfully")
        except Exception as service_error:
            connection_data["service_client_creation"] = {
                "status": "failed",
                "error": str(service_error),
                "error_type": type(service_error).__name__
            }
            connection_data["issues"].append(f"Service client creation failed: {service_error}")
            logger.error(f"❌ Service client creation failed: {service_error}")
        
        # Test basic connection
        try:
            is_available = db_client.is_available()
            connection_data["connection_tests"]["is_available"] = {
                "status": "success" if is_available else "failed",
                "available": is_available
            }
            if is_available:
                logger.info("✅ Database connection is available")
            else:
                logger.warning("⚠️ Database connection is not available")
                connection_data["issues"].append("Database connection is not available")
        except Exception as availability_error:
            connection_data["connection_tests"]["is_available"] = {
                "status": "failed",
                "error": str(availability_error),
                "error_type": type(availability_error).__name__
            }
            connection_data["issues"].append(f"Connection availability test failed: {availability_error}")
            logger.error(f"❌ Connection availability test failed: {availability_error}")
        
    except Exception as db_error:
        connection_data["database_client_import"] = {
            "status": "failed",
            "error": str(db_error),
            "error_type": type(db_error).__name__
        }
        connection_data["issues"].append(f"Database client import/creation failed: {db_error}")
        logger.error(f"❌ Database client import/creation failed: {db_error}")
    
    return connection_data

async def diagnose_authentication_flow() -> Dict[str, Any]:
    """Diagnose the complete authentication flow."""
    logger.info("🔍 [DIAGNOSIS] Testing authentication flow...")
    
    auth_data = {
        "auth_service_import": {},
        "demo_user_authentication": {},
        "supabase_auth_test": {},
        "issues": []
    }
    
    try:
        # Test auth service import
        logger.info("Testing auth service import...")
        from services.auth_service import AuthService
        from database import SupabaseClient
        from models.user import UserLogin
        
        auth_data["auth_service_import"] = {
            "status": "success",
            "imported": True
        }
        logger.info("✅ Auth service imported successfully")
        
        # Initialize auth service
        db_client = SupabaseClient()
        auth_service = AuthService(db_client)
        
        # Test demo user authentication
        logger.info("Testing demo user authentication...")
        demo_credentials = UserLogin(email="demo@example.com", password="demo123")
        
        try:
            user = await auth_service.authenticate_user(demo_credentials, "127.0.0.1", "diagnosis-script")
            if user:
                auth_data["demo_user_authentication"] = {
                    "status": "success",
                    "user_found": True,
                    "user_id": str(user.id),
                    "user_email": user.email,
                    "credits_balance": user.credits_balance
                }
                logger.info(f"✅ Demo user authentication successful: {user.email}")
                
                # Test token creation
                try:
                    token = await auth_service.create_access_token(user)
                    auth_data["demo_user_authentication"]["token_creation"] = {
                        "status": "success",
                        "token_type": token.token_type,
                        "token_length": len(token.access_token),
                        "is_jwt": not any(token.access_token.startswith(prefix) for prefix in ['demo_token_', 'mock_token_', 'dev_token_'])
                    }
                    logger.info(f"✅ Token creation successful: {token.token_type}, length: {len(token.access_token)}")
                except Exception as token_error:
                    auth_data["demo_user_authentication"]["token_creation"] = {
                        "status": "failed",
                        "error": str(token_error),
                        "error_type": type(token_error).__name__
                    }
                    auth_data["issues"].append(f"Token creation failed: {token_error}")
                    logger.error(f"❌ Token creation failed: {token_error}")
                    
            else:
                auth_data["demo_user_authentication"] = {
                    "status": "failed",
                    "user_found": False,
                    "message": "Authentication returned None - likely 'Invalid email or password'"
                }
                auth_data["issues"].append("Demo user authentication failed - this is the main issue")
                logger.error("❌ Demo user authentication failed - returned None")
                
        except Exception as auth_error:
            auth_data["demo_user_authentication"] = {
                "status": "failed",
                "error": str(auth_error),
                "error_type": type(auth_error).__name__
            }
            auth_data["issues"].append(f"Demo user authentication threw exception: {auth_error}")
            logger.error(f"❌ Demo user authentication threw exception: {auth_error}")
        
        # Test direct Supabase authentication
        logger.info("Testing direct Supabase authentication...")
        try:
            response = db_client.client.auth.sign_in_with_password({
                "email": "demo@example.com",
                "password": "demo123"
            })
            
            if response.user and response.session:
                auth_data["supabase_auth_test"] = {
                    "status": "success",
                    "user_id": response.user.id,
                    "user_email": response.user.email,
                    "session_exists": True,
                    "access_token_length": len(response.session.access_token) if response.session.access_token else 0
                }
                logger.info(f"✅ Direct Supabase authentication successful: {response.user.email}")
            else:
                auth_data["supabase_auth_test"] = {
                    "status": "failed",
                    "user_exists": bool(response.user),
                    "session_exists": bool(response.session),
                    "message": "Supabase authentication did not return user or session"
                }
                auth_data["issues"].append("Direct Supabase authentication failed - no user or session returned")
                logger.error("❌ Direct Supabase authentication failed - no user or session")
                
        except Exception as supabase_auth_error:
            auth_data["supabase_auth_test"] = {
                "status": "failed",
                "error": str(supabase_auth_error),
                "error_type": type(supabase_auth_error).__name__
            }
            
            # Analyze specific error
            error_str = str(supabase_auth_error).lower()
            if "database error granting user" in error_str:
                auth_data["issues"].append("CRITICAL: 'Database error granting user' - This is the root cause!")
                logger.error("🚨 CRITICAL: 'Database error granting user' detected - This is the root cause!")
            elif "invalid email or password" in error_str:
                auth_data["issues"].append("Invalid email or password - user may not exist in Supabase")
                logger.error("❌ Invalid email or password - user may not exist")
            elif "invalid api key" in error_str:
                auth_data["issues"].append("Invalid API key - check SUPABASE_ANON_KEY")
                logger.error("❌ Invalid API key - check SUPABASE_ANON_KEY")
            else:
                auth_data["issues"].append(f"Unknown Supabase auth error: {supabase_auth_error}")
                logger.error(f"❌ Unknown Supabase auth error: {supabase_auth_error}")
                
    except Exception as import_error:
        auth_data["auth_service_import"] = {
            "status": "failed",
            "error": str(import_error),
            "error_type": type(import_error).__name__
        }
        auth_data["issues"].append(f"Auth service import failed: {import_error}")
        logger.error(f"❌ Auth service import failed: {import_error}")
    
    return auth_data

def diagnose_user_existence() -> Dict[str, Any]:
    """Check if demo user exists in Supabase."""
    logger.info("🔍 [DIAGNOSIS] Checking demo user existence...")
    
    user_data = {
        "user_lookup_tests": {},
        "issues": []
    }
    
    try:
        from database import SupabaseClient
        db_client = SupabaseClient()
        
        # Test 1: Check in public.users table
        try:
            result = db_client.service_client.table('users').select('*').eq('email', 'demo@example.com').execute()
            user_data["user_lookup_tests"]["public_users_table"] = {
                "status": "success",
                "user_found": bool(result.data and len(result.data) > 0),
                "user_count": len(result.data) if result.data else 0
            }
            if result.data and len(result.data) > 0:
                user_data["user_lookup_tests"]["public_users_table"]["user_data"] = result.data[0]
                logger.info(f"✅ Demo user found in public.users: {result.data[0]['id']}")
            else:
                logger.warning("⚠️ Demo user not found in public.users table")
                user_data["issues"].append("Demo user not found in public.users table")
                
        except Exception as public_error:
            user_data["user_lookup_tests"]["public_users_table"] = {
                "status": "failed",
                "error": str(public_error),
                "error_type": type(public_error).__name__
            }
            user_data["issues"].append(f"Could not query public.users table: {public_error}")
            logger.error(f"❌ Could not query public.users table: {public_error}")
        
        # Test 2: Check in auth.users table (if accessible)
        try:
            auth_result = db_client.service_client.table('auth.users').select('*').eq('email', 'demo@example.com').execute()
            user_data["user_lookup_tests"]["auth_users_table"] = {
                "status": "success",
                "user_found": bool(auth_result.data and len(auth_result.data) > 0),
                "user_count": len(auth_result.data) if auth_result.data else 0
            }
            if auth_result.data and len(auth_result.data) > 0:
                # Don't include sensitive auth data, just confirm existence
                user_data["user_lookup_tests"]["auth_users_table"]["user_id"] = auth_result.data[0]['id']
                logger.info(f"✅ Demo user found in auth.users: {auth_result.data[0]['id']}")
            else:
                logger.warning("⚠️ Demo user not found in auth.users table")
                user_data["issues"].append("Demo user not found in auth.users table - user may not be registered")
                
        except Exception as auth_error:
            user_data["user_lookup_tests"]["auth_users_table"] = {
                "status": "failed",
                "error": str(auth_error),
                "error_type": type(auth_error).__name__
            }
            # This might be expected if we don't have access to auth schema
            logger.warning(f"⚠️ Could not query auth.users table: {auth_error}")
            
    except Exception as db_error:
        user_data["database_access"] = {
            "status": "failed",
            "error": str(db_error),
            "error_type": type(db_error).__name__
        }
        user_data["issues"].append(f"Database access failed: {db_error}")
        logger.error(f"❌ Database access failed: {db_error}")
    
    return user_data

async def run_comprehensive_diagnosis():
    """Run comprehensive authentication diagnosis."""
    logger.info("🚀 Starting comprehensive authentication diagnosis...")
    
    diagnosis_results = {
        "diagnosis_timestamp": datetime.now().isoformat(),
        "environment_diagnosis": {},
        "connection_diagnosis": {},
        "authentication_diagnosis": {},
        "user_existence_diagnosis": {},
        "summary": {
            "total_issues": 0,
            "critical_issues": [],
            "recommendations": []
        }
    }
    
    try:
        # Step 1: Environment diagnosis
        logger.info("=== STEP 1: Environment Diagnosis ===")
        diagnosis_results["environment_diagnosis"] = diagnose_environment()
        
        # Step 2: Connection diagnosis
        logger.info("=== STEP 2: Connection Diagnosis ===")
        diagnosis_results["connection_diagnosis"] = diagnose_supabase_connection()
        
        # Step 3: User existence diagnosis
        logger.info("=== STEP 3: User Existence Diagnosis ===")
        diagnosis_results["user_existence_diagnosis"] = diagnose_user_existence()
        
        # Step 4: Authentication flow diagnosis
        logger.info("=== STEP 4: Authentication Flow Diagnosis ===")
        diagnosis_results["authentication_diagnosis"] = await diagnose_authentication_flow()
        
        # Compile summary
        all_issues = []
        for section in diagnosis_results.values():
            if isinstance(section, dict) and "issues" in section:
                all_issues.extend(section["issues"])
        
        diagnosis_results["summary"]["total_issues"] = len(all_issues)
        diagnosis_results["summary"]["all_issues"] = all_issues
        
        # Identify critical issues
        critical_keywords = ["database error granting user", "invalid api key", "missing required", "service key"]
        for issue in all_issues:
            if any(keyword in issue.lower() for keyword in critical_keywords):
                diagnosis_results["summary"]["critical_issues"].append(issue)
        
        # Generate recommendations
        recommendations = []
        if "demo user not found in auth.users" in str(all_issues).lower():
            recommendations.append("Create demo user in Supabase Auth using register endpoint")
        if "database error granting user" in str(all_issues).lower():
            recommendations.append("CRITICAL: Fix Supabase RLS policies - this is blocking authentication")
        if "service key" in str(all_issues).lower():
            recommendations.append("Check SUPABASE_SERVICE_ROLE_KEY configuration")
        if "connection is not available" in str(all_issues).lower():
            recommendations.append("Verify Supabase URL and network connectivity")
        
        diagnosis_results["summary"]["recommendations"] = recommendations
        
        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"auth_diagnosis_{timestamp}.json"
        with open(filename, 'w') as f:
            json.dump(diagnosis_results, f, indent=2)
        
        logger.info(f"📊 Diagnosis complete! Results saved to {filename}")
        logger.info(f"🔍 Total issues found: {len(all_issues)}")
        logger.info(f"🚨 Critical issues: {len(diagnosis_results['summary']['critical_issues'])}")
        
        return diagnosis_results
        
    except Exception as e:
        logger.error(f"❌ Diagnosis failed with exception: {e}")
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        diagnosis_results["diagnosis_error"] = {
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc()
        }
        return diagnosis_results

if __name__ == "__main__":
    import asyncio
    
    print("🔍 VELRO AUTHENTICATION DIAGNOSIS TOOL")
    print("=====================================")
    print()
    
    try:
        # Add current directory to Python path for imports
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        
        # Run diagnosis
        results = asyncio.run(run_comprehensive_diagnosis())
        
        # Print summary
        print("\n📋 DIAGNOSIS SUMMARY")
        print("===================")
        print(f"Total issues found: {results['summary']['total_issues']}")
        
        if results['summary']['critical_issues']:
            print(f"\n🚨 CRITICAL ISSUES:")
            for issue in results['summary']['critical_issues']:
                print(f"  - {issue}")
        
        if results['summary']['recommendations']:
            print(f"\n💡 RECOMMENDATIONS:")
            for rec in results['summary']['recommendations']:
                print(f"  - {rec}")
        
        print(f"\n📁 Full results available in auth_diagnosis_*.json")
        
    except Exception as e:
        print(f"❌ Diagnosis tool failed: {e}")
        print(f"❌ Traceback: {traceback.format_exc()}")
        sys.exit(1)