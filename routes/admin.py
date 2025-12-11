from fastapi import FastAPI, Depends, File, UploadFile, Form, Query
from middleware.verifyToken import get_access_token
from config import initialize
from fastapi.responses import JSONResponse
from firebase_admin import auth
from typing import Optional, List
from pydantic import BaseModel
import os
import uuid
from datetime import datetime
import boto3
import json
from boto3.dynamodb.conditions import Attr
from decimal import Decimal

# Cloudflare R2 Bucket (S3-compatible)
R2_BUCKET_NAME = os.getenv('MY_R2_BUCKET_NAME')
if not R2_BUCKET_NAME:
    raise ValueError("R2_BUCKET_NAME environment variable is not set")

admin_app = FastAPI()

resources = initialize()
admin_table = resources['admin_table']

DOMAIN_MAPPING = {
    "UI/UX": "ui",
    "GRAPHIC DESIGN": "graphic",
    "VIDEO EDITING": "video",
    'EVENTS': 'events',
    'PNM': 'pnm',
    'WEB': 'web',
    'IOT': 'iot',
    'APP': 'app',
    'AI/ML': 'ai',
    'RND': 'rnd',
    'CC': 'cc',
    "WEB":"web"
}

from fastapi import HTTPException
from fastapi.responses import JSONResponse

async def verify_admin(authorization: str, required_domain: str = None):
    try:
        decoded_token = auth.verify_id_token(authorization, app=resources['firebase_app'])
        email = decoded_token.get('email')

        if not email:
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication failed: No email in token"}
            )

        admin_response = admin_table.get_item(Key={'email': email})
        admin = admin_response.get('Item')

        if not admin:
            return JSONResponse(
                status_code=403,
                content={"detail": "Access denied: Not an admin"}
            )

        if required_domain:
            allowed_domains = admin.get('allowed_domains', [])
            if required_domain not in allowed_domains:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Access denied: No permission for this domain"}
                )

        return admin

    except Exception as e:
        return JSONResponse(
            status_code=401,
            content={"detail": f"Authentication failed: {str(e)}"}
        )

def is_head_admin(admin: dict) -> bool:
    return admin.get('role') == 'head-admin'

class AddSubAdminRequest(BaseModel):
    email:str
    allowed_domains: List[str]

