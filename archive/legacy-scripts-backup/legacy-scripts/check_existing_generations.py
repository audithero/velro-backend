#!/usr/bin/env python3
"""
Check existing generations to see if the system has worked before
"""
import asyncio
import httpx

PRODUCTION_URL = "https://velro-backend-production.up.railway.app"
TEST_USER_ID = "bd1a2f69-89eb-489f-9288-8aacf4924763"

async def check_existing_generations():
    """Check what generations already exist."""
    print("🔍 CHECKING EXISTING GENERATIONS")
    print("=" * 50)
    
    auth_token = f"supabase_token_{TEST_USER_ID}"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{PRODUCTION_URL}/api/v1/generations/",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            
            if response.status_code == 200:
                generations = response.json()
                print(f"✅ Found {len(generations)} existing generations")
                
                if generations:
                    print("\nRecent generations:")
                    for i, gen in enumerate(generations[:5]):  # Show first 5
                        print(f"\n  Generation {i+1}:")
                        print(f"    ID: {gen.get('id')}")
                        print(f"    Status: {gen.get('status')}")
                        print(f"    Model: {gen.get('model_id')}")
                        print(f"    Prompt: {gen.get('prompt', '')[:50]}...")
                        print(f"    Created: {gen.get('created_at')}")
                        
                        output_urls = gen.get('output_urls', [])
                        if output_urls:
                            print(f"    Images: {len(output_urls)} URLs")
                            print(f"      First URL: {output_urls[0][:60]}...")
                        else:
                            print(f"    Images: None")
                    
                    # Check if any successful generations exist
                    successful = [g for g in generations if g.get('status') == 'completed' and g.get('output_urls')]
                    failed = [g for g in generations if g.get('status') == 'failed']
                    pending = [g for g in generations if g.get('status') in ['pending', 'processing']]
                    
                    print(f"\n📊 Generation Statistics:")
                    print(f"  ✅ Successful: {len(successful)}")
                    print(f"  ❌ Failed: {len(failed)}")
                    print(f"  ⏳ Pending/Processing: {len(pending)}")
                    
                    if successful:
                        print(f"\n🎉 System has worked before! Example successful generation:")
                        example = successful[0]
                        print(f"  Model: {example.get('model_id')}")
                        print(f"  Prompt: {example.get('prompt')}")
                        print(f"  Images: {len(example.get('output_urls', []))}")
                        return True
                    else:
                        print(f"\n⚠️ No successful generations found")
                        if failed:
                            print(f"   All {len(failed)} attempts have failed")
                            # Check last failure
                            last_failed = failed[0]
                            print(f"   Last failure: {last_failed.get('model_id')} - {last_failed.get('created_at')}")
                        return False
                else:
                    print("ℹ️ No generations found for this user")
                    return None
                    
            else:
                print(f"❌ Failed to get generations: {response.status_code}")
                return False
                
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

async def main():
    result = await check_existing_generations()
    
    print("\n" + "=" * 50)
    print("🏁 ANALYSIS")
    print("=" * 50)
    
    if result is True:
        print("✅ SYSTEM HAS WORKED BEFORE")
        print("   The production endpoint has successfully created generations")
        print("   Current 500 errors may be temporary issues with:")
        print("   - FAL API availability")
        print("   - Temporary service disruption")
        print("   - Credits/billing issues")
        
    elif result is False:
        print("⚠️ SYSTEM HAS ISSUES")
        print("   Previous generation attempts have failed")
        print("   This suggests persistent problems with:")
        print("   - FAL API integration")
        print("   - Configuration issues")
        print("   - Service setup")
        
    elif result is None:
        print("ℹ️ FRESH SYSTEM")
        print("   No previous generation attempts")
        print("   Current 500 errors are the first test results")
        
    else:
        print("❌ CANNOT DETERMINE STATUS")
        print("   Unable to retrieve generation history")

if __name__ == "__main__":
    asyncio.run(main())