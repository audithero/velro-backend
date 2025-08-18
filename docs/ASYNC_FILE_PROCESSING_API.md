# Async File Processing API Documentation

## Overview

The Async File Processing system provides robust, scalable file processing capabilities for handling FAL.ai file transfers to Supabase storage. It features streaming downloads, batch processing, background tasks, and comprehensive error handling.

## Features

- **Async File Downloads**: Streaming downloads with progress tracking
- **File Type Detection**: Magic byte detection and validation
- **Batch Processing**: Parallel processing of multiple files
- **Background Tasks**: Celery and asyncio task queue integration
- **Storage Optimization**: Image compression and deduplication
- **Comprehensive Logging**: Detailed operation tracking
- **Error Recovery**: Robust error handling and retry mechanisms

## Core Components

### 1. AsyncFileProcessor

Main service for file processing operations.

```python
from services.async_file_processor import async_file_processor
```

### 2. BackgroundTaskManager

Service for managing background task execution.

```python
from services.background_tasks import task_manager
```

## API Reference

### AsyncFileProcessor Methods

#### download_fal_file()

Download file from FAL.ai URL with streaming and progress tracking.

```python
async def download_fal_file(
    url: str,
    max_size: int = None,
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> bytes
```

**Parameters:**
- `url`: FAL.ai file URL
- `max_size`: Maximum file size in bytes (default: 50MB)
- `progress_callback`: Optional callback for progress updates (downloaded, total)

**Returns:** File data as bytes

**Raises:**
- `FileSizeExceededError`: If file exceeds size limit
- `FileProcessingError`: For download errors

**Example:**
```python
# Basic download
file_data = await async_file_processor.download_fal_file(
    "https://fal.ai/files/example.jpg"
)

# With progress tracking
def progress_callback(downloaded, total):
    progress = (downloaded / total) * 100
    print(f"Download progress: {progress:.1f}%")

file_data = await async_file_processor.download_fal_file(
    url="https://fal.ai/files/example.jpg",
    max_size=10 * 1024 * 1024,  # 10MB limit
    progress_callback=progress_callback
)
```

#### detect_file_type()

Detect and validate file type from content.

```python
def detect_file_type(
    file_data: bytes, 
    url: Optional[str] = None
) -> Tuple[str, str, bool]
```

**Parameters:**
- `file_data`: File content bytes
- `url`: Optional URL for additional context

**Returns:** Tuple of (content_type, extension, is_valid)

**Example:**
```python
content_type, extension, is_valid = async_file_processor.detect_file_type(
    file_data=image_bytes,
    url="https://example.com/image.jpg"
)

if is_valid:
    print(f"Valid {content_type} file with extension .{extension}")
else:
    print(f"Unsupported file type: {content_type}")
```

#### validate_file_integrity()

Validate file integrity and ensure it's not corrupted.

```python
def validate_file_integrity(
    file_data: bytes, 
    content_type: str
) -> bool
```

**Example:**
```python
is_valid = async_file_processor.validate_file_integrity(
    file_data=image_bytes,
    content_type="image/jpeg"
)

if not is_valid:
    raise FileProcessingError("File is corrupted or invalid")
```

#### process_file_batch()

Process multiple files in parallel with coordination.

```python
async def process_file_batch(
    urls: List[str],
    user_id: Union[UUID, str],
    generation_id: Union[UUID, str],
    max_concurrent: int = 3,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> ProcessingResult
```

**Parameters:**
- `urls`: List of file URLs to process
- `user_id`: User owning the files
- `generation_id`: Generation ID to associate files with
- `max_concurrent`: Maximum concurrent downloads (default: 3)
- `progress_callback`: Progress callback (completed, total, current_url)

**Returns:** `ProcessingResult` with success/failure details

**Example:**
```python
def batch_progress(completed, total, current_url):
    print(f"Processing {completed}/{total}: {current_url[:50]}...")

result = await async_file_processor.process_file_batch(
    urls=[
        "https://fal.ai/files/image1.jpg",
        "https://fal.ai/files/image2.jpg",
        "https://fal.ai/files/video1.mp4"
    ],
    user_id=user_id,
    generation_id=generation_id,
    max_concurrent=5,
    progress_callback=batch_progress
)

print(f"Batch processing completed:")
print(f"  Success: {result.success}")
print(f"  Total files: {result.total_files}")
print(f"  Successful: {len(result.processed_files)}")
print(f"  Failed: {len(result.failed_files)}")
print(f"  Processing time: {result.processing_time:.2f}s")

if result.failed_files:
    print("Failed files:")
    for failed in result.failed_files:
        print(f"  - {failed['url']}: {failed['error']}")
```