@admin_app.post('/add-sub-admin')
async def add_sub_admin(
    request: AddSubAdminRequest,
    authorization: str = Depends(get_access_token)
):
    try:
        admin_result = await verify_admin(authorization)
        if isinstance(admin_result, JSONResponse):
            return admin_result
        
        if not is_head_admin(admin_result):
            raise HTTPException(status_code=403, detail="Access denied: Not a head admin")

        requester_domains = set(admin_result.get('allowed_domains', []))
        requested_domains = set(request.allowed_domains)
    
        if not requested_domains.issubset(requester_domains):
            return JSONResponse(
                status_code=403,
                content={"detail": "You can only assign domains you have access to"}
            )
        
        sub_admin_response = admin_table.get_item(Key={'email': request.email})
        sub_admin = sub_admin_response.get('Item')
        
        if sub_admin:
            raise HTTPException(status_code=400, detail="Sub admin already exists")
        
        admin_table.put_item(
            Item={
                'email': request.email,
                'role': 'sub-admin',
                'allowed_domains': request.allowed_domains,
                'created-by': admin_result['email'] 
            }
        )
        
        return JSONResponse(status_code=200, content={"detail": "Sub admin added successfully"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@admin_app.get("/list-sub-admins")
async def list_sub_admins(authorization: str = Depends(get_access_token)):
    admin = await verify_admin(authorization)
    if isinstance(admin, JSONResponse):
        return admin
    
    if not is_head_admin(admin):
        return JSONResponse(status_code=403, content={"detail": "Only head-admins can list sub-admins"})
    
    # Scan for sub-admins created by this head-admin
    response = admin_table.scan(
        FilterExpression=Attr('created-by').eq(admin['email'])
    )
    
    return {"sub_admins": response.get('Items', [])}

@admin_app.delete("/remove-sub-admin")
async def remove_sub_admin(
    email: str,
    authorization: str = Depends(get_access_token)
):
    admin = await verify_admin(authorization)
    if isinstance(admin, JSONResponse):
        return admin
    
    if not is_head_admin(admin):
        return JSONResponse(status_code=403, content={"detail": "Only head-admins can remove sub-admins"})
    
    # Get the sub-admin to verify they were created by this head-admin
    sub_admin_response = admin_table.get_item(Key={'email': email})
    sub_admin = sub_admin_response.get('Item')
    
    if not sub_admin:
        return JSONResponse(status_code=404, content={"detail": "Sub-admin not found"})
    
    if sub_admin.get('created-by') != admin['email']:
        return JSONResponse(status_code=403, content={"detail": "You can only remove sub-admins you created"})
    
    admin_table.delete_item(Key={'email': email})
    
    return JSONResponse(status_code=200, content={"detail": "Sub-admin removed successfully"})

@admin_app.get('/fetch')
async def fetch_domains(
    domain: str,
    round: int,
    status: str,
    last_evaluated_key: Optional[str] = Query(None),
    authorization: str = Depends(get_access_token)
):
    try:
        admin_result = await verify_admin(authorization, domain)
        if isinstance(admin_result, JSONResponse):
            return admin_result
        
        if round < 1:
            raise HTTPException(status_code=400, detail="Round number must be greater than 0")
        
        mapped_domain = DOMAIN_MAPPING.get(domain)
        if not mapped_domain:
            raise HTTPException(status_code=400, detail="Invalid domain specified")
        
        domain_table = resources['domain_tables'].get(mapped_domain)
        if not domain_table:
            raise HTTPException(status_code=500, detail="Domain table not configured")
        
        qualification_attr = f'qualification_status{round}'
        previous_round_attr = f'qualification_status{round - 1}'

        def scan_table(filter_conditions):
            scan_params = {'FilterExpression': filter_conditions}
            if last_evaluated_key and last_evaluated_key != "start":
                scan_params['ExclusiveStartKey'] = {'email': last_evaluated_key}
            
            collected_items = []
            last_key = None
            
            while True:
                response = domain_table.scan(**scan_params)
                collected_items.extend(response.get('Items', []))
                last_key = response.get('LastEvaluatedKey')
                if not last_key:
                    break
                scan_params['ExclusiveStartKey'] = last_key
            
            return collected_items, last_key

        if round == 1:
            if status.lower() == "unmarked":
                filter_conditions = Attr(qualification_attr).not_exists() | Attr(qualification_attr).eq(None)
            else:
                filter_conditions = Attr(qualification_attr).eq(status)
            collected_items, last_key = scan_table(filter_conditions)

        elif round == 2:
            if domain == "WEB":
                frontend_conditions = (
                Attr(previous_round_attr).eq("qualified") & 
                Attr("frontend").exists()  
                )

                backend_conditions = (
                    Attr(previous_round_attr).eq("qualified") & 
                    Attr("backend").exists()  
                )



                if status.lower() == "unmarked":
                    frontend_conditions &= (~Attr(qualification_attr).exists() | Attr(qualification_attr).eq(None))
                    backend_conditions &= (~Attr(qualification_attr).exists() | Attr(qualification_attr).eq(None))
                else:
                    frontend_conditions &= Attr(qualification_attr).eq(status)
                    backend_conditions &= Attr(qualification_attr).eq(status)

                frontend_items, frontend_last_key = scan_table(frontend_conditions)
                backend_items, backend_last_key = scan_table(backend_conditions)

                return JSONResponse(
                status_code=200, 
                content=json.loads(json.dumps(
                    {
                        "items": {
                            "round2": {
                                "FRONTEND": frontend_items,
                                "BACKEND": backend_items
                            }
                        }
                    }, 
                    default=lambda obj: float(obj) if isinstance(obj, Decimal) else obj
                ))
                )
            else:
                filter_conditions = Attr(previous_round_attr).eq("qualified") & Attr("round2").exists()
                if status.lower() == "unmarked":
                    filter_conditions &= (~Attr(qualification_attr).exists() | Attr(qualification_attr).eq(None))
                else:
                    filter_conditions &= Attr(qualification_attr).eq(status)
                collected_items, last_key = scan_table(filter_conditions)

        return JSONResponse(
            status_code=200, 
            content=json.loads(json.dumps(
                {
                    "items": collected_items,
                    "last_evaluated_key": last_key['email'] if last_key else None
                }, 
                default=lambda obj: float(obj) if isinstance(obj, Decimal) else obj
            ))
        )
    
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    except Exception as e:
        return JSONResponse(status_code=400, content={"detail": f"Error processing request: {str(e)}"})

class QuestionData(BaseModel):
    question: str
    options: list
    correctIndex: str
    image: Optional[UploadFile] = None

class AddRequest(BaseModel):
    domain: str
    round: int
    question_data: QuestionData

async def upload_to_s3(file: UploadFile, bucket_name: str) -> str:
    # Debug logging
    print(f"🔍 DEBUG: Bucket name = {bucket_name}")
    print(f"🔍 DEBUG: R2 Endpoint = {os.getenv('MY_R2_ENDPOINT')}")
    print(f"🔍 DEBUG: Access Key exists = {os.getenv('MY_R2_ACCESS_KEY') is not None}")
    
    # Cloudflare R2 client (S3-compatible)
    s3_client = boto3.client(
        's3',
        endpoint_url=os.getenv("MY_R2_ENDPOINT"),  # R2 endpoint
        aws_access_key_id=os.getenv("MY_R2_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("MY_R2_SECRET_KEY"),
        region_name='auto'  # R2 uses 'auto' for region
    )

    file_extension = file.filename.split('.')[-1]
    unique_filename = f"{uuid.uuid4()}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.{file_extension}"

    s3_client.upload_fileobj(
        file.file,
        bucket_name,
        unique_filename,
        ExtraArgs={
            "ContentType": file.content_type
        }
    )

    # Use R2 public URL (from R2.dev subdomain or custom domain)
    r2_public_url = os.getenv("MY_R2_PUBLIC_URL")
    if not r2_public_url:
        raise ValueError("MY_R2_PUBLIC_URL environment variable is not set")
    
    url = f"{r2_public_url}/{unique_filename}"
    return url

@admin_app.post('/questions')
async def add_question(
    domain: str = Form(...),
    round: str = Form(...),
    question: str = Form(...),
    options: Optional[List[str]] = Form([]),
    correctIndex: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    authorization: str = Depends(get_access_token)
):
    try:
        admin_result = await verify_admin(authorization, domain)
        if isinstance(admin_result, JSONResponse):
            return admin_result
        quiz_table = resources['quiz_table']
        question_data_dict = {"question": question}

        if options:
            options = json.loads(options[0])
            question_data_dict["options"] = options
            if correctIndex:
                question_data_dict["correctIndex"] = int(correctIndex)

        if image:
            image_url = await upload_to_s3(image, bucket_name=R2_BUCKET_NAME)
            question_data_dict["image_url"] = image_url

        print(question_data_dict)
        response = quiz_table.get_item(Key={'qid': domain})
        field = response.get('Item') or {}  

        question_key = f"mcq{round}" if options else f"desc{round}"

        if question_key not in field:
            field[question_key] = []

        field[question_key].append(question_data_dict)
        field['qid'] = domain 

        quiz_table.put_item(Item=field)

        return JSONResponse(
            status_code=200,
            content={"detail": "Question added successfully", "total_questions": len(field[question_key])}
        )

    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"detail": f"Error processing request: {str(e)}"}
        )


class QualificationRequest(BaseModel):
    user_email: str
    domain: str
    status: str
    round: int

@admin_app.post('/qualify')
async def mark_qualification(request: QualificationRequest, authorization: str = Depends(get_access_token)):

    try:
        if request.status not in {"qualified", "unqualified", "pending"}:
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid status. Must be 'qualified', 'unqualified', or 'pending'."}
            )
        
        # if request.round==1:
        #     return JSONResponse(
        #         status_code=203,
        #         content={"detail": "Round 1 evaluations are closed'."}
        #     )

        admin_result = await verify_admin(authorization, request.domain)
        if isinstance(admin_result, JSONResponse):
            return admin_result
        
        email = admin_result['email']

        mapped_domain = DOMAIN_MAPPING.get(request.domain)
        if not mapped_domain:
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid domain specified"}
            )

        domain_table = resources['domain_tables'].get(mapped_domain)
        if not domain_table:
            return JSONResponse(
                status_code=500,
                content={"detail": "Domain table not configured"}
            )

        user_response = domain_table.get_item(Key={'email': request.user_email})
        user = user_response.get('Item')

        if not user:
            return JSONResponse(
                status_code=404,
                content={"detail": "User not found"}
            )

        if request.round > 1:
            prev_status = user.get(f'qualification_status{request.round-1}')
            if not prev_status or prev_status.lower() != "qualified":
                return JSONResponse(
                    status_code=409,
                    content={"detail": f"User {request.user_email} did not qualify in round {request.round-1}"}
                )

        user[f'qualification_status{request.round}'] = request.status
        user[f'updated_by']=email
        domain_table.put_item(Item=user)
        user_table=resources['user_table']
        response = user_table.get_item(Key={"uid": request.user_email})
        user_info = response.get("Item")
        user_info.setdefault(f'status{request.round}', {})[f'{request.domain}'] = request.status
        user_table.put_item(Item=user_info)

        return JSONResponse(
            status_code=200,
            content={"detail": f"User {request.user_email} marked as {request.status} for round {request.round}"}
        )

    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"detail": f"Error processing request: {str(e)}"}
        )
    
