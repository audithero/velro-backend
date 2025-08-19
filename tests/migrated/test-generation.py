import asyncio
import aiohttp
import json
import time
from datetime import datetime

async def test_full_flow():
    timestamp = int(time.time())
    email = f'e2e_test_{timestamp}@example.com'
    
    async with aiohttp.ClientSession() as session:
        # 1. Register user
        register_data = {
            'email': email,
            'password': 'TestPassword123\!',
            'full_name': 'E2E Test User'
        }
        
        print('=== E2E GENERATION TEST ===')
        print(f'Email: {email}')
        print()
        
        async with session.post(
            'https://velro-kong-gateway-production.up.railway.app/api/v1/auth/register',
            json=register_data
        ) as response:
            if response.status \!= 200:
                print('❌ Registration failed')
                return
            
            data = await response.json()
            token = data.get('access_token')
            print('✅ Registration successful')
            
        # 2. Submit generation
        headers = {'Authorization': f'Bearer {token}'}
        generation_data = {
            'model_id': 'flux-dev',
            'prompt': 'A beautiful mountain landscape at sunset',
            'parameters': {
                'num_images': 1,
                'image_size': 'square'
            }
        }
        
        print()
        print('Submitting generation...')
        
        async with session.post(
            'https://velro-kong-gateway-production.up.railway.app/api/v1/generations/submit',
            json=generation_data,
            headers=headers
        ) as response:
            print(f'Submit status: {response.status}')
            
            if response.status == 200:
                data = await response.json()
                generation_id = data.get('generation_id')
                print(f'✅ Generation submitted: {generation_id}')
                print(f'   Status: {data.get("status")}')
                print(f'   Cached: {data.get("cached", False)}')
                print(f'   Queue position: {data.get("queue_position")}')
                
                # 3. Poll for completion
                if not data.get('cached'):
                    print()
                    print('Polling for completion...')
                    
                    for i in range(30):
                        await asyncio.sleep(2)
                        
                        async with session.get(
                            f'https://velro-kong-gateway-production.up.railway.app/api/v1/generations/{generation_id}/status',
                            headers=headers
                        ) as status_response:
                            if status_response.status == 200:
                                status_data = await status_response.json()
                                status = status_data.get('status')
                                print(f'   Poll {i+1}: {status}')
                                
                                if status == 'completed':
                                    print(f'✅ Generation completed\!')
                                    print(f'   Output URLs: {status_data.get("output_urls")}')
                                    break
                                elif status == 'failed':
                                    print(f'❌ Generation failed: {status_data.get("error")}')
                                    break
            else:
                error_text = await response.text()
                print(f'❌ Submit failed: {error_text[:200]}')

asyncio.run(test_full_flow())
