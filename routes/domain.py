from fastapi import FastAPI, HTTPException, Depends, Response
from firebase_admin import auth
from typing import List, Dict
from middleware.verifyToken import get_access_token
from config import initialize
from fastapi.responses import JSONResponse
from cryptography.fernet import Fernet
import base64
import os
import random

domain_app = FastAPI()

resources = initialize()
user_table = resources['user_table']
quiz_table = resources['quiz_table']

DOMAIN_QUESTION_CONFIG = {
    "WEB": [12,0],
    "APP": [12,0],
    "AI/ML": [12,0],
    "CC": [12,0],
    "UI/UX": [5, 5],
    "VIDEO": [5, 5],
    "EVENTS": [9, 5],
    "PNM": [12, 3]
}

# @domain_app.post('/submit')
# async def post_domain(domain: Dict[str, List[str]], id_token: str = Depends(get_access_token)):
#     try:
#         decoded_token = auth.verify_id_token(id_token, app=resources['firebase_app'])
#         email = decoded_token.get('email')

#         response = user_table.get_item(Key={'uid': email})
#         user = response.get('Item')

#         if not user:
#             raise HTTPException(status_code=404, content="User not found")

#         if "round1" in user:
#             return JSONResponse(status_code=204, content="Quiz Started")

#         if not domain:
#             raise HTTPException(status_code=400, content="Domain list cannot be empty")

#         for key, domain_list in domain.items():
#             limit = 3 if "CC" in domain_list else 2
#             if len(domain_list) > limit:
#                 raise HTTPException(status_code=400, detail=f"Domain array for key {key} cannot have more than {limit} entries")

#         user['domain'] = domain
#         user_table.put_item(Item=user)

#         return JSONResponse(status_code=200, content=domain)

#     except Exception as e:
#         raise HTTPException(status_code=400, content=f"Error: {str(e)}")


@domain_app.get('/questions')
async def get_qs(domain: str, round: str, id_token: str = Depends(get_access_token)):
    try:
        decoded_token = auth.verify_id_token(id_token, app=resources['firebase_app'])
        email = decoded_token.get('email')
        response = quiz_table.get_item(Key={'qid': domain})
        field = response.get('Item')

        if not field:
            return JSONResponse(status_code=404, content="Invalid domain")

        mcq_data = field.get(f"mcq{round}", [])
        desc_data = field.get(f"desc{round}", [])

        if not mcq_data:
            return JSONResponse(status_code=204, content=f"Round {round} MCQ Questions not found")

        secret_key = os.environ.get('MY_SECRET_KEY')
        if not secret_key:
            raise HTTPException(status_code=500, detail="Secret key not found in environment variables")

        # Get configuration for the domain, default to [7, 3] if not found
        # Format: [num_mcq, num_desc]
        counts = DOMAIN_QUESTION_CONFIG.get(domain, [7, 3]) 
        target_mcq_count = counts[0]
        target_desc_count = counts[1]

        # Select MCQs
        selected_mcq = random.sample(mcq_data, min(target_mcq_count, len(mcq_data)))

        # Select Descriptive
        selected_desc = random.sample(desc_data, min(target_desc_count, len(desc_data)))

        formatted_questions = []
        for q in selected_mcq + selected_desc:
            question_data = {"question": q["question"]}

            if "id" in q:
                question_data["id"] = str(q["id"])

            if "options" in q:
                question_data["options"] = q["options"]

            if "correctIndex" in q:
                correct_index_str = str(q["correctIndex"])
                import hashlib
                question_salt = hashlib.md5(q["question"].encode()).hexdigest()[:10]
                data_to_hash = f"{secret_key}{correct_index_str}{question_salt}"
                hashed_index = hashlib.sha256(data_to_hash.encode()).hexdigest()
                question_data["correctIndexHash"] = hashed_index
                question_data["salt"] = question_salt

            if "image_url" in q:
                question_data["image_url"] = str(q["image_url"])

            formatted_questions.append(question_data)

        return JSONResponse(content={"questions": formatted_questions})

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error: {str(e)}")