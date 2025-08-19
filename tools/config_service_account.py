"""
Service Account Configuration Module
=====================================
Handles configuration for the service account JWT system.
Supports multiple secure storage backends for production use.
"""

import os
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import jwt

logger = logging.getLogger(__name__)

class ServiceAccountConfig:
    """
    Configuration manager for service account JWT.
    Supports multiple secure storage backends.
    """
    
    def __init__(self):
        """Initialize service account configuration."""
        self._service_jwt: Optional[str] = None
        self._jwt_metadata: Optional[Dict[str, Any]] = None
        self._last_check: Optional[datetime] = None
        self._check_interval = timedelta(hours=1)
        
    @property
    def service_jwt(self) -> str:
        """
        Get service account JWT from secure storage.
        
        Returns:
            Service account JWT token
        """
        if self._service_jwt:
            return self._service_jwt
        
        # Try different storage backends in order of preference
        
        # 1. AWS Secrets Manager
        if os.getenv("AWS_SECRETS_MANAGER_ENABLED", "false").lower() == "true":
            self._service_jwt = self._get_from_aws_secrets()
            if self._service_jwt:
                logger.info("Service JWT loaded from AWS Secrets Manager")
                return self._service_jwt
        
        # 2. HashiCorp Vault
        if os.getenv("VAULT_ENABLED", "false").lower() == "true":
            self._service_jwt = self._get_from_vault()
            if self._service_jwt:
                logger.info("Service JWT loaded from HashiCorp Vault")
                return self._service_jwt
        
        # 3. Azure Key Vault
        if os.getenv("AZURE_KEY_VAULT_ENABLED", "false").lower() == "true":
            self._service_jwt = self._get_from_azure_vault()
            if self._service_jwt:
                logger.info("Service JWT loaded from Azure Key Vault")
                return self._service_jwt
        
        # 4. Environment Variable (Development/Testing)
        self._service_jwt = os.getenv("SUPABASE_SERVICE_JWT")
        if self._service_jwt:
            logger.info("Service JWT loaded from environment variable")
            return self._service_jwt
        
        # 5. Local file (Development only - NOT for production)
        if os.path.exists("service_jwt_backup.json"):
            try:
                with open("service_jwt_backup.json", "r") as f:
                    data = json.load(f)
                    self._service_jwt = data.get("token")
                    if self._service_jwt:
                        logger.warning("Service JWT loaded from local file (NOT SECURE FOR PRODUCTION)")
                        return self._service_jwt
            except Exception as e:
                logger.error(f"Failed to load JWT from file: {e}")
        
        raise ValueError("No service JWT configured. Please set SUPABASE_SERVICE_JWT or enable a secure storage backend.")
    
    def _get_from_aws_secrets(self) -> Optional[str]:
        """Get JWT from AWS Secrets Manager."""
        try:
            import boto3
            client = boto3.client('secretsmanager')
            secret_name = os.getenv("AWS_SECRETS_MANAGER_SECRET_NAME", "velro/backend/service-jwt")
            
            response = client.get_secret_value(SecretId=secret_name)
            secret = json.loads(response['SecretString'])
            return secret.get('service_jwt')
        except Exception as e:
            logger.error(f"Failed to get JWT from AWS Secrets Manager: {e}")
            return None
    
    def _get_from_vault(self) -> Optional[str]:
        """Get JWT from HashiCorp Vault."""
        try:
            import hvac
            client = hvac.Client(
                url=os.getenv("VAULT_ADDR"),
                token=os.getenv("VAULT_TOKEN")
            )
            
            secret_path = os.getenv("VAULT_SECRET_PATH", "secret/data/velro/service-jwt")
            response = client.secrets.kv.v2.read_secret_version(
                path=secret_path.replace("secret/data/", "")
            )
            return response['data']['data'].get('service_jwt')
        except Exception as e:
            logger.error(f"Failed to get JWT from Vault: {e}")
            return None
    
    def _get_from_azure_vault(self) -> Optional[str]:
        """Get JWT from Azure Key Vault."""
        try:
            from azure.keyvault.secrets import SecretClient
            from azure.identity import DefaultAzureCredential
            
            vault_name = os.getenv("AZURE_KEY_VAULT_NAME")
            vault_url = f"https://{vault_name}.vault.azure.net"
            secret_name = os.getenv("AZURE_KEY_VAULT_SECRET_NAME", "service-jwt")
            
            credential = DefaultAzureCredential()
            client = SecretClient(vault_url=vault_url, credential=credential)
            
            secret = client.get_secret(secret_name)
            return secret.value
        except Exception as e:
            logger.error(f"Failed to get JWT from Azure Key Vault: {e}")
            return None
    
    @property
    def service_account_id(self) -> str:
        """Get service account user ID."""
        return os.getenv("SERVICE_ACCOUNT_ID", "a0000000-0000-0000-0000-000000000001")
    
    @property
    def service_account_email(self) -> str:
        """Get service account email."""
        return os.getenv("SERVICE_ACCOUNT_EMAIL", "backend-service@system.internal")
    
    def get_jwt_metadata(self) -> Dict[str, Any]:
        """
        Get metadata about the service JWT.
        
        Returns:
            Dictionary with JWT metadata
        """
        if not self._jwt_metadata or self._should_refresh_metadata():
            try:
                # Decode JWT without verification to get metadata
                payload = jwt.decode(self.service_jwt, options={"verify_signature": False})
                
                exp_timestamp = payload.get("exp", 0)
                exp_datetime = datetime.fromtimestamp(exp_timestamp, timezone.utc)
                days_until_expiry = (exp_datetime - datetime.now(timezone.utc)).days
                
                self._jwt_metadata = {
                    "user_id": payload.get("sub"),
                    "email": payload.get("email"),
                    "role": payload.get("role"),
                    "expires_at": exp_datetime.isoformat(),
                    "days_until_expiry": days_until_expiry,
                    "is_expired": days_until_expiry < 0,
                    "needs_renewal": days_until_expiry < int(os.getenv("TOKEN_WARNING_DAYS", 30))
                }
                
                self._last_check = datetime.now(timezone.utc)
                
            except Exception as e:
                logger.error(f"Failed to decode JWT metadata: {e}")
                self._jwt_metadata = {
                    "error": str(e),
                    "is_expired": True,
                    "needs_renewal": True
                }
        
        return self._jwt_metadata
    
    def _should_refresh_metadata(self) -> bool:
        """Check if metadata should be refreshed."""
        if not self._last_check:
            return True
        return datetime.now(timezone.utc) - self._last_check > self._check_interval
    
    def validate_jwt(self) -> bool:
        """
        Validate the service JWT is not expired.
        
        Returns:
            True if JWT is valid, False otherwise
        """
        metadata = self.get_jwt_metadata()
        
        if metadata.get("is_expired"):
            logger.error("Service JWT is expired!")
            return False
        
        if metadata.get("needs_renewal"):
            logger.warning(f"Service JWT expires in {metadata.get('days_until_expiry')} days - renewal recommended")
        
        return True
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on service account configuration.
        
        Returns:
            Health status dictionary
        """
        try:
            has_jwt = bool(self._service_jwt or os.getenv("SUPABASE_SERVICE_JWT"))
            metadata = self.get_jwt_metadata() if has_jwt else {}
            
            return {
                "status": "healthy" if has_jwt and not metadata.get("is_expired") else "unhealthy",
                "has_jwt": has_jwt,
                "jwt_valid": not metadata.get("is_expired", True),
                "days_until_expiry": metadata.get("days_until_expiry"),
                "needs_renewal": metadata.get("needs_renewal", False),
                "service_account": {
                    "id": metadata.get("user_id") or self.service_account_id,
                    "email": metadata.get("email") or self.service_account_email
                },
                "storage_backend": self._get_storage_backend(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    def _get_storage_backend(self) -> str:
        """Get the current storage backend being used."""
        if os.getenv("AWS_SECRETS_MANAGER_ENABLED", "false").lower() == "true":
            return "aws_secrets_manager"
        elif os.getenv("VAULT_ENABLED", "false").lower() == "true":
            return "hashicorp_vault"
        elif os.getenv("AZURE_KEY_VAULT_ENABLED", "false").lower() == "true":
            return "azure_key_vault"
        elif os.getenv("SUPABASE_SERVICE_JWT"):
            return "environment_variable"
        elif os.path.exists("service_jwt_backup.json"):
            return "local_file"
        else:
            return "none"

# Global singleton instance
_service_config: Optional[ServiceAccountConfig] = None

@lru_cache(maxsize=1)
def get_service_config() -> ServiceAccountConfig:
    """
    Get the global service account configuration instance.
    
    Returns:
        ServiceAccountConfig singleton
    """
    global _service_config
    if not _service_config:
        _service_config = ServiceAccountConfig()
    return _service_config