"""
Enhanced pytest configuration and fixtures for comprehensive Velro API testing.
Validates all PRD.MD functionality including authentication, generations, projects, and security.

CREDIT PROCESSING FIX VALIDATION - EXTENDED CONFIGURATION
Added specialized fixtures for credit processing testing.
"""
import os
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from uuid import uuid4, UUID
from datetime import datetime, timedelta
import json
from typing import Dict, Any, List, Optional

# Set testing environment variable before importing
os.environ["TESTING"] = "true"
os.environ["SUPABASE_URL"] = "https://test.supabase.co"
os.environ["SUPABASE_KEY"] = "test-anon-key"
os.environ["JWT_SECRET"] = "test-jwt-secret-key-for-testing"
os.environ["ENVIRONMENT"] = "test"

from main import app
from models.user import UserResponse, UserCreate, UserLogin
from models.project import ProjectResponse, ProjectCreate
from models.generation import GenerationResponse, GenerationCreate
from models.ai_model import AIModelResponse as AIModel


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def client():
    """Test client for FastAPI app with proper setup."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def mock_supabase_client():
    """Mock Supabase client for testing."""
    mock_client = MagicMock()
    
    # Mock table methods
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    
    # Mock query builder methods
    mock_table.select.return_value = mock_table
    mock_table.insert.return_value = mock_table
    mock_table.update.return_value = mock_table
    mock_table.delete.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.filter.return_value = mock_table
    mock_table.order.return_value = mock_table
    mock_table.limit.return_value = mock_table
    mock_table.offset.return_value = mock_table
    mock_table.single.return_value = mock_table
    mock_table.maybe_single.return_value = mock_table
    
    # Mock auth methods
    mock_auth = MagicMock()
    mock_client.auth = mock_auth
    
    return mock_client


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for caching tests."""
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.delete.return_value = True
    mock_redis.exists.return_value = False
    return mock_redis


@pytest.fixture
def sample_user_data():
    """Sample user data for testing."""
    return {
        "id": str(uuid4()),
        "email": "test@example.com",
        "display_name": "Test User",
        "avatar_url": "https://example.com/avatar.jpg",
        "credits_balance": 100,
        "role": "user",
        "created_at": datetime.utcnow(),
        "updated_at": None,
        "email_confirmed_at": datetime.utcnow(),
        "phone": None,
        "phone_confirmed_at": None
    }


@pytest.fixture
def sample_user_response(sample_user_data):
    """Sample UserResponse object for testing."""
    return UserResponse(**sample_user_data)


@pytest.fixture
def sample_user_create():
    """Sample user creation data."""
    return UserCreate(
        email="newuser@example.com",
        password="SecurePassword123!",
        full_name="New Test User"
    )


@pytest.fixture
def sample_user_login():
    """Sample user login data."""
    return UserLogin(
        email="test@example.com",
        password="correctpassword"
    )


@pytest.fixture
def sample_project_data():
    """Sample project data for testing."""
    return {
        "id": str(uuid4()),
        "title": "Test Project",
        "description": "A comprehensive test project for validation",
        "visibility": "private",
        "user_id": str(uuid4()),
        "created_at": datetime.utcnow(),
        "updated_at": None
    }


@pytest.fixture
def sample_project_response(sample_project_data):
    """Sample ProjectResponse object for testing."""
    return ProjectResponse(**sample_project_data)


@pytest.fixture
def sample_project_create():
    """Sample project creation data."""
    return ProjectCreate(
        title="New Test Project",
        description="A test project for creation testing",
        visibility="private"
    )


@pytest.fixture
def sample_generation_data(sample_user_data, sample_project_data):
    """Sample generation data for testing."""
    return {
        "id": str(uuid4()),
        "user_id": sample_user_data["id"],
        "project_id": sample_project_data["id"],
        "model_id": "fal-ai/flux-pro",
        "prompt": "A beautiful sunset over mountains",
        "negative_prompt": "blurry, low quality",
        "parameters": {"width": 1024, "height": 1024, "steps": 30},
        "status": "completed",
        "result_urls": ["https://storage.example.com/image1.jpg"],
        "error_message": None,
        "credits_cost": 10,
        "processing_time": 15.5,
        "created_at": datetime.utcnow(),
        "completed_at": datetime.utcnow() + timedelta(seconds=15)
    }


@pytest.fixture
def sample_generation_response(sample_generation_data):
    """Sample GenerationResponse object for testing."""
    return GenerationResponse(**sample_generation_data)


@pytest.fixture
def sample_generation_create():
    """Sample generation creation data."""
    return GenerationCreate(
        model_id="fal-ai/flux-pro",
        prompt="A test image generation",
        negative_prompt="low quality",
        parameters={"width": 512, "height": 512}
    )