@admin_app.get('/questions')
async def get_qs(domain: str, round: str, authorization: str = Depends(get_access_token)):
    try:
        quiz_table = resources['quiz_table']
        admin_result = await verify_admin(authorization, domain)
        if isinstance(admin_result, JSONResponse):
            return admin_result

        response = quiz_table.get_item(Key={'qid': domain})
        field = response.get('Item')

        if not field:
            return JSONResponse(status_code=404, content={"detail": "Invalid domain"})

        mcq_key = f"mcq{round}"
        desc_key = f"desc{round}"

        mcq_questions = field.get(mcq_key, [])
        desc_questions = field.get(desc_key, [])

        if not mcq_questions and not desc_questions:
            return JSONResponse(status_code=204, content={"detail": f"Round {round} Questions not found"})

        formatted_mcq = [
            {
                "question": q["question"],
                "options": q["options"],
                "correctIndex": int(q["correctIndex"]),
                **({"image_url": str(q["image_url"])} if "image_url" in q else {})
            }
            for q in mcq_questions
        ]

        formatted_desc = [
            {
                "question": q["question"],
                **({"image_url": str(q["image_url"])} if "image_url" in q else {})
            }
            for q in desc_questions
        ]

        return JSONResponse(content={"mcq_questions": formatted_mcq, "desc_questions": formatted_desc})


    except Exception as e:
        return JSONResponse(status_code=400, content={"detail": f"Error: {str(e)}"})


