from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from ..services.auth import AuthService
from ..models.user import UserCreate, User, UserUpdate
from .auth import verify_super_admin, get_auth_service
from motor.motor_asyncio import AsyncIOMotorClient

router = APIRouter(prefix="/super-admin", tags=["super-admin"])

@router.post("/admins", response_model=User)
async def create_admin_user(
    user_data: UserCreate,
    current_user: User = Depends(verify_super_admin),
    auth_service: AuthService = Depends(get_auth_service)
):
    try:
        user_data.role = "admin"
        return await auth_service.create_user(user_data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("/admins", response_model=List[User])
async def get_admin_users(
    current_user: User = Depends(verify_super_admin),
    auth_service: AuthService = Depends(get_auth_service)
):
    return await auth_service.get_users_by_role("admin")

@router.get("/admins/{admin_id}", response_model=User)
async def get_admin_user(
    admin_id: str,
    current_user: User = Depends(verify_super_admin),
    auth_service: AuthService = Depends(get_auth_service)
):
    user = await auth_service.get_user_by_id(admin_id)
    if not user or user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin user not found"
        )
    return user

@router.put("/admins/{admin_id}", response_model=User)
async def update_admin_user(
    admin_id: str,
    user_update: UserUpdate,
    current_user: User = Depends(verify_super_admin),
    auth_service: AuthService = Depends(get_auth_service)
):
    user = await auth_service.get_user_by_id(admin_id)
    if not user or user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin user not found"
        )
    
    return await auth_service.update_user(admin_id, user_update)

@router.delete("/admins/{admin_id}")
async def delete_admin_user(
    admin_id: str,
    current_user: User = Depends(verify_super_admin),
    auth_service: AuthService = Depends(get_auth_service)
):
    user = await auth_service.get_user_by_id(admin_id)
    if not user or user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin user not found"
        )
    
    await auth_service.delete_user(admin_id)
    return {"message": "Admin user deleted successfully"}

@router.patch("/admins/{admin_id}/status")
async def toggle_admin_status(
    admin_id: str,
    status_update: dict,
    current_user: User = Depends(verify_super_admin),
    auth_service: AuthService = Depends(get_auth_service)
):
    user = await auth_service.get_user_by_id(admin_id)
    if not user or user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin user not found"
        )
    
    is_active = status_update.get("is_active")
    if is_active is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="is_active field is required"
        )
    
    # Si on désactive l'admin, déclencher la désactivation en cascade
    if not is_active:
        await auth_service.cascade_deactivate_admin(admin_id)
        # Invalider les tokens de l'entreprise
        company_id = user.get("company_id")
        if company_id:
            await auth_service.invalidate_company_tokens(str(company_id))
    
    return await auth_service.update_user_status(admin_id, is_active)