#### compress_image()

Compress image while maintaining quality.

```python
async def compress_image(
    file_data: bytes, 
    quality: int = 85
) -> bytes
```

**Example:**
```python
original_size = len(image_data)
compressed_data = await async_file_processor.compress_image(
    file_data=image_data,
    quality=75
)
compressed_size = len(compressed_data)

print(f"Compression: {original_size} -> {compressed_size} bytes")
print(f"Space saved: {((original_size - compressed_size) / original_size) * 100:.1f}%")
```

### BackgroundTaskManager Methods

#### queue_file_processing()

Queue file processing as background task.

```python
async def queue_file_processing(
    urls: List[str],
    user_id: Union[UUID, str],
    generation_id: Union[UUID, str],
    task_options: Optional[Dict[str, Any]] = None
) -> str
```

**Returns:** Task ID for tracking

**Example:**
```python
task_id = await task_manager.queue_file_processing(
    urls=["https://fal.ai/files/batch1.jpg", "https://fal.ai/files/batch2.jpg"],
    user_id=user_id,
    generation_id=generation_id,
    task_options={'max_concurrent': 5}
)

print(f"Background task queued: {task_id}")
```

#### get_task_status()

Get task status and result.

```python
async def get_task_status(task_id: str) -> Dict[str, Any]
```

**Example:**
```python
status = await task_manager.get_task_status(task_id)

print(f"Task {task_id}:")
print(f"  Status: {status['status']}")
print(f"  Ready: {status['ready']}")

if status['ready']:
    if status.get('successful'):
        result = status['result']
        print(f"  Files processed: {result['successful_files']}")
        print(f"  Processing time: {result['processing_time']:.2f}s")
    else:
        print(f"  Error: {status.get('error', 'Unknown error')}")
```

#### cancel_task()

Cancel a running task.

```python
async def cancel_task(task_id: str) -> bool
```

**Example:**
```python
cancelled = await task_manager.cancel_task(task_id)
if cancelled:
    print(f"Task {task_id} cancelled successfully")
else:
    print(f"Failed to cancel task {task_id}")
```

## Usage Examples

### Single File Processing

```python
import asyncio
from uuid import uuid4
from services.async_file_processor import async_file_processor

async def process_single_file():
    try:
        # Download file
        file_data = await async_file_processor.download_fal_file(
            "https://fal.ai/files/generated_image.jpg"
        )
        
        # Detect and validate file type
        content_type, extension, is_valid = async_file_processor.detect_file_type(file_data)
        
        if not is_valid:
            raise ValueError(f"Unsupported file type: {content_type}")
        
        # Validate integrity
        if not async_file_processor.validate_file_integrity(file_data, content_type):
            raise ValueError("File integrity check failed")
        
        # Process through storage service
        from services.storage_service import storage_service
        
        upload_request = FileUploadRequest(
            bucket_name=StorageBucket.GENERATIONS,
            filename=f"processed.{extension}",
            content_type=ContentType(content_type),
            file_size=len(file_data)
        )
        
        result = await storage_service.upload_file(
            user_id=uuid4(),
            file_data=file_data,
            upload_request=upload_request
        )
        
        print(f"File processed successfully: {result.id}")
        
    except Exception as e:
        print(f"Processing failed: {e}")

asyncio.run(process_single_file())
```

### Batch Processing with Progress Tracking

