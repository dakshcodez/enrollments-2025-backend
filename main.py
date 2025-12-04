from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.domain import domain_app
from routes.user import user
from routes.answer import ans_app
from routes.slots import slot_app
from routes.admin import admin_app
from fastapi.responses import FileResponse
import os

origins = [
    "https://enrollments.ieeecsvit.com",
    "http://localhost:5173",
    "http://localhost:3000",
    "https://admin-portal-three-peach.vercel.app"
]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=600,
)

@app.get("/")
def read_root():
    return {"message": "Welcome to FastAPI!"}

@app.get("/favicon.ico")
def get_favicon():
    favicon_path = os.path.join(os.path.dirname(__file__), "favicon.svg")
    return FileResponse(favicon_path)


app.mount("/user", user)
app.mount("/admin", admin_app)
app.mount("/domain", domain_app)
app.mount("/answer", ans_app)
app.mount("/slots", slot_app)