@pytest.fixture
def sample_ai_models():
    """Sample AI models configuration for testing."""
    return [
        AIModel(
            id="fal-ai/flux-pro",
            name="FLUX.1 Pro",
            description="High-quality image generation",
            category="image",
            provider="fal-ai",
            is_active=True,
            credits_cost=10,
            parameters_schema={
                "width": {"type": "integer", "default": 1024, "min": 256, "max": 2048},
                "height": {"type": "integer", "default": 1024, "min": 256, "max": 2048},
                "steps": {"type": "integer", "default": 30, "min": 1, "max": 50}
            }
        ),
        AIModel(
            id="fal-ai/flux-dev",
            name="FLUX.1 Dev",
            description="Fast image generation for development",
            category="image",
            provider="fal-ai",
            is_active=True,
            credits_cost=5,
            parameters_schema={
                "width": {"type": "integer", "default": 512, "min": 256, "max": 1024},
                "height": {"type": "integer", "default": 512, "min": 256, "max": 1024}
            }
        )
    ]


@pytest.fixture
def mock_jwt_token():
    """Mock JWT token for authentication tests."""
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoidGVzdC11c2VyLTEyMyIsImVtYWlsIjoidGVzdEBleGFtcGxlLmNvbSIsImV4cCI6OTk5OTk5OTk5OX0.test-signature"


@pytest.fixture
def auth_headers(mock_jwt_token):
    """Authentication headers for protected endpoints."""
    return {"Authorization": f"Bearer {mock_jwt_token}"}


@pytest.fixture
def mock_fal_client():
    """Mock FAL client for AI generation testing."""
    mock_client = AsyncMock()
    
    # Mock successful generation response
    mock_client.submit.return_value = {
        "request_id": "test-request-123",
        "status": "processing"
    }
    
    mock_client.status.return_value = {
        "status": "completed",
        "result": {
            "images": [
                {"url": "https://storage.example.com/generated-image.jpg"}
            ]
        }
    }
    
    return mock_client


@pytest.fixture
def mock_storage_service():
    """Mock storage service for file upload testing."""
    mock_service = AsyncMock()
    
    mock_service.upload_file.return_value = {
        "url": "https://storage.example.com/uploaded-file.jpg",
        "file_id": str(uuid4()),
        "size": 1024000,
        "content_type": "image/jpeg"
    }
    
    mock_service.get_signed_url.return_value = "https://storage.example.com/signed-url.jpg?token=abc123"
    mock_service.delete_file.return_value = True
    
    return mock_service


@pytest.fixture
def database_test_data():
    """Comprehensive test data for database operations."""
    base_user_id = str(uuid4())
    base_project_id = str(uuid4())
    
    return {
        "users": [
            {
                "id": base_user_id,
                "email": "testuser1@example.com",
                "display_name": "Test User 1",
                "credits_balance": 100,
                "role": "user",
                "created_at": datetime.utcnow()
            },
            {
                "id": str(uuid4()),
                "email": "testuser2@example.com", 
                "display_name": "Test User 2",
                "credits_balance": 50,
                "role": "user",
                "created_at": datetime.utcnow()
            }
        ],
        "projects": [
            {
                "id": base_project_id,
                "title": "Test Project 1",
                "description": "First test project",
                "visibility": "private",
                "user_id": base_user_id,
                "created_at": datetime.utcnow()
            },
            {
                "id": str(uuid4()),
                "title": "Test Project 2", 
                "description": "Second test project",
                "visibility": "public",
                "user_id": base_user_id,
                "created_at": datetime.utcnow()
            }
        ],
        "generations": [
            {
                "id": str(uuid4()),
                "user_id": base_user_id,
                "project_id": base_project_id,
                "model_id": "fal-ai/flux-pro",
                "prompt": "Test generation 1",
                "status": "completed",
                "result_urls": ["https://storage.example.com/test1.jpg"],
                "credits_cost": 10,
                "created_at": datetime.utcnow()
            }
        ]
    }


@pytest.fixture
def mock_database_operations(mock_supabase_client, database_test_data):
    """Mock database operations with test data."""
    def mock_execute():
        """Mock execute method that returns test data."""
        return MagicMock(data=database_test_data["users"], count=len(database_test_data["users"]))
    
    mock_supabase_client.table.return_value.select.return_value.execute = mock_execute
    mock_supabase_client.table.return_value.insert.return_value.execute = mock_execute
    mock_supabase_client.table.return_value.update.return_value.execute = mock_execute
    mock_supabase_client.table.return_value.delete.return_value.execute = mock_execute
    
    return mock_supabase_client


