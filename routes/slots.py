from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import JSONResponse
from typing import List, Dict
from pydantic import BaseModel
from middleware.verifyToken import get_access_token
from firebase_admin import auth
from config import initialize

resources = initialize()
user_table = resources['user_table']
interview_table = resources['interview_table']
firebase_app = resources['firebase_app']

slot_app = FastAPI()

# Route for getting user's assigned slots
@slot_app.get("/get-slots")
async def get_slots(idToken: str = Depends(get_access_token), resources: dict = Depends(initialize)):
    """Get slots assigned to the logged-in user by admin"""
    try:
        # Verify token and get user email
        decoded_token = auth.verify_id_token(idToken, app=firebase_app)
        email = decoded_token.get('email')
        
        # Get user's assigned slots
        response = user_table.get_item(Key={'uid': email})
        user = response.get('Item')
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Get interview_slots from user record
        interview_slots = user.get('interview_slots', {})
        
        if not interview_slots:
            return {"message": "No slots assigned yet", "slots": []}
        
        # Format slots for response
        assigned_slots = []
        for round_key, slot_data in interview_slots.items():
            if slot_data:
                assigned_slots.append({
                    "round": round_key,
                    "iid": slot_data.get('iid'),
                    "time": slot_data.get('time'),
                    "panel": slot_data.get('panel'),
                    "domain": slot_data.get('domain'),
                    "assigned_at": slot_data.get('assigned_at')
                })
        
        return {"message": "Slots fetched successfully", "slots": assigned_slots}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error retrieving slots: {str(e)}")
    
# Struct for slot
class Slot(BaseModel):
    iid: str
    time_slot: str

# Route for posting selected slots - DEPRECATED
@slot_app.post("/post-slots")
async def post_slots(slot_req: Slot, idToken: str = Depends(get_access_token), resources: dict = Depends(initialize)):
    """DEPRECATED: Slots are now assigned by admins, not self-booked by users"""
    return JSONResponse(
        status_code=403,
        content={
            "detail": "Self-booking is disabled. Interview slots are assigned by admins.",
            "message": "Please wait for an admin to assign you a slot. You can view your assigned slot via GET /slots/get-slots"
        }
    )