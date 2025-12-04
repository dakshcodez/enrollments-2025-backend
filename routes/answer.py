from fastapi import FastAPI, HTTPException, Depends
from typing import List, Optional, Union
from pydantic import BaseModel, Field
from middleware.verifyToken import get_access_token
from firebase_admin import auth
from config import initialize
from fastapi.responses import JSONResponse
from botocore.exceptions import ClientError
from itertools import chain

ans_app = FastAPI()

resources = initialize()
user_table = resources['user_table']
firebase_app = resources['firebase_app']


class AnswerStruct(BaseModel):
    domain: str = Field(...)
    answers: List[str] = Field(...)
    round: int

domain_mapping = {
    "UI/UX": "ui",
    "GRAPHIC DESIGN": "graphic",
    "VIDEO EDITING": "video",
    'EVENTS':'events',
    'PNM':'pnm',
    'WEB':'web',
    # 'IOT':'iot',
    'APP':'app',
    'AI/ML':'ai',
    # 'RND':'rnd',
    "CC": "cc",
    "FRONTEND":"web",
    "BACKEND":"web",
}

@ans_app.post("/submit")
async def post_answers(answerReq: AnswerStruct, idToken: str = Depends(get_access_token)):
# async def post_answers(answerReq: AnswerStruct):
    try:
        decoded_token = auth.verify_id_token(idToken, app=resources["firebase_app"])
        email = decoded_token.get("email")
        # email='aryanramesh.jain2023@vitstudent.ac.in'

        if not email:
            return JSONResponse(status_code=401, content="Invalid or missing email in token.")

        response = user_table.get_item(Key={"uid": email})
        user = response.get("Item")

        if not user:
            return JSONResponse(status_code=404, content="User not found.")

        flat_domains = list(chain.from_iterable(user.get("domain", []).values()))
        if answerReq.domain not in flat_domains:
            return JSONResponse(status_code=408, content="Domain was not selected")
        mapped_domain = domain_mapping.get(answerReq.domain)
        # if answerReq.domain in ["GRAPHIC DESIGN", "CC", "AI/ML", "UI/UX", "VIDEO EDITING"]:
        #     raise HTTPException(status_code=401, detail=f"Deadline for '{answerReq.domain}' is over.")
        
        domain_tables = resources['domain_tables']
        domain_table = domain_tables.get(mapped_domain)

        if not domain_table:
            raise HTTPException(status_code=400, detail=f"Domain '{answerReq.domain}' not recognized.")

        # if len(answerReq.questions) != len(answerReq.answers):
        #     raise HTTPException(status_code=400, detail="Questions and answers lists must have the same length.")

        # answers_dict = [{"question": q, "answer": a} for q, a in zip(answerReq.questions, answerReq.answers)]
        response = domain_table.get_item(Key={'email': email})
        domain_response = response.get('Item')

        if answerReq.round == 1:
            if 'Item' in response:
                return JSONResponse(status_code=409, content="Answers already submitted")

            domain_table.put_item(
                Item={
                    "email": email,
                    # f"round{answerReq.round}": answers_dict,
                    # f"score{answerReq.round}": answerReq.score
                    "round1": answerReq.answers
                }
            )
        if answerReq.round == 2:
            # if not domain_response.get("round1"):
            #     return JSONResponse(status_code=201, content=f"Did not attempt round 1")


            if domain_response.get('qualification_status1') != "qualified":
                return JSONResponse(status_code=202, content=f"did not qualify round 1")

            if answerReq.domain=="FRONTEND":
                name="frontend"
            elif answerReq.domain=="BACKEND":
                name="backend"
            else:
                name="round2"
            
            domain_table.update_item(
                Key={"email": email},
                UpdateExpression=f"SET {name} = :answers",
                ExpressionAttributeValues={":answers": answerReq.answers}
            )

        existing_rounds = user.get(f"round{answerReq.round}", [])

        if answerReq.domain not in existing_rounds:
            user_table.update_item(
                Key={'uid': email},
                UpdateExpression=f"SET round{answerReq.round} = list_append(if_not_exists(round{answerReq.round}, :empty_list), :new_value)",
                ExpressionAttributeValues={
                    ':new_value': [answerReq.domain],
                    ':empty_list': []
                }
            )

        return JSONResponse(status_code=200,content=f"Answers for domain '{answerReq.domain}' submitted successfully for round {answerReq.round}.")

    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"DynamoDB error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error posting answers: {str(e)}")