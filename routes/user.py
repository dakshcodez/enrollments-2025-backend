from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from firebase_admin import auth
from pydantic import BaseModel
from middleware.verifyToken import get_access_token
from config import get_resources
from collections import defaultdict

user = FastAPI()

class LoginRequest(BaseModel):
    idToken: str

class UsernameRequest(BaseModel):
    username: str

@user.post("/login")
async def login(authorization: str = Depends(get_access_token), resources: dict = Depends(get_resources)):
    try:
        if not authorization:
            raise HTTPException(status_code=400, detail="Authorization token missing")

        try:
            decoded_token = auth.verify_id_token(authorization)
        except Exception as token_error:
            raise HTTPException(status_code=401, detail=f"Invalid token: {str(token_error)}")

        email = decoded_token.get('email')

        if not email:
            raise HTTPException(status_code=400, detail="Email not found in ID token")

        try:
            user_table = resources.get("user_table")
            response = user_table.get_item(Key={'uid': email})
            user = response.get('Item')

        except Exception as db_error:
            raise HTTPException(status_code=500, detail=f"Database lookup failed: {str(db_error)}")

        if user is None:
            return JSONResponse(content={"message": "User not registered on VTOP"}, status_code=204)
            # if not email.endswith('@vitstudent.ac.in'):
            #     return JSONResponse(status_code=403, content="User not registered on VTOP")

            name = decoded_token.get('name', '')
            
            user_table.put_item(Item={ 'uid' : email, 'name' : name})
            return JSONResponse(status_code=200, content="new user registered successfully")

        if 'username' not in user:
            return JSONResponse(status_code=201, content="Logged In Successfully")
        else:
            return JSONResponse(status_code=200, content="Logged In Successfully")

    except HTTPException:
        raise
    except Exception as unexpected_error:
        raise HTTPException(status_code=500, detail=f"Unexpected server error: {str(unexpected_error)}")

@user.get("/profile")
async def get_profile(authorization: str = Depends(get_access_token), resources: dict = Depends(get_resources)):
    try:
        decoded_token = auth.verify_id_token(authorization)
        email = decoded_token.get('email')
        response = resources['user_table'].get_item(Key={'uid': email})
        user = response.get('Item')
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return {
            "email": email,
            "username": user.get("username"),
            "mobile": user.get("mobile"),
            "name": user.get("name"),
            "domain": user.get("domain")
        }

    except auth.InvalidIdTokenError:
        raise HTTPException(status_code=401, detail="Invalid ID token")

@user.post("/username")
async def submit_username(
    username_request: UsernameRequest,
    authorization: str = Depends(get_access_token), resources: dict = Depends(get_resources)
):
    try:
        username = username_request.username.strip()
        if not username:
            return JSONResponse(status_code=400, content={"detail": "Username cannot be empty"})

        decoded_token = auth.verify_id_token(authorization)
        email = decoded_token.get('email')

        user_table = resources['user_table']
        response = user_table.get_item(Key={'uid': email})
        user = response.get('Item')

        if not user:
            raise HTTPException(status_code=404, content="User not registered on VTOP")

        if user.get('username'):
            return JSONResponse(status_code=409, content= "Username already exists for this user")

        gsi_response = user_table.query(
            IndexName="username-index",
            KeyConditionExpression="username = :username",
            ExpressionAttributeValues={":username": username}
        )
        if gsi_response.get('Items'):
            return JSONResponse(status_code=201, content= "Username already taken")

        user['username'] = username
        user_table.put_item(Item=user)

        return JSONResponse(status_code=200, content= "Username added successfully")

    except HTTPException as e:
        raise e
    except Exception as e:
        return JSONResponse(status_code=500, content= f"Internal Server Error: {str(e)}")

SUBDOMAIN_MAPPING = {
    "WEB": "Technical",
    "APP": "Technical",
    "AI/ML": "Technical",
    # "RND": "Technical",
    # "IOT": "Technical",
    "CC": "Technical",
    "PNM": "Management",
    "EVENTS": "Management",
    "UI/UX": "Design",
    # "GRAPHIC DESIGN": "Design",
    "VIDEO EDITING": "Design"
}
@user.get("/dashboard")
async def get_dashboard(
    round: int = Query(..., description="Round number"),
    authorization: str = Depends(get_access_token),
    resources: dict = Depends(get_resources)
):
    try:
        if not authorization:
            raise HTTPException(status_code=400, detail="Authorization token missing")

        try:
            decoded_token = auth.verify_id_token(authorization)
        except Exception as token_error:
            raise HTTPException(status_code=401, detail=f"Invalid token: {str(token_error)}")

        email = decoded_token.get('email')
        # email='aiman.parvezdhanani2024@vitstudent.ac.in'
        if not email:
            raise HTTPException(status_code=400, detail="Email not found in ID token")

        try:
            user_table = resources.get("user_table")
            response = user_table.get_item(Key={"uid": email})
            user = response.get("Item", {})

        except Exception as db_error:
            raise HTTPException(status_code=500, detail=f"Database lookup failed: {str(db_error)}")

        if round==1:
            domain_data = user.get("domain", {})  # Dictionary of domains and their subdomains
            completed_subdomains = set(user.get(f"round{round}", []))  # Subdomains completed in the round

            pending_list = []
            completed_list = []

            for domain, subdomains in domain_data.items():
                for sub in subdomains:
                    category = SUBDOMAIN_MAPPING.get(sub.upper(), "Other")
                    formatted_entry = f"{category}:{sub.upper()}"

                    if sub.upper() in completed_subdomains:
                        completed_list.append(formatted_entry)
                    else:
                        pending_list.append(formatted_entry)

        if round == 2:
            if "round1" not in user:
                return JSONResponse(status_code=201, content={"message": "Did not attempt round 1"})
            
            pending_list = []
            completed_list = []
            if "status1" not in user:
                return JSONResponse(status_code=200, content={
                    "pending": pending_list,
                    "completed": completed_list
                })

            status_data = user.get("status1", {})  

            for sub, status in status_data.items():
                category = SUBDOMAIN_MAPPING.get(sub.upper(), "Other")
                formatted_entry = f"{category}:{sub.upper()}"

                if status.lower() == "qualified":
                    completed_list.append(formatted_entry)
                else:
                    pending_list.append(formatted_entry)

        return JSONResponse(status_code=200, content={
            "pending": pending_list,
            "completed": completed_list,
            "slots":user.get("slots",{})
        })
                
    except Exception as unexpected_error:
        raise HTTPException(status_code=500, detail=f"Unexpected server error: {str(unexpected_error)}")