```python
import asyncio
from uuid import uuid4
from services.async_file_processor import async_file_processor

async def batch_process_with_progress():
    urls = [
        "https://fal.ai/files/image1.jpg",
        "https://fal.ai/files/image2.jpg", 
        "https://fal.ai/files/video1.mp4",
        "https://fal.ai/files/image3.png"
    ]
    
    user_id = uuid4()
    generation_id = uuid4()
    
    def progress_callback(completed, total, current_url):
        progress = (completed / total) * 100
        filename = current_url.split('/')[-1]
        print(f"[{progress:5.1f}%] Processing: {filename}")
    
    try:
        result = await async_file_processor.process_file_batch(
            urls=urls,
            user_id=user_id,
            generation_id=generation_id,
            max_concurrent=3,
            progress_callback=progress_callback
        )
        
        print(f"\n=== Batch Processing Results ===")
        print(f"Overall success: {result.success}")
        print(f"Total files: {result.total_files}")
        print(f"Successful: {len(result.processed_files)}")
        print(f"Failed: {len(result.failed_files)}")
        print(f"Processing time: {result.processing_time:.2f} seconds")
        print(f"Average time per file: {result.processing_time / result.total_files:.2f}s")
        
        if result.failed_files:
            print(f"\n=== Failed Files ===")
            for failed in result.failed_files:
                print(f"- {failed['url']}: {failed['error']}")
        
        if result.processed_files:
            print(f"\n=== Processed Files ===")
            for file_meta in result.processed_files:
                print(f"- {file_meta.original_filename}: {file_meta.file_size} bytes")
                
    except Exception as e:
        print(f"Batch processing failed: {e}")

asyncio.run(batch_process_with_progress())
```

### Background Task Processing

```python
import asyncio
from uuid import uuid4
from services.background_tasks import task_manager

async def background_processing_example():
    urls = [
        "https://fal.ai/files/large_batch1.jpg",
        "https://fal.ai/files/large_batch2.mp4",
        "https://fal.ai/files/large_batch3.jpg"
    ]
    
    user_id = uuid4()
    generation_id = uuid4()
    
    # Queue background task
    task_id = await task_manager.queue_file_processing(
        urls=urls,
        user_id=user_id,
        generation_id=generation_id,
        task_options={
            'max_concurrent': 2,
            'quality': 85  # For image compression
        }
    )
    
    print(f"Background task queued: {task_id}")
    
    # Monitor task progress
    while True:
        status = await task_manager.get_task_status(task_id)
        
        print(f"Task status: {status['status']}")
        
        if status['ready']:
            if status.get('successful'):
                result = status['result']
                print(f"Task completed successfully!")
                print(f"  Files processed: {result['successful_files']}/{result['total_files']}")
                print(f"  Processing time: {result['processing_time']:.2f}s")
                
                # Access processed file IDs
                for file_id in result['processed_file_ids']:
                    print(f"  - File ID: {file_id}")
            else:
                print(f"Task failed: {status.get('error')}")
            break
        
        # Wait before checking again
        await asyncio.sleep(2)

asyncio.run(background_processing_example())
```

### Image Compression Workflow

```python
import asyncio
from services.async_file_processor import async_file_processor

async def compression_workflow():
    # Download image
    image_url = "https://fal.ai/files/high_res_image.jpg"
    
    print("Downloading image...")
    original_data = await async_file_processor.download_fal_file(image_url)
    original_size = len(original_data)
    
    print(f"Original size: {original_size / (1024*1024):.2f} MB")
    
    # Compress at different quality levels
    quality_levels = [95, 85, 75, 65]
    
    for quality in quality_levels:
        compressed_data = await async_file_processor.compress_image(
            file_data=original_data,
            quality=quality
        )
        
        compressed_size = len(compressed_data)
        savings = ((original_size - compressed_size) / original_size) * 100
        
        print(f"Quality {quality:2d}: {compressed_size / (1024*1024):5.2f} MB "
              f"({savings:5.1f}% savings)")

asyncio.run(compression_workflow())
```

### Error Handling and Recovery

