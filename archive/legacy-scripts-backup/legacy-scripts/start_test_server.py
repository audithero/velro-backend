#!/usr/bin/env python3
"""
Test server startup script for local deployment testing.
"""

import os
import sys
import asyncio
import subprocess
from pathlib import Path

async def start_test_server():
    """Start the test server with proper configuration."""
    print("🚀 Starting Velro Test Server")
    print("=" * 40)
    
    # Set test port
    os.environ["PORT"] = "8000"
    
    # Change to backend directory
    backend_dir = Path(__file__).parent
    os.chdir(backend_dir)
    
    print(f"📁 Working directory: {backend_dir}")
    print(f"🔌 Server will start on: http://localhost:8000")
    print(f"📊 Health check: http://localhost:8000/health")
    print(f"📖 API docs: http://localhost:8000/docs")
    print()
    
    # Start uvicorn server
    cmd = [
        sys.executable, "-m", "uvicorn",
        "main:app",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--reload",
        "--log-level", "info"
    ]
    
    print(f"🎯 Starting server with command: {' '.join(cmd)}")
    print("⏹️  Press Ctrl+C to stop the server")
    print("=" * 40)
    
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Server failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(start_test_server())