# delete later

round_table = resources["user_table"]

def delete_email_entries(table_name: str, email: str):
    table = resources["domain_tables"].get(table_name)
    if not table:
        return f"Table {table_name} not found."

    response = table.get_item(Key={"email": email})
    if "Item" in response:
        table.delete_item(Key={"email": email})
        return f"Deleted {email} from {table_name}"
    return f"Email {email} not found in {table_name}"

def remove_round1_attribute(email: str):
    response = round_table.get_item(Key={"uid": email})
    if "Item" in response:
        round_table.update_item(
            Key={"uid": email},
            UpdateExpression="REMOVE round1"
        )
        return f"Removed 'round1' from {email}"
    return f"Uid {email} not found in round table"

@admin_app.post("/delete-responses")
def delete_email(email: str):
    emails = ["aniruddha.neema2023@vitstudent.ac.in","shubham.prasad2023@vitstudent.ac.in","medhansh.jain2022a@vitstudent.ac.in"]
    if email not in emails:
        return {"message":"you cannot delete responses"}
    results = [delete_email_entries(table, email) for table in resources["domain_tables"].keys()]
    round1_result = remove_round1_attribute(email)
    results.append(round1_result)

    return {"message": " Email deletions and updates completed.", "details": results}

@admin_app.get("/search")
async def search_user(email: str = Query(..., description="User email to search"), authorization: str = Depends(get_access_token)):
    admin_result = await verify_admin(authorization)
    if isinstance(admin_result, JSONResponse):
        return admin_result
    
    response = round_table.get_item(Key={"uid": email})
    user = response.get("Item")

    if not user:
        return JSONResponse(status_code=404, content="User not found")

    return {
        "email": email,
        "status1": user.get("status1", {}),
        "status2": user.get("status2", {})
    }


class SlotRequest(BaseModel):
    domain: str
    date: str
    startTime: str
    endTime: str
    panel: int

@admin_app.post("/create-slot")
async def create_slot(slot_request: SlotRequest, authorization: str = Depends(get_access_token)):
    admin_result = await verify_admin(authorization, slot_request.domain)
    if isinstance(admin_result, JSONResponse):
        return admin_result

    # Create unique ID: DOMAIN_DATE_START_PANEL
    slot_id = f"{slot_request.domain}_{slot_request.date}_{slot_request.startTime}_P{slot_request.panel}"

    interview_table = resources["interview_table"]

    try:
        interview_table.put_item(
            Item={
                "iid": slot_id,
                "domain": slot_request.domain,
                "date": slot_request.date,
                "time_slot": f"{slot_request.startTime} - {slot_request.endTime}",
                "panel": slot_request.panel, 
                "isBooked": False, 
                "bookedBy": None
            }
        )
        return JSONResponse(status_code=200, content={"detail": f"Slot created successfully for Panel {slot_request.panel}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"Error creating slot: {str(e)}"})