```python
import asyncio
from services.async_file_processor import (
    async_file_processor,
    FileProcessingError,
    FileSizeExceededError,
    FileTypeNotSupportedError
)

async def robust_file_processing():
    urls = [
        "https://fal.ai/files/valid_image.jpg",
        "https://fal.ai/files/too_large.jpg",  # Will exceed size limit
        "https://fal.ai/files/unsupported.exe",  # Unsupported type
        "https://fal.ai/files/non_existent.jpg"  # 404 error
    ]
    
    user_id = uuid4()
    generation_id = uuid4()
    
    successful_files = []
    
    for url in urls:
        try:
            print(f"\nProcessing: {url}")
            
            # Download with size limit
            file_data = await async_file_processor.download_fal_file(
                url=url,
                max_size=10 * 1024 * 1024  # 10MB limit
            )
            
            # Validate file type
            content_type, extension, is_valid = async_file_processor.detect_file_type(
                file_data, url
            )
            
            if not is_valid:
                raise FileTypeNotSupportedError(f"Unsupported type: {content_type}")
            
            # Validate integrity
            if not async_file_processor.validate_file_integrity(file_data, content_type):
                raise FileProcessingError("File integrity validation failed")
            
            # If we get here, file is valid
            successful_files.append({
                'url': url,
                'size': len(file_data),
                'type': content_type,
                'extension': extension
            })
            
            print(f"  ✅ Success: {len(file_data)} bytes, {content_type}")
            
        except FileSizeExceededError as e:
            print(f"  ❌ Size error: {e}")
            
        except FileTypeNotSupportedError as e:
            print(f"  ❌ Type error: {e}")
            
        except FileProcessingError as e:
            print(f"  ❌ Processing error: {e}")
            
        except Exception as e:
            print(f"  ❌ Unexpected error: {e}")
    
    print(f"\n=== Summary ===")
    print(f"Successfully processed: {len(successful_files)}/{len(urls)} files")
    
    for file_info in successful_files:
        print(f"  - {file_info['url']}: {file_info['size']} bytes ({file_info['type']})")

asyncio.run(robust_file_processing())
```

## Configuration

### Environment Variables

```bash
# Redis configuration (for Celery)
REDIS_URL=redis://localhost:6379/0

# File processing limits
MAX_FILE_SIZE_MB=50
MAX_BATCH_SIZE=10
CHUNK_SIZE_KB=8

# Task timeouts
TASK_TIMEOUT_MINUTES=30
TASK_SOFT_TIMEOUT_MINUTES=25
```

### Celery Configuration

```python
# In settings or configuration file
CELERY_BROKER_URL = "redis://localhost:6379/0"
CELERY_RESULT_BACKEND = "redis://localhost:6379/0"
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_ENABLE_UTC = True
```

### Starting Celery Worker

```bash
# Start Celery worker
celery -A services.background_tasks.celery_app worker --loglevel=info --queues=file_processing,maintenance,optimization

# Start Celery beat (for periodic tasks)
celery -A services.background_tasks.celery_app beat --loglevel=info

# Monitor tasks
celery -A services.background_tasks.celery_app flower
```

## Performance Considerations

### Optimization Tips

1. **Concurrent Downloads**: Adjust `max_concurrent` based on server capacity
2. **Chunk Size**: Larger chunks for faster networks, smaller for reliability
3. **Memory Usage**: Process files in batches to avoid memory exhaustion
4. **Compression**: Use quality 75-85 for optimal size/quality balance
5. **Task Distribution**: Use multiple Celery workers for high throughput

### Monitoring

```python
# Get worker statistics
stats = task_manager.get_worker_stats()
print(f"Active workers: {len(stats.get('workers', {}))}")
print(f"Active tasks: {sum(len(tasks) for tasks in stats.get('active_tasks', {}).values())}")
```

## Error Handling

### Custom Exceptions

- `FileProcessingError`: Base exception for processing errors
- `FileSizeExceededError`: File exceeds size limits
- `FileTypeNotSupportedError`: Unsupported file format

### Retry Mechanisms

The system includes automatic retry for:
- Network timeouts
- Temporary server errors
- Rate limiting responses

### Logging

All operations are comprehensively logged with structured information:

```python
import logging
logger = logging.getLogger('async_file_processor')
logger.setLevel(logging.INFO)
```

Log levels:
- `INFO`: Normal operations and progress
- `WARNING`: Recoverable errors and fallbacks
- `ERROR`: Processing failures and exceptions
- `DEBUG`: Detailed operation traces

## Integration

### With Storage Service

```python
from services.storage_service import storage_service
from services.async_file_processor import async_file_processor

# Process and store files
result = await storage_service.upload_generation_result(
    user_id=user_id,
    generation_id=generation_id,
    file_urls=fal_output_urls
)
```

### With Generation Service

```python
from services.generation_service import generation_service

# Update generation with processed files
await generation_service.update_generation_media(
    generation_id=generation_id,
    processed_files=result.processed_files
)
```

This completes the comprehensive Async File Processing API documentation with practical examples and integration guidance.