class TestDataBuilder:
    """Builder class for creating complex test data scenarios."""
    
    @staticmethod
    def create_user_with_projects(num_projects: int = 3) -> Dict[str, Any]:
        """Create a user with multiple projects."""
        user_id = str(uuid4())
        user_data = {
            "id": user_id,
            "email": f"user-{user_id[:8]}@example.com",
            "display_name": f"Test User {user_id[:8]}",
            "credits_balance": 200,
            "role": "user",
            "created_at": datetime.utcnow()
        }
        
        projects = []
        for i in range(num_projects):
            projects.append({
                "id": str(uuid4()),
                "title": f"Project {i+1}",
                "description": f"Test project {i+1} description",
                "visibility": "private" if i % 2 == 0 else "public",
                "user_id": user_id,
                "created_at": datetime.utcnow()
            })
        
        return {"user": user_data, "projects": projects}
    
    @staticmethod
    def create_project_with_generations(num_generations: int = 5) -> Dict[str, Any]:
        """Create a project with multiple generations."""
        user_id = str(uuid4())
        project_id = str(uuid4())
        
        project_data = {
            "id": project_id,
            "title": "Test Project with Generations",
            "description": "A project containing multiple test generations",
            "visibility": "private",
            "user_id": user_id,
            "created_at": datetime.utcnow()
        }
        
        generations = []
        for i in range(num_generations):
            status = ["completed", "processing", "failed"][i % 3]
            generations.append({
                "id": str(uuid4()),
                "user_id": user_id,
                "project_id": project_id,
                "model_id": "fal-ai/flux-pro",
                "prompt": f"Test generation {i+1}",
                "status": status,
                "result_urls": [f"https://storage.example.com/gen{i+1}.jpg"] if status == "completed" else [],
                "credits_cost": 10,
                "created_at": datetime.utcnow()
            })
        
        return {"project": project_data, "generations": generations}


@pytest.fixture
def test_data_builder():
    """Test data builder fixture."""
    return TestDataBuilder


