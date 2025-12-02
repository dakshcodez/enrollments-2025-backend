import boto3
import firebase_admin
from firebase_admin import credentials
import os
from dotenv import load_dotenv
import json
import base64

load_dotenv()

def initialize():
    dynamodb = boto3.resource(
        'dynamodb',
        region_name=os.getenv("MY_AWS_REGION"),
        aws_access_key_id=os.getenv("MY_AWS_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("MY_AWS_SECRET_KEY")
    )

    domain_tables = {
        "ai": dynamodb.Table("domain-ai"),
        "app": dynamodb.Table("domain-app"),
        "events": dynamodb.Table("domain-events"),
        "graphic": dynamodb.Table("domain-graphic"),
        "iot": dynamodb.Table("domain-iot"),
        "pnm": dynamodb.Table("domain-pnm"),
        "rnd": dynamodb.Table("domain-rnd"),
        "ui": dynamodb.Table("domain-ui"),
        "video": dynamodb.Table("domain-video"),
        "web": dynamodb.Table("domain-web"),
        "cc": dynamodb.Table("domain-cc")
    }

    user_table = dynamodb.Table("enrollments-site-users")
    admin_table = dynamodb.Table("enrollments-site-admins")
    quiz_table = dynamodb.Table("enrollments-site-quiz")
    interview_table = dynamodb.Table("enrollments-site-interview")

    if not firebase_admin._apps:
        service_account_key = os.getenv("MY_FIREBASE_SERVICE_ACCOUNT_KEY")
        if service_account_key:
         
            try:
                decoded_key = json.loads(service_account_key)
            except json.JSONDecodeError:
              
                decoded_key = json.loads(base64.b64decode(service_account_key).decode('utf-8'))
            cred = credentials.Certificate(decoded_key)
            firebase_app = firebase_admin.initialize_app(cred)
        else:
            raise ValueError("FIREBASE_SERVICE_ACCOUNT_KEY is not set")
    else:
        firebase_app = firebase_admin.get_app()

    return {
        'firebase_app': firebase_app,
        'user_table': user_table,
        'admin_table':admin_table,
        'quiz_table': quiz_table,
        'interview_table': interview_table,
        'domain_tables': domain_tables
    }

resources = None

def get_resources():
    global resources
    if resources is None:
        resources = initialize()
    return resources
