from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from ..services.auth import AuthService
from ..models.user import UserCreate, User, UserUpdate,AgentCreate,UserRole
from .auth import verify_admin, get_auth_service

router = APIRouter(prefix="/admin", tags=["admin"])

@router.post("/users", response_model=User)
async def create_user(
    user_data: UserCreate,
    current_user: User = Depends(verify_admin),
    auth_service: AuthService = Depends(get_auth_service)
):
    if user_data.role not in ["agent", "work"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin can only create agent or work users"
        )
    try:
        return await auth_service.create_user(user_data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("/users", response_model=List[User])
async def get_users(
    current_user: User = Depends(verify_admin),
    auth_service: AuthService = Depends(get_auth_service)
):
    # Get both agent and work users
    agents = await auth_service.get_users_by_role("agent")
    workers = await auth_service.get_users_by_role("work")
    return agents + workers

@router.get("/users/{user_id}", response_model=User)
async def get_user(
    user_id: str,
    current_user: User = Depends(verify_admin),
    auth_service: AuthService = Depends(get_auth_service)
):
    user = await auth_service.get_user_by_id(user_id)
    if not user or user.role not in ["agent", "work"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user

@router.put("/users/{user_id}", response_model=User)
async def update_user(
    user_id: str,
    user_update: UserUpdate,
    current_user: User = Depends(verify_admin),
    auth_service: AuthService = Depends(get_auth_service)
):
    user = await auth_service.get_user_by_id(user_id)
    if not user or user.role not in ["agent", "work"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if user_update.role and user_update.role not in ["agent", "work"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin can only manage agent or work users"
        )
    
    return await auth_service.update_user(user_id, user_update)

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: User = Depends(verify_admin),
    auth_service: AuthService = Depends(get_auth_service)
):
    user = await auth_service.get_user_by_id(user_id)
    if not user or user.role not in ["agent", "work"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    await auth_service.delete_user(user_id)
    return {"message": "User deleted successfully"}

@router.patch("/users/{user_id}/status")
async def toggle_user_status(
    user_id: str,
    status_update: dict,
    current_user: User = Depends(verify_admin),
    auth_service: AuthService = Depends(get_auth_service)
):
    user = await auth_service.get_user_by_id(user_id)
    if not user or user.role not in ["agent", "work"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    is_active = status_update.get("is_active")
    if is_active is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="is_active field is required"
        )
    
    return await auth_service.update_user_status(user_id, is_active)

@router.get("/dashboard/stats")
async def get_dashboard_stats(
    current_user: User = Depends(verify_admin),
    auth_service: AuthService = Depends(get_auth_service)
):
    stats = {
        "total_agents": await auth_service.count_users_by_role("agent"),
        "total_workers": await auth_service.count_users_by_role("work"),
        "active_agents": await auth_service.count_active_users_by_role("agent"),
        "active_workers": await auth_service.count_active_users_by_role("work")
    }
    return stats


@router.post("/agents", response_model=User)
async def create_agent(
    agent_data: AgentCreate,
    current_user: User = Depends(verify_admin),
    auth_service: AuthService = Depends(get_auth_service)
):
    # Vérifier que l'utilisateur courant est bien un admin
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin users can create agents"
        )
    
    # Assigner automatiquement le company_id de l'admin et le rôle
    agent_data.company_id = current_user.company_id
    agent_data.role = UserRole.AGENT  # S'assurer que c'est bien un agent
    
    try:
        return await auth_service.create_agent(agent_data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )