from fastapi import FastAPI, HTTPException, Depends
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

# Route for getting slots from interview table
@slot_app.get("/get-slots")
async def get_slots(resources: dict = Depends(initialize)):
    try:
        # Fetching all slots from the interview table
        response = interview_table.scan()
        slots = response.get('Items', [])

        if not slots:
            raise HTTPException(status_code=404, detail="No slots found")
    
        return {"message": "Slots have been fetched successfully", "slots": slots}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error retrieving slots: {str(e)}")
    
# Struct for slot
class Slot(BaseModel):
    iid: str
    time_slot: str

# Route for posting selected slots
@slot_app.post("/post-slots")
async def post_slots(slot_req: Slot, idToken: str = Depends(get_access_token), resources: dict = Depends(initialize)):
    try:
        # Verifying token and fetching user records
        decoded_token = auth.verify_id_token(idToken, app=firebase_app)
        email = decoded_token.get('email')

        response = user_table.get_item(Key={'uid': email})
        user = response.get('Item')

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # 1. Check if slot is already booked (Concurrency check)
        slot_response = interview_table.get_item(Key={'iid': slot_req.iid})
        slot_item = slot_response.get('Item')
        
        if not slot_item:
             raise HTTPException(status_code=404, detail="Slot not found")
             
        if slot_item.get('isBooked'):
             raise HTTPException(status_code=409, detail="Slot is already booked")

        # 2. Mark it as Booked in Interview Table
        interview_table.update_item(
            Key={'iid': slot_req.iid},
            UpdateExpression="set isBooked=:b, bookedBy=:u",
            ExpressionAttributeValues={
                ':b': True,
                ':u': email
            }
        )

        # Updating the user record with selected slot
        user["slot"] = [{
            "iid": slot_req.iid,
            "time": slot_req.time_slot
        }]
        
        result = user_table.put_item(Item=user)
        return {"message": "Slot selected successfully", "response": result}  

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error posting slot: {str(e)}")