class MockSecurity:
    """Mock security utilities for testing."""
    
    @staticmethod
    def create_mock_user_context(user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create mock user context for request state."""
        return {
            "user": UserResponse(**user_data),
            "user_id": user_data["id"],
            "authenticated": True,
            "scopes": ["user"]
        }
    
    @staticmethod
    def create_mock_jwt_payload(user_id: str, email: str) -> Dict[str, Any]:
        """Create mock JWT payload."""
        return {
            "user_id": user_id,
            "email": email,
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iat": datetime.utcnow(),
            "scopes": ["user"]
        }


@pytest.fixture
def mock_security():
    """Mock security utilities fixture."""
    return MockSecurity


@pytest.fixture(autouse=True)
def clean_environment():
    """Clean up environment after each test."""
    yield
    # Clean up any test-specific environment variables or state
    # This runs after each test


@pytest.fixture
def performance_timer():
    """Timer fixture for performance testing."""
    import time
    
    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
        
        def start(self):
            self.start_time = time.time()
        
        def stop(self):
            self.end_time = time.time()
        
        @property
        def elapsed(self):
            if self.start_time and self.end_time:
                return self.end_time - self.start_time
            return None
    
    return Timer()


# Async fixtures for testing async functions
@pytest.fixture
async def async_mock_supabase_client():
    """Async mock Supabase client."""
    mock_client = AsyncMock()
    
    # Mock async methods
    mock_client.table.return_value.select.return_value.execute = AsyncMock(
        return_value=MagicMock(data=[], count=0)
    )
    mock_client.table.return_value.insert.return_value.execute = AsyncMock(
        return_value=MagicMock(data=[], count=0)
    )
    
    return mock_client


# Custom markers for test categorization
pytest_plugins = []

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "auth: mark test as authentication related")
    config.addinivalue_line("markers", "generation: mark test as generation related")
    config.addinivalue_line("markers", "project: mark test as project management related")
    config.addinivalue_line("markers", "security: mark test as security related")
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "unit: mark test as unit test")
    config.addinivalue_line("markers", "e2e: mark test as end-to-end test")
    config.addinivalue_line("markers", "performance: mark test as performance test")
    config.addinivalue_line("markers", "slow: mark test as slow running")
    
    # Credit processing fix validation markers
    config.addinivalue_line("markers", "comprehensive: mark test as comprehensive credit processing test")
    config.addinivalue_line("markers", "credit_processing: mark test as credit processing related")
    config.addinivalue_line("markers", "service_key: mark test as service key validation")
    config.addinivalue_line("markers", "pipeline: mark test as pipeline validation")
    config.addinivalue_line("markers", "production: mark test as production environment test")


# ===== CREDIT PROCESSING FIX VALIDATION FIXTURES =====

# Test configuration for credit processing
CREDIT_TEST_USER_ID = "22cb3917-57f6-49c6-ac96-ec266570081b"
CREDIT_TEST_USER_EXPECTED_CREDITS = 1200
PRODUCTION_BACKEND_URL = "https://velro-backend-production.up.railway.app"

@pytest.fixture(scope="session")
def credit_test_user_id():
    """Provide the affected user ID for credit processing tests."""
    return CREDIT_TEST_USER_ID

@pytest.fixture(scope="session")
def credit_test_expected_credits():
    """Provide expected credits for the test user."""
    return CREDIT_TEST_USER_EXPECTED_CREDITS

@pytest.fixture(scope="session")
def production_backend_url():
    """Provide production backend URL for testing."""
    return PRODUCTION_BACKEND_URL

@pytest.fixture(scope="function")
async def credit_test_environment_info():
    """Provide credit test environment information."""
    return {
        "test_user_id": CREDIT_TEST_USER_ID,
        "expected_credits": CREDIT_TEST_USER_EXPECTED_CREDITS,
        "environment": os.getenv("ENVIRONMENT", "test"),
        "supabase_url": os.getenv("SUPABASE_URL", "not_set"),
        "has_service_key": bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY")),
        "has_anon_key": bool(os.getenv("SUPABASE_ANON_KEY")),
        "has_fal_key": bool(os.getenv("FAL_KEY")),
        "production_url": PRODUCTION_BACKEND_URL
    }

@pytest.fixture(scope="function")
async def validate_credit_test_prerequisites(credit_test_environment_info):
    """Validate that all credit test prerequisites are met."""
    errors = []
    
    if not credit_test_environment_info["has_service_key"]:
        errors.append("SUPABASE_SERVICE_ROLE_KEY not configured")
    
    if not credit_test_environment_info["has_anon_key"]:
        errors.append("SUPABASE_ANON_KEY not configured")
    
    if not credit_test_environment_info["has_fal_key"]:
        errors.append("FAL_KEY not configured")
    
    if credit_test_environment_info["supabase_url"] == "not_set":
        errors.append("SUPABASE_URL not configured")
    
    if errors:
        pytest.skip(f"Credit test prerequisites not met: {', '.join(errors)}")
    
    return True

@pytest.fixture(scope="function")
def credit_test_generation_data():
    """Provide test generation data for credit processing tests."""
    from models.generation import GenerationCreate, GenerationType
    
    return GenerationCreate(
        prompt="Test prompt for credit processing validation",
        model_id="fal-ai/fast-turbo-diffusion",  # Low cost model for testing
        project_id=None,
        generation_type=GenerationType.TEXT_TO_IMAGE,
        parameters={"num_images": 1, "guidance_scale": 7.5}
    )

@pytest.fixture(scope="function")
def credit_test_transaction_data():
    """Provide test credit transaction data."""
    from services.credit_transaction_service import CreditTransaction
    from models.credit import TransactionType
    
    return CreditTransaction(
        user_id=CREDIT_TEST_USER_ID,
        amount=1,  # Minimal test amount
        transaction_type=TransactionType.USAGE,
        description="Test transaction for credit processing validation",
        metadata={"test": True, "automated_test": True, "credit_processing_fix": True}
    )

@pytest.fixture(scope="function")
def test_results_directory():
    """Ensure test results directory exists."""
    from pathlib import Path
    results_dir = Path(__file__).parent.parent / "test-results"
    results_dir.mkdir(exist_ok=True)
    return results_dir

@pytest.fixture(scope="session", autouse=True)
def log_credit_test_session_info():
    """Log credit test session information.""" 
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 80)
    logger.info("🧪 CREDIT PROCESSING FIX VALIDATION TEST SESSION")
    logger.info("=" * 80)
    logger.info(f"Test User ID: {CREDIT_TEST_USER_ID}")
    logger.info(f"Expected Credits: {CREDIT_TEST_USER_EXPECTED_CREDITS}")
    logger.info(f"Production URL: {PRODUCTION_BACKEND_URL}")
    logger.info(f"Environment: {os.getenv('ENVIRONMENT', 'test')}")
    logger.info(f"Service Key Available: {bool(os.getenv('SUPABASE_SERVICE_ROLE_KEY'))}")
    logger.info(f"Issue: Credit processing failed: Profile lookup error")
    logger.info("=" * 80)
    
    yield
    
    logger.info("=" * 80)
    logger.info("🏁 CREDIT PROCESSING FIX VALIDATION SESSION COMPLETE")
    logger.info("=" * 80)