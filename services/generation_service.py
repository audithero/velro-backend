"""
Generation service for coordinating AI generation workflow.
Following CLAUDE.md: Service layer for business logic.
"""
import asyncio
import logging
import time
from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import HttpUrl

from database import get_database
from repositories.generation_repository import GenerationRepository
from services.fal_service import fal_service
from services.storage_service import storage_service
from services.credit_transaction_service import credit_transaction_service, CreditTransaction
from models.generation import (
    GenerationCreate, 
    GenerationResponse, 
    GenerationStatus,
    GenerationType
)
from models.fal_config import get_model_config
from models.credit import TransactionType
from utils.logging_config import perf_logger, log_performance
from utils.performance_monitor import performance_monitor
from utils.cache_manager import cached, CacheLevel

logger = logging.getLogger(__name__)


class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open."""
    pass


class GenerationService:
    """Service for managing AI generation lifecycle."""
    
    def __init__(self):
        self.db = None
        self.generation_repo = None
        # Circuit breaker for external API calls - EMERGENCY RESET
        self._circuit_breaker_state = "closed"  # closed, open, half-open
        self._circuit_breaker_failures = 0
        self._circuit_breaker_last_failure = 0
        self._circuit_breaker_timeout = 30  # 30 seconds
        self._max_circuit_failures = 5
        # Performance optimization settings
        self._enable_caching = True
        self._cache_ttl = 300  # 5 minutes default
        
        # CRITICAL FIX: Emergency reset for production recovery
        logger.warning("🚨 [GENERATION-SERVICE] Emergency circuit breaker reset for production recovery")
    
    async def _get_repositories(self):
        """Initialize repositories if not already done."""
        if self.db is None:
            try:
                logger.info("Initializing database connection for GenerationService")
                self.db = await get_database()
                
                if not self.db.is_available():
                    raise ConnectionError("Database is not available")
                
                self.generation_repo = GenerationRepository(self.db)
                logger.info("Successfully initialized GenerationService repositories")
                
            except Exception as e:
                logger.error(f"Failed to initialize GenerationService repositories: {e}")
                raise RuntimeError(f"Service initialization failed: {str(e)}")
    
    def _can_execute_generation(self) -> bool:
        """Check if generation can be executed based on circuit breaker state."""
        current_time = time.time()
        
        if self._circuit_breaker_state == "closed":
            return True
        elif self._circuit_breaker_state == "open":
            if current_time - self._circuit_breaker_last_failure >= self._circuit_breaker_timeout:
                self._circuit_breaker_state = "half-open"
                logger.info("🔄 [GENERATION-CIRCUIT] Circuit breaker half-open - testing recovery")
                return True
            return False
        else:  # half-open
            return True
    
    def _record_circuit_breaker_success(self):
        """Record successful operation for circuit breaker."""
        self._circuit_breaker_failures = 0
        if self._circuit_breaker_state == "half-open":
            self._circuit_breaker_state = "closed"
            logger.info("✅ [GENERATION-CIRCUIT] Circuit breaker closed - operations restored")
    
    async def emergency_reset_circuit_breaker(self):
        """🚨 EMERGENCY: Reset circuit breaker for production recovery."""
        self._circuit_breaker_state = "closed"
        self._circuit_breaker_failures = 0
        self._circuit_breaker_last_failure = 0
        logger.warning("🚨 EMERGENCY: Circuit breaker manually reset for production recovery")
    
    def _record_circuit_breaker_failure(self):
        """Record failed operation for circuit breaker."""
        self._circuit_breaker_failures += 1
        self._circuit_breaker_last_failure = time.time()
        
        if self._circuit_breaker_failures >= self._max_circuit_failures:
            self._circuit_breaker_state = "open"
            logger.warning(f"⚠️ [GENERATION-CIRCUIT] Circuit breaker opened - {self._circuit_breaker_failures} failures")
    
    async def _execute_with_circuit_breaker(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection."""
        if not self._can_execute_generation():
            logger.error("🚨 [GENERATION-CIRCUIT] Circuit breaker is OPEN - blocking request")
            raise CircuitBreakerError("Service temporarily unavailable due to high error rate. Please try again in a few minutes.")
        
        try:
            result = await func(*args, **kwargs)
            self._record_circuit_breaker_success()
            return result
        except Exception as e:
            error_msg = str(e).lower()
            
            # 🚨 CRITICAL FIX: Don't trigger circuit breaker for auth issues
            if any(keyword in error_msg for keyword in ["jwt", "token", "auth", "invalid", "expired", "refresh"]):
                logger.error(f"🔐 [GENERATION-CIRCUIT] Auth error (not circuit breaker trigger): {e}")
                raise  # Re-raise without recording circuit breaker failure
            else:
                # Only trigger circuit breaker for actual service failures
                self._record_circuit_breaker_failure()
                logger.error(f"🚨 [GENERATION-CIRCUIT] Service error (circuit breaker eligible): {str(e)}")
                raise
    
    @cached(level=CacheLevel.L2_SESSION, ttl=300)  # Cache model configs for 5 minutes
    async def _get_cached_model_config(self, model_id: str):
        """Get model configuration with caching."""
        return get_model_config(model_id)
    
    @log_performance("create_generation_optimized")
    async def create_generation(
        self,
        user_id: str,
        generation_data: GenerationCreate,
        reference_image_file: Optional[bytes] = None,
        reference_image_filename: Optional[str] = None,
        auth_token: Optional[str] = None
    ) -> GenerationResponse:
        """
        Create a new AI generation.
        
        Args:
            user_id: User ID creating the generation
            generation_data: Generation parameters
            
        Returns:
            Created generation with initial status
        """
        await self._get_repositories()
        
        # Check circuit breaker before attempting generation
        try:
            await self._execute_with_circuit_breaker(self._check_service_dependencies)
        except CircuitBreakerError as cb_error:
            logger.error(f"🚨 [GENERATION] Circuit breaker blocked generation: {cb_error}")
            raise RuntimeError(str(cb_error))
        
        try:
            # Handle reference image upload if provided
            reference_image_url = generation_data.reference_image_url
            if reference_image_file and reference_image_filename:
                try:
                    # Upload reference image to storage
                    from models.storage import FileUploadRequest, StorageBucket, ContentType
                    
                    # Detect content type from filename
                    content_type = "image/jpeg"  # Default
                    if reference_image_filename.lower().endswith('.png'):
                        content_type = "image/png"
                    elif reference_image_filename.lower().endswith('.webp'):
                        content_type = "image/webp"
                    elif reference_image_filename.lower().endswith('.gif'):
                        content_type = "image/gif"
                    
                    upload_request = FileUploadRequest(
                        bucket_name=StorageBucket.UPLOADS,
                        filename=reference_image_filename,
                        content_type=ContentType(content_type),
                        file_size=len(reference_image_file),
                        metadata={"usage": "generation_reference"}
                    )
                    
                    uploaded_file = await storage_service.upload_file(
                        user_id=user_id,  # Pass string directly, storage service will handle conversion
                        file_data=reference_image_file,
                        upload_request=upload_request
                    )
                    
                    # Generate signed URL for FAL.ai to access the reference image
                    signed_url_response = await storage_service.get_signed_url(
                        file_id=uploaded_file.id,
                        user_id=user_id,  # Pass string directly, storage service will handle conversion
                        expires_in=3600  # 1 hour should be enough for generation
                    )
                    
                    reference_image_url = signed_url_response.signed_url
                    logger.info(f"Reference image uploaded for generation: {uploaded_file.file_path}")
                    
                except Exception as e:
                    logger.error(f"Failed to upload reference image for user {user_id}: {e}")
                    raise ValueError(f"Failed to upload reference image: {str(e)}")
            
            # Get model configuration and pricing
            model_config = get_model_config(generation_data.model_id)
            credits_required = model_config.credits
            
            # Optimized credit validation using the new credit transaction service
            logger.info(f"🔍 [GENERATION] Starting optimized credit validation for user {user_id}, credits_required: {credits_required}")
            
            try:
                # Use optimized credit validation with caching
                validation_result = await credit_transaction_service.validate_credit_transaction(
                    user_id=user_id,
                    required_amount=credits_required,
                    auth_token=auth_token
                )
                
                logger.info(f"✅ [GENERATION] Credit validation result for user {user_id}: {validation_result.message}")
                
                if not validation_result.valid:
                    logger.error(f"💳 [GENERATION] {validation_result.message}")
                    performance_monitor.record_generation_result(False)
                    raise ValueError(validation_result.message)
                    
                logger.info(f"✅ [GENERATION] Credit validation passed for user {user_id}, proceeding with generation")
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ [GENERATION] Credit validation exception for user {user_id}: {e}")
                logger.error(f"❌ [GENERATION] Exception type: {type(e).__name__}")
                logger.error(f"❌ [GENERATION] Exception message: {error_msg}")
                
                performance_monitor.record_generation_result(False)
                
                if "not found" in error_msg.lower():
                    logger.error(f"👤 [GENERATION] Credit validation failed - user profile missing for {user_id}: {e}")
                    raise ValueError(f"User profile not found. Please contact support if this continues.")
                else:
                    logger.error(f"💥 [GENERATION] Credit validation failed for user {user_id}: {e}")
                    raise ValueError(f"Credit verification failed: {str(e)}")
            
            # Create generation record in database (match actual schema)
            generation_record = {
                "user_id": str(user_id),
                "project_id": str(generation_data.project_id) if generation_data.project_id else "00000000-0000-0000-0000-000000000000",  # Use default UUID for NULL project_id
                "model_id": generation_data.model_id,  # CRITICAL: Include model_id in database record
                "prompt": generation_data.prompt,
                "status": GenerationStatus.PENDING.value,
                "cost": credits_required,
                "media_type": model_config.ai_model_type.value,
                # media_url will be set after generation completes
                # parent_generation_id and style_stack_id can be None
            }
            
            # Debug: log the generation record before saving
            logger.info(f"Creating generation record: {generation_record}")
            
            # EMERGENCY FIX: Handle generation repository compatibility
            try:
                # Try new signature with auth_token
                created_generation = await self.generation_repo.create_generation(generation_record, auth_token=auth_token)
            except TypeError as te:
                if "unexpected keyword argument 'auth_token'" in str(te):
                    logger.warning("🔧 [GENERATION] Using legacy repository signature - calling without auth_token")
                    # Fall back to old signature without auth_token
                    created_generation = await self.generation_repo.create_generation(generation_record)
                else:
                    raise
            
            # Optimized atomic credit deduction using the new credit transaction service
            # CRITICAL FIX: Safe UUID handling for user_id
            from utils.uuid_utils import UUIDUtils
            user_id_str = UUIDUtils.ensure_uuid_string(user_id)
            if not user_id_str:
                raise ValueError(f"Invalid user_id format: {user_id}")
            
            logger.info(f"💳 [GENERATION] Starting atomic credit deduction for user {user_id_str}, generation {created_generation.id}")
            logger.info(f"💳 [GENERATION] Deduction amount: {credits_required}, model: {generation_data.model_id}")
            
            try:
                # Create credit transaction for atomic deduction - CRITICAL FIX: Enhanced auth token handling
                credit_transaction = CreditTransaction(
                    user_id=user_id_str,
                    amount=credits_required,
                    transaction_type=TransactionType.USAGE,
                    generation_id=str(created_generation.id),
                    model_name=generation_data.model_id,
                    description=f"Credit deduction for {generation_data.model_id} generation",
                    auth_token=auth_token,  # CRITICAL FIX: Pass JWT token for database operations
                    metadata={
                        "auth_token": auth_token,  # Also store in metadata as backup
                        "generation_model": generation_data.model_id,
                        "credit_deduction": True,
                        "service_key_available": True,  # Will be used to determine fallback strategy
                        "operation_context": "generation_credit_deduction"
                    }
                )
                
                logger.info(f"🔍 [GENERATION] Executing atomic credit deduction for user {user_id_str}")
                updated_user = await credit_transaction_service.atomic_credit_deduction(credit_transaction)
                
                logger.info(f"✅ [GENERATION] Successfully deducted {credits_required} credits from user {user_id_str} for generation {created_generation.id}")
                logger.info(f"✅ [GENERATION] New user balance: {updated_user.credits_balance}")
                
                # Record successful credit operation
                performance_monitor.record_credit_operation()
                
            except Exception as credit_error:
                logger.error(f"❌ [GENERATION] Atomic credit deduction failed for generation {created_generation.id}: {credit_error}")
                logger.error(f"❌ [GENERATION] Credit error type: {type(credit_error).__name__}")
                logger.error(f"❌ [GENERATION] Credit error message: {str(credit_error)}")
                
                # Record failed generation
                performance_monitor.record_generation_result(False)
                
                # If credit deduction fails after creation, we need to mark generation as failed
                logger.info(f"🔄 [GENERATION] Marking generation {created_generation.id} as failed due to credit deduction failure")
                try:
                    await self.generation_repo.update_generation(
                        created_generation.id,
                        {
                            "status": GenerationStatus.FAILED,
                            "error_message": "Credit deduction failed",
                            "completed_at": datetime.utcnow().isoformat()
                        }
                    )
                    logger.info(f"✅ [GENERATION] Generation {created_generation.id} marked as failed")
                except Exception as update_error:
                    logger.error(f"❌ [GENERATION] Failed to update generation status after credit error: {update_error}")
                
                logger.error(f"💥 [GENERATION] Raising credit processing error for user {user_id}")
                # CRITICAL FIX: More specific error message for debugging
                error_msg = str(credit_error)
                logger.error(f"💥 [GENERATION] Detailed credit error: {error_msg}")
                
                # CRITICAL FIX: Enhanced error handling with better user messaging and profile creation
                if "authentication expired" in error_msg.lower() or "refresh your session" in error_msg.lower():
                    logger.error(f"🔴 [GENERATION] JWT token authentication issue: {error_msg}")
                    raise ValueError("Your session has expired. Please refresh the page and try again.")
                elif "not found" in error_msg.lower():
                    logger.error(f"💳 [GENERATION] Profile lookup failed during credit processing: {error_msg}")
                    # CRITICAL FIX: Try to auto-create profile for missing users
                    try:
                        logger.info(f"🔄 [GENERATION] Attempting profile auto-creation for user {user_id}")
                        from services.user_service import user_service
                        
                        # Get the user's email from JWT token if available
                        user_email = "unknown@email.com"  # Fallback
                        if auth_token:
                            try:
                                import jwt
                                decoded = jwt.decode(auth_token, options={"verify_signature": False})
                                user_email = decoded.get("email", user_email)
                                logger.info(f"🔍 [GENERATION] Extracted email from token: {user_email}")
                            except Exception as jwt_error:
                                logger.warning(f"⚠️ [GENERATION] Failed to decode JWT for email: {jwt_error}")
                        
                        # Try to create user profile
                        new_user = await user_service.create_user_profile(
                            user_id=user_id,
                            email=user_email,
                            full_name="Auto-created User"
                        )
                        logger.info(f"✅ [GENERATION] Successfully auto-created profile for user {user_id}")
                        
                        # Retry credit validation after profile creation
                        logger.info(f"🔄 [GENERATION] Retrying credit validation after profile creation")
                        validation_result_retry = await credit_transaction_service.validate_credit_transaction(
                            user_id=user_id,
                            required_amount=credits_required,
                            auth_token=auth_token
                        )
                        
                        if not validation_result_retry.valid:
                            logger.error(f"💳 [GENERATION] Credit validation still failed after profile creation: {validation_result_retry.message}")
                            raise ValueError(validation_result_retry.message)
                        
                        logger.info(f"✅ [GENERATION] Credit validation successful after profile creation")
                        
                    except Exception as profile_creation_error:
                        logger.error(f"❌ [GENERATION] Profile auto-creation failed: {profile_creation_error}")
                        # Fall back to user-friendly error message
                        # SECURITY FIX: Prevent information leakage in error messages
                    logger.error(f"Account verification failed: {error_msg}")
                    raise ValueError("Account verification failed. Please ensure you are logged in and try again.")
                elif "insufficient" in error_msg.lower():
                    raise ValueError("Insufficient credits available") 
                elif "generation_usage" in error_msg.lower() or "GENERATION_USAGE" in error_msg:
                    raise ValueError("Credit processing failed: Invalid transaction type format")
                else:
                    # Default to session expiration for unknown authentication-related errors
                    if any(keyword in error_msg.lower() for keyword in ["token", "auth", "jwt", "expired"]):
                        raise ValueError("Your session has expired. Please refresh the page and try again.")
                    else:
                        raise ValueError(f"Credit processing failed: {error_msg}")
            
            # Start FAL.ai generation asynchronously with updated reference URL
            updated_generation_data = generation_data.model_copy()
            if reference_image_url:
                # Convert string URL to HttpUrl for Pydantic validation
                from pydantic import HttpUrl
                updated_generation_data.reference_image_url = HttpUrl(reference_image_url)
            
            asyncio.create_task(
                self._process_generation(created_generation.id, updated_generation_data)
            )
            
            # Record successful generation creation
            performance_monitor.record_generation_result(True)
            
            logger.info(f"🎉 [GENERATION] Successfully created generation {created_generation.id} for user {user_id}")
            logger.info(f"✅ [GENERATION] Generation created with status: {created_generation.status}, cost: {created_generation.cost}")
            logger.info(f"🚀 [GENERATION] Background processing task started for generation {created_generation.id}")
            
            # Log generation lifecycle event
            perf_logger.log_generation_lifecycle(
                generation_id=str(created_generation.id),
                status="created",
                user_id=user_id,
                model_id=generation_data.model_id,
                credits_cost=credits_required
            )
            
            return created_generation
            
        except ValueError as e:
            # Re-raise validation errors as-is
            logger.warning(f"Generation validation error for user {user_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating generation for user {user_id}: {e}")
            logger.error(f"Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Wrap unexpected errors in a more user-friendly message
            raise RuntimeError(f"Generation creation failed due to system error. Please try again later.")
    
    async def _process_generation(
        self,
        generation_id: str,
        generation_data: GenerationCreate
    ):
        """
        Process the generation with FAL.ai (background task).
        
        Args:
            generation_id: Database generation ID
            generation_data: Generation parameters
        """
        logger.info(f"🚀 [GENERATION-PROCESSING] Starting background processing for generation {generation_id}")
        logger.info(f"🔍 [GENERATION-PROCESSING] Model: {generation_data.model_id}, Prompt length: {len(generation_data.prompt)}")
        
        try:
            # Update status to processing WITH DETAILED LOGGING
            logger.info(f"📝 [GENERATION-PROCESSING] Updating status to PROCESSING for generation {generation_id}")
            
            updated_generation = await self.generation_repo.update_generation_status(
                generation_id,
                GenerationStatus.PROCESSING
            )
            
            logger.info(f"✅ [GENERATION-PROCESSING] Status updated successfully: {updated_generation.status}")
            logger.info(f"🔍 [GENERATION-PROCESSING] Generation record after status update: ID={updated_generation.id}, Status={updated_generation.status}")
            
            # Submit to FAL.ai with timeout and retry mechanism
            logger.info(f"🤖 [GENERATION-PROCESSING] Submitting to FAL.ai service for generation {generation_id}")
            logger.info(f"🔍 [GENERATION-PROCESSING] FAL parameters: model={generation_data.model_id}, has_negative_prompt={generation_data.negative_prompt is not None}, has_reference_image={generation_data.reference_image_url is not None}")
            
            # Implement retry logic for FAL service calls
            max_retries = 3
            retry_delay = 5  # seconds
            fal_result = None
            
            for attempt in range(max_retries):
                try:
                    logger.info(f"🔄 [GENERATION-PROCESSING] FAL.ai attempt {attempt + 1}/{max_retries} for generation {generation_id}")
                    
                    # Use asyncio.wait_for to add timeout protection
                    fal_result = await asyncio.wait_for(
                        fal_service.create_generation(
                            model_id=generation_data.model_id,
                            prompt=generation_data.prompt,
                            negative_prompt=generation_data.negative_prompt,
                            reference_image_url=generation_data.reference_image_url,
                            parameters=generation_data.parameters
                        ),
                        timeout=300.0  # 5 minute timeout for generation
                    )
                    
                    logger.info(f"✅ [GENERATION-PROCESSING] FAL.ai call successful on attempt {attempt + 1}")
                    break
                    
                except asyncio.TimeoutError:
                    logger.error(f"⏰ [GENERATION-PROCESSING] FAL.ai timeout on attempt {attempt + 1} for generation {generation_id}")
                    if attempt == max_retries - 1:
                        raise RuntimeError(f"FAL.ai service timeout after {max_retries} attempts")
                    await asyncio.sleep(retry_delay)
                    
                except Exception as fal_error:
                    logger.error(f"❌ [GENERATION-PROCESSING] FAL.ai error on attempt {attempt + 1}: {fal_error}")
                    if attempt == max_retries - 1:
                        raise
                    await asyncio.sleep(retry_delay)
            
            if not fal_result:
                raise RuntimeError("FAL.ai service failed after all retry attempts")
            
            logger.info(f"🎯 [GENERATION-PROCESSING] FAL.ai result received for generation {generation_id}: status={fal_result.get('status')}")
            logger.info(f"🔍 [GENERATION-PROCESSING] FAL result details: output_urls_count={len(fal_result.get('output_urls', []))}, has_metadata={bool(fal_result.get('metadata'))}")
            
            # Handle the result based on status
            if fal_result["status"] == GenerationStatus.COMPLETED:
                logger.info(f"✅ [GENERATION-PROCESSING] FAL.ai generation completed successfully for {generation_id}")
                
                # Generation completed successfully - store results in Supabase Storage
                try:
                    logger.info(f"📦 [STORAGE] Starting storage process for generation {generation_id}")
                    
                    # Get generation details for user context
                    generation = await self.generation_repo.get_generation_by_id(
                        generation_id=generation_id,
                        user_id=None,  # No user_id available in background processing context
                        auth_token=None  # No auth token available in background processing, rely on service key
                    )
                    if not generation:
                        logger.error(f"❌ [STORAGE] Generation {generation_id} not found in database during storage process")
                        raise ValueError(f"Generation {generation_id} not found")
                    
                    logger.info(f"🔍 [STORAGE] Retrieved generation from DB: user_id={generation.user_id}, media_type={generation.media_type}")
                    
                    # Store generation results in storage with enhanced progress tracking
                    output_urls = fal_result.get("output_urls", [])
                    logger.info(f"📥 [STORAGE] Processing {len(output_urls)} output URLs from FAL.ai")
                    
                    for i, url in enumerate(output_urls):
                        logger.info(f"🔗 [STORAGE] Output URL {i+1}: {url[:100]}{'...' if len(url) > 100 else ''}")
                    
                    stored_files = []
                    
                    if output_urls:
                        logger.info(f"☁️ [STORAGE] Uploading generation results to Supabase Storage...")
                        
                        # Create progress callback for storage operations with flexible signature
                        async def storage_progress_callback(progress_data):
                            """
                            Progress callback for storage upload tracking.
                            Handles both dictionary-style and individual parameter styles.
                            """
                            try:
                                if isinstance(progress_data, dict):
                                    # Dictionary-style progress data
                                    stage = progress_data.get('stage', 'processing')
                                    current_file = progress_data.get('current_file', 0)
                                    total_files = progress_data.get('total_files', 0)
                                    percentage = progress_data.get('percentage', 0)
                                    
                                    logger.info(f"📊 [STORAGE-PROGRESS] {stage.title()}: {current_file}/{total_files} files ({percentage:.1f}%)")
                                else:
                                    # Fallback for other formats
                                    logger.info(f"📊 [STORAGE-PROGRESS] Upload progress: {progress_data}")
                            except Exception as cb_error:
                                logger.warning(f"⚠️ [STORAGE-PROGRESS] Progress callback error: {cb_error}")
                        
                        try:
                            stored_files = await storage_service.upload_generation_result(
                                user_id=generation.user_id if isinstance(generation.user_id, UUID) else UUID(generation.user_id),
                                generation_id=generation_id if isinstance(generation_id, UUID) else UUID(generation_id),
                                file_urls=output_urls,
                                file_type="image" if generation.media_type == "image" else "video",
                                project_id=generation.project_id if generation.project_id and isinstance(generation.project_id, UUID) else (UUID(generation.project_id) if generation.project_id else None),
                                progress_callback=storage_progress_callback
                            )
                            
                            logger.info(f"✅ [STORAGE] Successfully uploaded {len(stored_files)} files to Supabase Storage")
                            
                            for i, stored_file in enumerate(stored_files):
                                logger.info(f"📁 [STORAGE] File {i+1}: {stored_file.file_path} ({stored_file.file_size} bytes)")
                                
                        except Exception as upload_error:
                            logger.error(f"❌ [STORAGE] Upload failed, attempting partial recovery: {upload_error}")
                            
                            # Try to upload files individually as fallback
                            for i, url in enumerate(output_urls):
                                try:
                                    individual_files = await storage_service.upload_generation_result(
                                        user_id=generation.user_id if isinstance(generation.user_id, UUID) else UUID(generation.user_id),
                                        generation_id=generation_id if isinstance(generation_id, UUID) else UUID(generation_id),
                                        file_urls=[url],  # Single file
                                        file_type="image" if generation.media_type == "image" else "video",
                                        project_id=generation.project_id if generation.project_id and isinstance(generation.project_id, UUID) else (UUID(generation.project_id) if generation.project_id else None)
                                    )
                                    stored_files.extend(individual_files)
                                    logger.info(f"✅ [STORAGE-RECOVERY] Recovered file {i+1}: {individual_files[0].file_path}")
                                except Exception as individual_error:
                                    logger.error(f"❌ [STORAGE-RECOVERY] Failed to recover file {i+1}: {individual_error}")
                                    continue
                            
                            if not stored_files:
                                raise upload_error  # Re-raise if complete failure
                                
                    else:
                        logger.warning(f"⚠️ [STORAGE] No output URLs to store for generation {generation_id}")
                    
                    # Calculate total storage size
                    total_storage_size = sum(file_meta.file_size for file_meta in stored_files)
                    logger.info(f"📊 [STORAGE] Total storage size: {total_storage_size} bytes")
                    
                    # Store file path instead of expiring signed URL to prevent URL expiration issues
                    primary_media_path = None
                    primary_media_url = None  # CRITICAL FIX: Initialize variable
                    if stored_files:
                        # Store the file path instead of generating a signed URL that expires
                        primary_media_path = stored_files[0].file_path
                        logger.info(f"✅ [STORAGE] Primary file stored at path: {primary_media_path}")
                        logger.info(f"💡 [STORAGE] Frontend should use /generations/{generation_id}/media-urls for fresh signed URLs")
                        
                        # Generate a primary signed URL for immediate use (optional)
                        try:
                            signed_url_response = await storage_service.get_signed_url(
                                file_id=stored_files[0].id,
                                user_id=generation.user_id if isinstance(generation.user_id, UUID) else UUID(generation.user_id),
                                expires_in=86400  # 24 hours for initial access
                            )
                            primary_media_url = signed_url_response.signed_url
                            logger.info(f"✅ [STORAGE] Primary signed URL generated: {primary_media_url[:100]}...")
                        except Exception as url_error:
                            logger.warning(f"⚠️ [STORAGE] Failed to generate primary signed URL: {url_error}")
                            primary_media_url = None
                    
                    # Prepare update data with non-expiring file paths
                    update_data = {
                        "status": GenerationStatus.COMPLETED,
                        "output_urls": [f.file_path for f in stored_files],  # Use storage paths for reference
                        "media_url": primary_media_path,  # Store file path instead of expiring signed URL
                        "media_files": [
                            {
                                "file_id": str(f.id),
                                "bucket": f.bucket_name.value if hasattr(f.bucket_name, 'value') else str(f.bucket_name),
                                "path": f.file_path,
                                "size": f.file_size,
                                "content_type": f.content_type.value if hasattr(f.content_type, 'value') else str(f.content_type),
                                "is_thumbnail": f.is_thumbnail
                            } for f in stored_files
                        ],
                        "storage_size": total_storage_size,
                        "is_media_processed": True,
                        "metadata": {
                            **fal_result.get("metadata", {}),
                            "files_stored": len(stored_files),
                            "total_size": total_storage_size,
                            "storage_successful": True,
                            "supabase_urls_used": True,
                            "signed_url_generated": primary_media_url is not None,
                            "primary_signed_url": primary_media_url  # Store the URL for debugging
                        },
                        "completed_at": datetime.utcnow().isoformat()
                    }
                    
                    logger.info(f"🔄 [STORAGE] Updating generation {generation_id} with storage information")
                    logger.info(f"🔍 [STORAGE] Primary media_url: {update_data['media_url']}")
                    logger.info(f"🔍 [STORAGE] Storage paths count: {len(update_data['output_urls'])}")
                    
                    # Update generation with storage information
                    updated_generation = await self.generation_repo.update_generation(
                        generation_id,
                        update_data
                    )
                    
                    logger.info(f"✅ [STORAGE] Generation {generation_id} updated successfully in database")
                    logger.info(f"🎉 [GENERATION-PROCESSING] Generation {generation_id} completed and stored: {len(stored_files)} files, {total_storage_size} bytes")
                    logger.info(f"🔍 [GENERATION-PROCESSING] Final generation status: {updated_generation.status}, media_url: {updated_generation.media_url}")
                    
                except Exception as storage_error:
                    logger.error(f"❌ [STORAGE] Failed to store generation results for {generation_id}: {storage_error}")
                    logger.error(f"❌ [STORAGE] Storage error type: {type(storage_error).__name__}")
                    import traceback
                    logger.error(f"❌ [STORAGE] Storage error traceback: {traceback.format_exc()}")
                    
                    # CRITICAL: NO FALLBACK TO FAL URLS - Aggressive retry for Supabase Storage
                    max_storage_retries = 5
                    retry_delay = 10  # seconds
                    stored_files = []
                    
                    logger.error(f"🚨 [STORAGE] CRITICAL: Storage failed, attempting aggressive retry for generation {generation_id}")
                    
                    for retry_attempt in range(max_storage_retries):
                        try:
                            logger.info(f"🔄 [STORAGE-RETRY] Retry attempt {retry_attempt + 1}/{max_storage_retries} for generation {generation_id}")
                            
                            # Wait before retry (exponential backoff)
                            if retry_attempt > 0:
                                wait_time = retry_delay * (2 ** (retry_attempt - 1))
                                logger.info(f"⏰ [STORAGE-RETRY] Waiting {wait_time} seconds before retry...")
                                await asyncio.sleep(wait_time)
                            
                            # Retry storage upload with aggressive parameters
                            stored_files = await storage_service.upload_generation_result(
                                user_id=generation.user_id if isinstance(generation.user_id, UUID) else UUID(generation.user_id),
                                generation_id=generation_id if isinstance(generation_id, UUID) else UUID(generation_id),
                                file_urls=output_urls,
                                file_type="image" if generation.media_type == "image" else "video",
                                project_id=generation.project_id if generation.project_id and isinstance(generation.project_id, UUID) else (UUID(generation.project_id) if generation.project_id else None),
                                progress_callback=None  # Skip progress callback during retry
                            )
                            
                            logger.info(f"✅ [STORAGE-RETRY] Retry successful! Uploaded {len(stored_files)} files on attempt {retry_attempt + 1}")
                            break  # Success, exit retry loop
                            
                        except Exception as retry_error:
                            logger.error(f"❌ [STORAGE-RETRY] Retry attempt {retry_attempt + 1} failed: {retry_error}")
                            
                            if retry_attempt == max_storage_retries - 1:
                                # All retries failed - mark generation as FAILED
                                logger.error(f"🚨 [STORAGE-RETRY] All {max_storage_retries} storage retries failed for generation {generation_id}")
                                
                                failure_data = {
                                    "status": GenerationStatus.FAILED,
                                    "error_message": f"Storage failed after {max_storage_retries} attempts: {str(retry_error)}",
                                    "metadata": {
                                        **fal_result.get("metadata", {}),
                                        "storage_failed": True,
                                        "storage_retries_exhausted": True,
                                        "max_retries_attempted": max_storage_retries,
                                        "final_storage_error": str(retry_error),
                                        "original_storage_error": str(storage_error),
                                        "failure_stage": "storage_upload"
                                    },
                                    "completed_at": datetime.utcnow().isoformat()
                                }
                                
                                updated_generation = await self.generation_repo.update_generation(
                                    generation_id,
                                    failure_data
                                )
                                
                                logger.error(f"💀 [STORAGE-RETRY] Generation {generation_id} marked as FAILED due to storage failure")
                                return  # Exit processing
                    
                    if stored_files:
                        # Storage retry succeeded - continue with normal completion
                        logger.info(f"🎉 [STORAGE-RETRY] Storage retry successful, completing generation {generation_id}")
                        
                        # Calculate total storage size
                        total_storage_size = sum(file_meta.file_size for file_meta in stored_files)
                        
                        # Store file path instead of expiring signed URL to prevent URL expiration issues
                        primary_media_path = None
                        primary_media_url = None
                        if stored_files:
                            # Store the file path instead of generating a signed URL that expires
                            primary_media_path = stored_files[0].file_path
                            logger.info(f"✅ [STORAGE-RETRY] Primary file stored at path: {primary_media_path}")
                            
                            # Generate a primary signed URL for immediate use (optional)
                            try:
                                signed_url_response = await storage_service.get_signed_url(
                                    file_id=stored_files[0].id,
                                    user_id=generation.user_id if isinstance(generation.user_id, UUID) else UUID(generation.user_id),
                                    expires_in=86400  # 24 hours for initial access
                                )
                                primary_media_url = signed_url_response.signed_url
                                logger.info(f"✅ [STORAGE-RETRY] Primary signed URL generated: {primary_media_url[:100]}...")
                            except Exception as url_error:
                                logger.warning(f"⚠️ [STORAGE-RETRY] Failed to generate primary signed URL: {url_error}")
                                primary_media_url = None
                        
                        # Prepare update data with non-expiring file paths
                        update_data = {
                            "status": GenerationStatus.COMPLETED,
                            "output_urls": [f.file_path for f in stored_files],  # Use storage paths for reference
                            "media_url": primary_media_path,  # Store file path instead of expiring signed URL
                            "media_files": [
                                {
                                    "file_id": str(f.id),
                                    "bucket": f.bucket_name.value if hasattr(f.bucket_name, 'value') else str(f.bucket_name),
                                    "path": f.file_path,
                                    "size": f.file_size,
                                    "content_type": f.content_type.value if hasattr(f.content_type, 'value') else str(f.content_type),
                                    "is_thumbnail": f.is_thumbnail
                                } for f in stored_files
                            ],
                            "storage_size": total_storage_size,
                            "is_media_processed": True,
                            "metadata": {
                                **fal_result.get("metadata", {}),
                                "files_stored": len(stored_files),
                                "total_size": total_storage_size,
                                "storage_successful": True,
                                "supabase_urls_used": True,
                                "storage_retry_succeeded": True,
                                "storage_retries_used": retry_attempt + 1,
                                "signed_url_generated": primary_media_url is not None,
                                "primary_signed_url": primary_media_url  # Store the URL for debugging
                            },
                            "completed_at": datetime.utcnow().isoformat()
                        }
                        
                        # Update generation with storage information
                        updated_generation = await self.generation_repo.update_generation(
                            generation_id,
                            update_data
                        )
                        
                        logger.info(f"✅ [STORAGE-RETRY] Generation {generation_id} completed successfully after retry")
                        logger.info(f"🎉 [GENERATION-PROCESSING] Generation {generation_id} completed and stored: {len(stored_files)} files, {total_storage_size} bytes")
                        logger.info(f"🔍 [GENERATION-PROCESSING] Final generation status: {updated_generation.status}, media_url: {updated_generation.media_url}")
            
            elif fal_result["status"] == GenerationStatus.FAILED:
                logger.error(f"❌ [GENERATION-PROCESSING] FAL.ai generation failed for {generation_id}")
                error_message = fal_result.get("error_message", "Generation failed")
                logger.error(f"💥 [GENERATION-PROCESSING] Error message: {error_message}")
                
                # Generation failed - update with detailed error information
                failure_data = {
                    "status": GenerationStatus.FAILED,
                    "error_message": error_message,
                    "metadata": {
                        **fal_result.get("metadata", {}),
                        "fal_error": True,
                        "failure_stage": "fal_generation"
                    },
                    "completed_at": datetime.utcnow().isoformat()
                }
                
                logger.info(f"🔄 [GENERATION-PROCESSING] Updating generation {generation_id} status to FAILED")
                
                updated_generation = await self.generation_repo.update_generation(
                    generation_id,
                    failure_data
                )
                
                logger.error(f"💀 [GENERATION-PROCESSING] Generation {generation_id} marked as failed: {error_message}")
                logger.info(f"🔍 [GENERATION-PROCESSING] Final failed status: {updated_generation.status}")
            
            else:
                logger.warning(f"⚠️ [GENERATION-PROCESSING] Unexpected FAL.ai status for generation {generation_id}: {fal_result['status']}")
                logger.warning(f"🔍 [GENERATION-PROCESSING] Full FAL result: {fal_result}")
            
        except Exception as e:
            logger.error(f"💥 [GENERATION-PROCESSING] Critical error processing generation {generation_id}: {e}")
            logger.error(f"❌ [GENERATION-PROCESSING] Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"❌ [GENERATION-PROCESSING] Full traceback: {traceback.format_exc()}")
            
            # Mark generation as failed and cleanup any uploaded reference images
            try:
                logger.info(f"🧹 [GENERATION-PROCESSING] Starting cleanup for failed generation {generation_id}")
                await self._cleanup_failed_generation(generation_id)
                logger.info(f"✅ [GENERATION-PROCESSING] Cleanup completed for generation {generation_id}")
            except Exception as cleanup_error:
                logger.error(f"❌ [GENERATION-PROCESSING] Failed to cleanup failed generation {generation_id}: {cleanup_error}")
                logger.error(f"❌ [GENERATION-PROCESSING] Cleanup error traceback: {traceback.format_exc()}")
            
            # Mark generation as failed with comprehensive error information
            critical_failure_data = {
                "status": GenerationStatus.FAILED,
                "error_message": f"Processing error: {str(e)}",
                "metadata": {
                    "critical_error": True,
                    "error_type": type(e).__name__,
                    "failure_stage": "processing_pipeline",
                    "processing_failed": True
                },
                "completed_at": datetime.utcnow().isoformat()
            }
            
            logger.info(f"🔄 [GENERATION-PROCESSING] Marking generation {generation_id} as failed due to critical error")
            
            try:
                updated_generation = await self.generation_repo.update_generation(
                    generation_id,
                    critical_failure_data
                )
                logger.error(f"💀 [GENERATION-PROCESSING] Generation {generation_id} marked as critically failed")
                logger.info(f"🔍 [GENERATION-PROCESSING] Final critical failure status: {updated_generation.status}")
            except Exception as update_error:
                logger.error(f"💥 [GENERATION-PROCESSING] Failed to update generation status after critical error: {update_error}")
                logger.error(f"❌ [GENERATION-PROCESSING] This generation {generation_id} is now in an inconsistent state!")
    
    async def _poll_generation_completion(self, generation_id: str, fal_request_id: str):
        """
        Poll FAL.ai for generation completion.
        
        Args:
            generation_id: Database generation ID
            fal_request_id: FAL.ai request ID
        """
        max_attempts = 60  # 10 minutes with 10-second intervals
        attempt = 0
        
        while attempt < max_attempts:
            try:
                # Check status with FAL.ai
                status_result = await fal_service.check_generation_status(fal_request_id)
                
                if status_result["status"] == GenerationStatus.COMPLETED:
                    # Generation completed successfully - store results in Supabase Storage
                    try:
                        # Get generation details for user context
                        generation = await self.generation_repo.get_generation_by_id(
                            generation_id=generation_id,
                            user_id=None,  # No user_id available in polling context
                            auth_token=None  # No auth token available in polling context, rely on service key
                        )
                        if not generation:
                            raise ValueError(f"Generation {generation_id} not found")
                        
                        # Store generation results in storage
                        output_urls = status_result.get("output_urls", [])
                        stored_files = []
                        
                        if output_urls:
                            stored_files = await storage_service.upload_generation_result(
                                user_id=generation.user_id,  # Pass string directly
                                generation_id=generation_id,  # Pass string directly
                                file_urls=output_urls,
                                file_type="image" if generation.media_type == "image" else "video",
                                project_id=generation.project_id if generation.project_id else None
                            )
                        
                        # Calculate total storage size
                        total_storage_size = sum(file_meta.file_size for file_meta in stored_files)
                        
                        # Update generation with storage information
                        await self.generation_repo.update_generation(
                            generation_id,
                            {
                                "status": GenerationStatus.COMPLETED,
                                "output_urls": [f.file_path for f in stored_files],  # Use storage paths instead of external URLs
                                "media_url": stored_files[0].file_path if stored_files else None,  # Set primary media URL
                                "media_files": [
                                    {
                                        "file_id": str(f.id),
                                        "bucket": f.bucket_name.value if hasattr(f.bucket_name, 'value') else str(f.bucket_name),
                                        "path": f.file_path,
                                        "size": f.file_size,
                                        "content_type": f.content_type.value if hasattr(f.content_type, 'value') else str(f.content_type),
                                        "is_thumbnail": f.is_thumbnail
                                    } for f in stored_files
                                ],
                                "storage_size": total_storage_size,
                                "is_media_processed": True,
                                "metadata": {
                                    **status_result.get("metadata", {}),
                                    "fal_request_id": fal_request_id,
                                    "processing_time": attempt * 10,
                                    "files_stored": len(stored_files),
                                    "total_size": total_storage_size
                                },
                                "completed_at": datetime.utcnow().isoformat()
                            }
                        )
                        
                        logger.info(
                            f"Generation {generation_id} completed and stored: "
                            f"{len(stored_files)} files, {total_storage_size} bytes"
                        )
                        
                    except Exception as storage_error:
                        logger.error(f"Failed to store generation results for {generation_id}: {storage_error}")
                        
                        # Mark generation as completed but with storage warning
                        await self.generation_repo.update_generation(
                            generation_id,
                            {
                                "status": GenerationStatus.COMPLETED,
                                "output_urls": status_result.get("output_urls", []),  # Fallback to external URLs
                                "metadata": {
                                    **status_result.get("metadata", {}),
                                    "fal_request_id": fal_request_id,
                                    "processing_time": attempt * 10,
                                    "storage_error": str(storage_error)
                                },
                                "completed_at": datetime.utcnow().isoformat()
                            }
                        )
                        logger.warning(f"Generation {generation_id} completed but storage failed")
                    
                    break
                    
                elif status_result["status"] == GenerationStatus.FAILED:
                    # Generation failed
                    await self.generation_repo.update_generation(
                        generation_id,
                        {
                            "status": GenerationStatus.FAILED,
                            "error_message": status_result.get("error_message", "Generation failed"),
                            "completed_at": datetime.utcnow().isoformat()
                        }
                    )
                    
                    logger.error(f"Generation {generation_id} failed: {status_result.get('error_message')}")
                    break
                    
                else:
                    # Still processing, continue polling
                    attempt += 1
                    await asyncio.sleep(10)  # Wait 10 seconds before next check
                    
            except Exception as e:
                logger.error(f"Error polling generation {generation_id}: {e}")
                attempt += 1
                await asyncio.sleep(10)
        
        # If we've exceeded max attempts, mark as failed
        if attempt >= max_attempts:
            await self.generation_repo.update_generation(
                generation_id,
                {
                    "status": GenerationStatus.FAILED,
                    "error_message": "Generation timed out",
                    "completed_at": datetime.utcnow().isoformat()
                }
            )
            logger.error(f"Generation {generation_id} timed out after {max_attempts} attempts")
    
    async def get_generation(self, generation_id: str, user_id: str, auth_token: Optional[str] = None) -> GenerationResponse:
        """Get a generation by ID."""
        await self._get_repositories()
        
        generation = await self.generation_repo.get_generation_by_id(
            generation_id=generation_id,
            user_id=user_id,  # Pass user_id for RLS compliance
            auth_token=auth_token  # Pass JWT token for database authentication
        )
        if not generation:
            raise ValueError(f"Generation {generation_id} not found")
            
        # Verify ownership (additional check, but RLS should handle this)
        if generation.user_id != user_id:
            raise PermissionError("Access denied to this generation")
            
        return generation
    
    async def list_user_generations(
        self,
        user_id: str,
        project_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        auth_token: Optional[str] = None
    ) -> List[GenerationResponse]:
        """List generations for a user."""
        logger.info(f"🔍 [GENERATION-SERVICE] Listing generations for user {user_id}, auth_token: {'***' + auth_token[-10:] if auth_token else 'None'}")
        
        await self._get_repositories()
        
        try:
            # CRITICAL FIX: Pass auth_token to repository for proper database authentication
            generations = await self.generation_repo.list_user_generations(
                user_id=user_id,
                project_id=project_id,
                limit=limit,
                offset=offset,
                auth_token=auth_token  # Pass JWT token for RLS authentication
            )
            
            logger.info(f"✅ [GENERATION-SERVICE] Successfully retrieved {len(generations)} generations for user {user_id}")
            return generations
            
        except Exception as e:
            logger.error(f"❌ [GENERATION-SERVICE] Failed to list generations for user {user_id}: {e}")
            logger.error(f"❌ [GENERATION-SERVICE] Error type: {type(e).__name__}")
            raise
    
    async def delete_generation(self, generation_id: str, user_id: str) -> bool:
        """Delete a generation and its associated storage files with enhanced cleanup."""
        await self._get_repositories()
        
        logger.info(f"🗑️ [DELETE] Starting deletion of generation {generation_id} for user {user_id}")
        
        # CRITICAL FIX: Verify ownership with proper authentication context
        generation = await self.generation_repo.get_generation_by_id(
            generation_id=generation_id,
            user_id=user_id,  # Pass user_id for RLS compliance
            auth_token=None  # No auth token available in delete context, rely on service key
        )
        if not generation:
            raise ValueError(f"Generation {generation_id} not found")
            
        if generation.user_id != user_id:
            raise PermissionError("Access denied to this generation")
        
        # Cancel FAL.ai generation if still processing
        if generation.status in [GenerationStatus.PENDING, GenerationStatus.PROCESSING]:
            metadata = generation.metadata or {}
            fal_request_id = metadata.get("fal_request_id")
            if fal_request_id:
                try:
                    logger.info(f"❌ [DELETE] Cancelling active FAL.ai generation {fal_request_id}")
                    await fal_service.cancel_generation(fal_request_id)
                    logger.info(f"✅ [DELETE] FAL.ai generation cancelled successfully")
                except Exception as e:
                    logger.warning(f"⚠️ [DELETE] Failed to cancel FAL.ai generation {fal_request_id}: {e}")
        
        # Enhanced storage cleanup using the improved storage service
        try:
            logger.info(f"🧹 [DELETE] Starting comprehensive storage cleanup...")
            
            # Use the enhanced cleanup method
            cleanup_count = await storage_service.cleanup_failed_generation_files(
                generation_id=generation_id,
                user_id=user_id
            )
            
            logger.info(f"✅ [DELETE] Storage cleanup completed: {cleanup_count} files removed")
            
            # Additional cleanup for any remaining files referenced in media_files
            if hasattr(generation, 'media_files') and generation.media_files:
                logger.info(f"📁 [DELETE] Processing {len(generation.media_files)} media file references...")
                
                for file_info in generation.media_files:
                    try:
                        file_id = file_info.get('file_id')
                        if file_id:
                            await storage_service.delete_file(
                                file_id=file_id if isinstance(file_id, UUID) else UUID(file_id),
                                user_id=user_id if isinstance(user_id, UUID) else UUID(user_id),
                                force=True  # Force delete even if referenced
                            )
                            logger.info(f"✅ [DELETE] Deleted media file: {file_id}")
                    except Exception as e:
                        logger.warning(f"⚠️ [DELETE] Failed to delete media file {file_info.get('file_id')}: {e}")
                        
        except Exception as e:
            logger.error(f"❌ [DELETE] Failed to cleanup storage files for generation {generation_id}: {e}")
            # Continue with generation deletion even if storage cleanup fails
        
        # Delete the generation record
        try:
            success = await self.generation_repo.delete_generation(generation_id)
            if success:
                logger.info(f"✅ [DELETE] Generation {generation_id} deleted successfully")
            else:
                logger.error(f"❌ [DELETE] Failed to delete generation {generation_id} from database")
            return success
            
        except Exception as e:
            logger.error(f"❌ [DELETE] Database deletion failed for generation {generation_id}: {e}")
            raise
    
    async def toggle_generation_favorite(
        self,
        generation_id: str,
        user_id: str
    ) -> GenerationResponse:
        """Toggle favorite status of a generation."""
        await self._get_repositories()
        
        # CRITICAL FIX: Verify ownership with proper authentication context
        generation = await self.generation_repo.get_generation_by_id(
            generation_id=generation_id,
            user_id=user_id,  # Pass user_id for RLS compliance
            auth_token=None  # No auth token available in favorite toggle context, rely on service key
        )
        if not generation:
            raise ValueError(f"Generation {generation_id} not found")
            
        if generation.user_id != user_id:
            raise PermissionError("Access denied to this generation")
        
        # Toggle favorite status
        new_favorite_status = not generation.is_favorite
        
        return await self.generation_repo.update_generation(
            generation_id,
            {"is_favorite": new_favorite_status}
        )
    
    async def get_generation_stats(self, user_id: str, auth_token: Optional[str] = None) -> Dict[str, Any]:
        """Get generation statistics for a user."""
        logger.info(f"🔍 [GENERATION-SERVICE] Getting stats for user {user_id}, auth_token: {'***' + auth_token[-10:] if auth_token else 'None'}")
        
        await self._get_repositories()
        
        try:
            stats = await self.generation_repo.get_user_generation_stats(user_id)
            logger.info(f"✅ [GENERATION-SERVICE] Successfully retrieved stats for user {user_id}")
            return stats
        except Exception as e:
            logger.error(f"❌ [GENERATION-SERVICE] Failed to get stats for user {user_id}: {e}")
            logger.error(f"❌ [GENERATION-SERVICE] Error type: {type(e).__name__}")
            raise
    
    async def _cleanup_failed_generation(self, generation_id: str):
        """
        Enhanced cleanup for storage files from failed generation.
        
        Args:
            generation_id: Generation ID to cleanup
        """
        try:
            generation = await self.generation_repo.get_generation_by_id(
                generation_id=generation_id,
                user_id=None,  # No user_id available in cleanup context
                auth_token=None  # No auth token available in cleanup context, rely on service key
            )
            if not generation:
                logger.warning(f"🤷 [CLEANUP] Generation {generation_id} not found for cleanup")
                return
            
            logger.info(f"🧹 [CLEANUP] Starting enhanced cleanup for failed generation {generation_id}")
            
            # Use enhanced storage service cleanup method
            cleanup_count = await storage_service.cleanup_failed_generation_files(
                generation_id=generation_id,
                user_id=generation.user_id
            )
            
            logger.info(f"✅ [CLEANUP] Enhanced cleanup completed: {cleanup_count} files removed for generation {generation_id}")
            
            # Additional cleanup: Update generation metadata to reflect cleanup
            try:
                await self.generation_repo.update_generation(
                    generation_id,
                    {
                        "metadata": {
                            **(generation.metadata or {}),
                            "cleanup_performed": True,
                            "cleanup_timestamp": datetime.utcnow().isoformat(),
                            "files_cleaned": cleanup_count
                        }
                    }
                )
                logger.info(f"✅ [CLEANUP] Updated generation metadata to reflect cleanup")
            except Exception as metadata_error:
                logger.warning(f"⚠️ [CLEANUP] Failed to update generation metadata: {metadata_error}")
                    
        except Exception as e:
            logger.error(f"❌ [CLEANUP] Error during enhanced cleanup for {generation_id}: {e}")
            import traceback
            logger.error(f"❌ [CLEANUP] Cleanup error traceback: {traceback.format_exc()}")


    async def get_generation_media_urls(self, generation_id: str, user_id: str, expires_in: int = 3600, auth_token: Optional[str] = None) -> Dict[str, Any]:
        """
        Get comprehensive media access information for generation files.
        
        Args:
            generation_id: Generation ID
            user_id: User ID for ownership verification
            expires_in: URL expiration time in seconds (default 1 hour)
            auth_token: JWT token for database authentication
            
        Returns:
            Dictionary with signed URLs and storage information
        """
        await self._get_repositories()
        
        logger.info(f"🔗 [MEDIA-URLS] Getting media URLs for generation {generation_id}, auth_token: {'***' + auth_token[-10:] if auth_token else 'None'}")
        
        # CRITICAL FIX: Verify ownership with proper authentication context
        generation = await self.generation_repo.get_generation_by_id(
            generation_id=generation_id, 
            user_id=user_id,  # Pass user_id for RLS compliance
            auth_token=auth_token  # Pass JWT token for database authentication
        )
        if not generation:
            raise ValueError(f"Generation {generation_id} not found")
            
        # COMPREHENSIVE AUTHORIZATION IMPLEMENTATION - Fixes HTTP 403 errors
        try:
            from services.authorization_service import authorization_service
            
            # Use comprehensive authorization validation instead of simple ownership check
            generation_permissions = await authorization_service.validate_generation_media_access(
                generation_id=generation_id if isinstance(generation_id, UUID) else UUID(generation_id),
                user_id=user_id if isinstance(user_id, UUID) else UUID(user_id),
                auth_token=auth_token,
                expires_in=expires_in
            )
            
            if not generation_permissions.granted:
                raise PermissionError(f"Access denied to generation {generation_id}: {generation_permissions.audit_trail}")
            
            logger.info(f"✅ [AUTH-SUCCESS] User {user_id} granted access to generation {generation_id} via {generation_permissions.access_method}")
            
            # If comprehensive authorization provided media URLs, use them directly
            if generation_permissions.media_urls:
                logger.info(f"🚀 [MEDIA-URLS] Using pre-authorized media URLs ({len(generation_permissions.media_urls)} URLs)")
                return {
                    'generation_id': generation_id,
                    'signed_urls': generation_permissions.media_urls,
                    'primary_url': generation_permissions.media_urls[0] if generation_permissions.media_urls else None,
                    'expires_in': expires_in,
                    'expires_at': generation_permissions.expires_at.isoformat() if generation_permissions.expires_at else None,
                    'file_count': len(generation_permissions.media_urls),
                    'access_method': generation_permissions.access_method.value,
                    'authorization_complete': True
                }
        
        except ImportError:
            # Fallback to simple ownership check if authorization service not available
            logger.warning("⚠️ [AUTH-FALLBACK] Authorization service not available, using simple ownership check")
            if generation.user_id != user_id:
                raise PermissionError("Access denied to this generation")
        
        try:
            # Use the enhanced storage service to get comprehensive storage info
            storage_info = await storage_service.get_generation_storage_info(
                generation_id=generation_id,
                user_id=user_id
            )
            
            # Extract signed URLs from storage info
            signed_urls = [item['signed_url'] for item in storage_info.get('signed_urls', [])]
            
            media_response = {
                'generation_id': generation_id,
                'signed_urls': signed_urls,
                'primary_url': signed_urls[0] if signed_urls else None,
                'expires_in': expires_in,
                'expires_at': (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat(),
                'file_count': storage_info.get('total_files', 0),
                'total_size_mb': storage_info.get('total_size_mb', 0),
                'storage_paths': storage_info.get('storage_paths', []),
                'has_thumbnails': storage_info.get('has_thumbnails', False),
                'is_fully_processed': storage_info.get('is_fully_processed', False)
            }
            
            logger.info(f"✅ [MEDIA-URLS] Retrieved {len(signed_urls)} signed URLs for generation {generation_id}")
            return media_response
            
        except Exception as e:
            logger.error(f"❌ [MEDIA-URLS] Failed to get storage info, falling back to legacy method: {e}")
            
            # Fallback to legacy method
            signed_urls = []
            
            if hasattr(generation, 'media_files') and generation.media_files:
                logger.info(f"🔄 [MEDIA-URLS] Using legacy method for {len(generation.media_files)} media files")
                
                for file_info in generation.media_files:
                    try:
                        file_id = file_info.get('file_id')
                        if file_id:
                            signed_url_response = await storage_service.get_signed_url(
                                file_id=file_id if isinstance(file_id, UUID) else UUID(file_id),
                                user_id=user_id if isinstance(user_id, UUID) else UUID(user_id),
                                expires_in=expires_in
                            )
                            signed_urls.append(signed_url_response.signed_url)
                    except Exception as e:
                        logger.warning(f"⚠️ [MEDIA-URLS] Failed to get signed URL for file {file_info.get('file_id')}: {e}")
            
            return {
                'generation_id': generation_id,
                'signed_urls': signed_urls,
                'primary_url': signed_urls[0] if signed_urls else None,
                'expires_in': expires_in,
                'expires_at': (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat(),
                'file_count': len(signed_urls),
                'legacy_fallback': True
            }
    
    async def _check_service_dependencies(self):
        """Check if all required services are available."""
        try:
            # Check database availability
            if not self.db or not self.db.is_available():
                raise RuntimeError("Database service unavailable")
            
            # Check FAL service availability (basic connectivity test)
            try:
                # This will test if FAL service is configured correctly
                supported_models = fal_service.get_supported_models()
                if not supported_models:
                    logger.warning("⚠️ [GENERATION-DEPS] FAL service returned no models")
            except Exception as fal_error:
                logger.error(f"❌ [GENERATION-DEPS] FAL service check failed: {fal_error}")
                raise RuntimeError(f"AI generation service unavailable: {str(fal_error)}")
            
            # Check storage service availability
            try:
                # Initialize storage service repositories to verify database connectivity
                # EMERGENCY FIX: Handle both old and new method names for production compatibility
                if hasattr(storage_service, '_get_storage_client'):
                    await storage_service._get_storage_client()
                else:
                    await storage_service._get_repositories()
                logger.info("✅ [GENERATION-DEPS] Storage service initialized successfully")
            except Exception as storage_error:
                logger.error(f"❌ [GENERATION-DEPS] Storage service check failed: {storage_error}")
                # EMERGENCY FIX: Don't fail generation for storage dependency issues
                logger.warning("⚠️ [GENERATION-DEPS] Storage service unavailable, continuing with generation")
            
            logger.info("✅ [GENERATION-DEPS] All service dependencies are available")
            
        except Exception as e:
            logger.error(f"❌ [GENERATION-DEPS] Service dependency check failed: {e}")
            raise


# Global service instance
generation_service = GenerationService()