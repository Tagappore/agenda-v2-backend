from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from datetime import datetime, timedelta
from ..models.user import User
from ..models.schedule import Schedule, ScheduleCreate
from .auth import get_current_user
from motor.motor_asyncio import AsyncIOMotorClient
from ..config import settings

router = APIRouter(prefix="/work", tags=["work"])

@router.get("/schedule", response_model=List[Schedule])
async def get_user_schedule(
    current_user: User = Depends(get_current_user)
):
    # Ensure the user is a work user
    if current_user.role != "work":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only work users can access their schedule"
        )
    
    # Get current date
    today = datetime.now().date()
    
    # Get schedule for the current month
    month_start = today.replace(day=1)
    if today.month == 12:
        month_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        month_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    
    # Query the database for the schedule
    db = AsyncIOMotorClient(settings.mongodb_url)[settings.database_name]
    schedule_items = await db.schedules.find({
        "user_id": str(current_user.id),
        "date": {
            "$gte": month_start,
            "$lte": month_end
        }
    }).to_list(None)
    
    # Convert to Schedule objects
    schedule = []
    for item in schedule_items:
        item["id"] = str(item["_id"])
        schedule.append(Schedule(**item))
    
    return schedule

@router.get("/schedule/upcoming", response_model=List[Schedule])
async def get_upcoming_schedule(
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "work":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only work users can access their schedule"
        )
    
    # Get upcoming schedule (next 7 days)
    today = datetime.now().date()
    end_date = today + timedelta(days=7)
    
    db = AsyncIOMotorClient(settings.mongodb_url)[settings.database_name]
    schedule_items = await db.schedules.find({
        "user_id": str(current_user.id),
        "date": {
            "$gte": today,
            "$lte": end_date
        }
    }).sort("date", 1).to_list(None)
    
    # Convert to Schedule objects
    schedule = []
    for item in schedule_items:
        item["id"] = str(item["_id"])
        schedule.append(Schedule(**item))
    
    return schedule

@router.get("/schedule/{month_year}", response_model=List[Schedule])
async def get_month_schedule(
    month_year: str,  # Format: "YYYY-MM"
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "work":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only work users can access their schedule"
        )
    
    try:
        year, month = map(int, month_year.split("-"))
        month_start = datetime(year, month, 1).date()
        if month == 12:
            month_end = datetime(year + 1, 1, 1).date() - timedelta(days=1)
        else:
            month_end = datetime(year, month + 1, 1).date() - timedelta(days=1)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid month-year format. Use YYYY-MM"
        )
    
    db = AsyncIOMotorClient(settings.mongodb_url)[settings.database_name]
    schedule_items = await db.schedules.find({
        "user_id": str(current_user.id),
        "date": {
            "$gte": month_start,
            "$lte": month_end
        }
    }).sort("date", 1).to_list(None)
    
    schedule = []
    for item in schedule_items:
        item["id"] = str(item["_id"])
        schedule.append(Schedule(**item))
    
    return schedule

@router.get("/schedule/stats/monthly", response_model=dict)
async def get_monthly_stats(
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "work":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only work users can access their schedule statistics"
        )
    
    # Get current month's statistics
    today = datetime.now().date()
    month_start = today.replace(day=1)
    if today.month == 12:
        month_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        month_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    
    db = AsyncIOMotorClient(settings.mongodb_url)[settings.database_name]
    schedule_items = await db.schedules.find({
        "user_id": str(current_user.id),
        "date": {
            "$gte": month_start,
            "$lte": month_end
        }
    }).to_list(None)
    
    # Calculate statistics
    total_hours = sum(
        (datetime.strptime(item["end_time"], "%H:%M") - 
         datetime.strptime(item["start_time"], "%H:%M")).total_seconds() / 3600
        for item in schedule_items
    )
    
    total_shifts = len(schedule_items)
    
    return {
        "total_hours": round(total_hours, 2),
        "total_shifts": total_shifts,
        "month": today.strftime("%B %Y")
    }