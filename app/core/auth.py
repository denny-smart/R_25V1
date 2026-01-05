"""
Authentication and Authorization (Supabase)
Verifies Supabase JWT tokens and checks user approval status
"""

from typing import Optional, Dict
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging
from supabase.client import Client

from app.core.settings import settings
from app.core.supabase import supabase

logger = logging.getLogger(__name__)

# HTTP Bearer for token extraction
security = HTTPBearer(auto_error=False)

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[Dict]:
    """
    Dependency to get current authenticated user via Supabase
    Returns None if not authenticated (allows optional auth)
    """
    if not credentials:
        return None
    
    token = credentials.credentials
    
    try:
        # Verify user with Supabase Auth
        user_response = supabase.auth.get_user(token)
        user = user_response.user
        
        if not user:
            return None
            
        # Check profiles table for approval status
        # We use the service_role client (global 'supabase') to query the profiles table safely
        # assuming RLS might block normal users from seeing 'is_approved' if not careful,
        # but realistically the user should be able to see their own profile.
        # However, to be safe and authoritative, we query profiles using the ID.
        
        profile_response = supabase.table('profiles').select('*').eq('id', user.id).single().execute()
        
        if not profile_response.data:
            # Profile doesn't exist yet (maybe trigger failed?)
            logger.warning(f"Profile missing for user {user.id}")
            return {
                "id": user.id,
                "email": user.email,
                "is_approved": False,
                "role": "unknown",
                "aud": user.aud
            }
            
        profile = profile_response.data
        
        return {
            "id": user.id,
            "email": user.email,
            "is_approved": profile.get('is_approved', False),
            "role": profile.get('role', 'user'),
            "created_at": profile.get('created_at'),
            "aud": user.aud
        }
        
    except Exception as e:
        logger.error(f"Auth error: {e}")
        return None


async def require_auth(
    current_user: Optional[Dict] = Depends(get_current_user)
) -> Dict:
    """
    Dependency that REQUIRES authentication AND Admin Approval
    """
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not current_user.get("is_approved", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account not approved by admin. Please contact support."
        )
    
    return current_user


async def optional_auth(
    current_user: Optional[Dict] = Depends(get_current_user)
) -> Optional[Dict]:
    """
    Dependency for optional authentication
    """
    return current_user

# Alias for compatibility
get_current_active_user = require_auth


async def create_initial_admin():
    """
    Promote initial admin based on environment variable
    """
    import os
    email = os.getenv("INITIAL_ADMIN_EMAIL")
    if not email:
        return
        
    try:
        # Check if user exists
        response = supabase.table('profiles').select('*').eq('email', email).execute()
        if not response.data:
            logger.warning(f"Initial admin email {email} not found in profiles")
            return
            
        user = response.data[0]
        if user.get('role') == 'admin' and user.get('is_approved'):
            return
            
        # Promote
        supabase.table('profiles').update({
            'role': 'admin',
            'is_approved': True
        }).eq('id', user['id']).execute()
        logger.info(f"Promoted {email} to admin")
        
    except Exception as e:
        logger.error(f"Failed to create initial admin: {e}")