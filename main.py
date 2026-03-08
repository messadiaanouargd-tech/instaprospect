from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import asyncpg
import uuid
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="InstaProspect API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")

async def get_db():
    return await asyncpg.connect(DATABASE_URL)

@app.get("/")
async def root():
    return {"name": "InstaProspect API", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "ok"}

class SearchRequest(BaseModel):
    query: str
    search_type: str = "hashtag"

@app.post("/api/search")
async def create_search(req: SearchRequest):
    db = await get_db()
    try:
        job_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO search_jobs (id, query, search_type, status) VALUES ($1, $2, $3, $4)",
            job_id, req.query, req.search_type, "pending"
        )
        return {"job_id": job_id, "status": "pending"}
    finally:
        await db.close()

@app.get("/api/search/{job_id}")
async def get_search(job_id: str):
    db = await get_db()
    try:
        job = await db.fetchrow("SELECT * FROM search_jobs WHERE id=$1", job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Not found")
        return dict(job)
    finally:
        await db.close()

@app.get("/api/leads")
async def get_leads():
    db = await get_db()
    try:
        rows = await db.fetch("""
            SELECT sl.id, sl.status, sl.list_name, sl.created_at,
                   sp.username, sp.full_name, sp.followers, 
                   sp.qualification_score, sp.detected_niche, sp.bio
            FROM saved_leads sl
            JOIN scraped_profiles sp ON sl.profile_id = sp.id
            WHERE sl.user_id = 'demo-user'
            ORDER BY sl.created_at DESC
        """)
        return [dict(r) for r in rows]
    finally:
        await db.close()

@app.patch("/api/leads/{lead_id}")
async def update_lead(lead_id: str, status: str):
    db = await get_db()
    try:
        await db.execute("UPDATE saved_leads SET status=$1 WHERE id=$2", status, lead_id)
        return {"message": "Updated"}
    finally:
        await db.close()