#!/usr/bin/env python3
"""
Debug Models Endpoint Response Format
"""
import requests
import json

def debug_models_endpoint():
    base_url = 'https://velro-backend-production.up.railway.app'

    print('🔍 Debugging Models Endpoint Response')
    print('=' * 50)

    try:
        models_response = requests.get(f'{base_url}/api/v1/generations/models/supported', timeout=10)
        print(f'Status: {models_response.status_code}')
        
        if models_response.status_code == 200:
            models_data = models_response.json()
            print(f'Raw response keys: {list(models_data.keys())}')
            print(f'Models key type: {type(models_data.get("models"))}')
            
            models = models_data.get("models", [])
            print(f'Models count: {len(models)}')
            
            # Show detailed structure
            for i, model in enumerate(models[:3]):
                print(f'Model {i+1}:')
                print(f'  Type: {type(model)}')
                print(f'  Content: {model}')
                if isinstance(model, dict):
                    print(f'  Keys: {list(model.keys())}')
                    # Get the actual model ID
                    for key, value in model.items():
                        print(f'    {key}: {type(value)} - {str(value)[:100]}')
                        if hasattr(value, 'endpoint'):
                            print(f'      Endpoint: {value.endpoint}')
                print()
                
        else:
            print(f'Error response: {models_response.text}')
            
    except Exception as e:
        print(f'Error: {e}')

if __name__ == "__main__":
    debug_models_endpoint()