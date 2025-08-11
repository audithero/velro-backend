#!/bin/bash
"""
Auth Performance Test Runner
Simple wrapper script for running performance tests with different configurations.
"""

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Auth Performance Test Runner${NC}"
echo "=================================="

# Default values
BASE_URL="http://localhost:8000"
PING_REQUESTS=50
LOGIN_REQUESTS=20

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --url)
      BASE_URL="$2"
      shift 2
      ;;
    --ping-requests)
      PING_REQUESTS="$2"
      shift 2
      ;;
    --login-requests)
      LOGIN_REQUESTS="$2"
      shift 2
      ;;
    --production)
      BASE_URL="https://velro-003-backend-production.up.railway.app"
      echo -e "${YELLOW}⚠️ Using production URL: $BASE_URL${NC}"
      shift
      ;;
    --quick)
      PING_REQUESTS=10
      LOGIN_REQUESTS=5
      echo -e "${YELLOW}⚡ Quick test mode: fewer requests${NC}"
      shift
      ;;
    --extensive)
      PING_REQUESTS=100
      LOGIN_REQUESTS=50
      echo -e "${YELLOW}🔍 Extensive test mode: more requests${NC}"
      shift
      ;;
    -h|--help)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --url URL              Base URL to test (default: http://localhost:8000)"
      echo "  --ping-requests N      Number of ping requests (default: 50)"
      echo "  --login-requests N     Number of login requests (default: 20)"
      echo "  --production          Use production URL"
      echo "  --quick               Quick test (fewer requests)"
      echo "  --extensive           Extensive test (more requests)"
      echo "  -h, --help            Show this help"
      echo ""
      echo "Examples:"
      echo "  $0                              # Test localhost with defaults"
      echo "  $0 --production                 # Test production environment"
      echo "  $0 --url http://localhost:3000  # Test custom URL"
      echo "  $0 --quick                      # Quick test with fewer requests"
      exit 0
      ;;
    *)
      echo -e "${RED}❌ Unknown option: $1${NC}"
      exit 1
      ;;
  esac
done

echo "Configuration:"
echo "  Target URL: $BASE_URL"
echo "  Ping requests: $PING_REQUESTS"
echo "  Login requests: $LOGIN_REQUESTS"
echo ""

# Check if server is running
echo -e "${BLUE}🔍 Checking server availability...${NC}"
if curl -s -f "$BASE_URL/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Server is responding at $BASE_URL${NC}"
else
    echo -e "${RED}❌ Server is not responding at $BASE_URL${NC}"
    echo "   Please ensure the server is running before running performance tests."
    exit 1
fi

# Check if Python script exists
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/test_auth_performance.py"

if [[ ! -f "$PYTHON_SCRIPT" ]]; then
    echo -e "${RED}❌ Performance test script not found: $PYTHON_SCRIPT${NC}"
    exit 1
fi

# Check Python dependencies
echo -e "${BLUE}🔍 Checking Python dependencies...${NC}"
if ! python3 -c "import aiohttp, asyncio" 2>/dev/null; then
    echo -e "${YELLOW}⚠️ Installing required Python packages...${NC}"
    pip3 install aiohttp || {
        echo -e "${RED}❌ Failed to install aiohttp. Please install manually:${NC}"
        echo "   pip3 install aiohttp"
        exit 1
    }
fi

echo -e "${GREEN}✅ Dependencies available${NC}"
echo ""

# Run the performance test
echo -e "${BLUE}🚀 Starting performance tests...${NC}"
echo "Target Performance:"
echo "  - Ping P95: <200ms (ideal: <50ms)"
echo "  - Login P95: <1500ms"
echo ""

# Run with timeout to prevent hanging
timeout 300 python3 "$PYTHON_SCRIPT" \
    --url "$BASE_URL" \
    --ping-requests "$PING_REQUESTS" \
    --login-requests "$LOGIN_REQUESTS" || {
    
    exit_code=$?
    if [[ $exit_code -eq 124 ]]; then
        echo -e "${RED}❌ Performance test timed out after 5 minutes${NC}"
    elif [[ $exit_code -eq 1 ]]; then
        echo -e "${YELLOW}⚠️ Some performance targets not met${NC}"
    else
        echo -e "${RED}❌ Performance test failed with exit code $exit_code${NC}"
    fi
    exit $exit_code
}

echo ""
echo -e "${GREEN}🎉 Performance tests completed successfully!${NC}"