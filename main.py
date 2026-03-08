from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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

MOCK_RESULTS = [
    {"id": "1", "username": "fitcoach_sarah", "full_name": "Sarah Johnson", "followers": 8400, "qualification_score": 87, "detected_niche": "Fitness", "bio": "Personal trainer | Online coaching | DM for programs 💪", "email_in_bio": "sarah@fitpro.com", "engagement_rate": 4.2},
    {"id": "2", "username": "realestate_mike", "full_name": "Mike Torres", "followers": 12300, "qualification_score": 92, "detected_niche": "Real Estate", "bio": "Real estate investor | CEO @miketorresprop", "email_in_bio": None, "engagement_rate": 3.8},
    {"id": "3", "username": "ecom_brandlab", "full_name": "Brand Lab", "followers": 5600, "qualification_score": 74, "detected_niche": "E-commerce", "bio": "Ecommerce branding studio | Book a call below 👇", "email_in_bio": "hello@brandlab.co", "engagement_rate": 5.1},
    {"id": "4", "username": "dentalstudio_nyc", "full_name": "NYC Dental Studio", "followers": 3200, "qualification_score": 81, "detected_niche": "Healthcare", "bio": "Premium dental care in Manhattan | Booking open!", "email_in_bio": None, "engagement_rate": 6.3},
    {"id": "5", "username": "coach_lifestyle", "full_name": "Alex Rivera", "followers": 19800, "qualification_score": 65, "detected_niche": "Coaching", "bio": "Life & business coach | Speaker | DM START to begin", "email_in_bio": "alex@coachlife.com", "engagement_rate": 2.9},
    {"id": "6", "username": "luxuryhomes_la", "full_name": "LA Luxury Homes", "followers": 7100, "qualification_score": 88, "detected_niche": "Real Estate", "bio": "Luxury real estate LA | Selling $1M+ homes", "email_in_bio": None, "engagement_rate": 4.7},
    {"id": "7", "username": "yogastudio_berlin", "full_name": "Berlin Yoga", "followers": 4200, "qualification_score": 79, "detected_niche": "Wellness", "bio": "Yoga studio Berlin | Classes daily | Book online", "email_in_bio": "info@berlinyoga.de", "engagement_rate": 7.2},
    {"id": "8", "username": "smma_growth", "full_name": "Growth Agency", "followers": 9800, "qualification_score": 91, "detected_niche": "Marketing", "bio": "Social media agency | We grow brands | DM for audit", "email_in_bio": "hello@growthagency.co", "engagement_rate": 3.4},
]

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
            "INSERT INTO search_jobs (id, query, search_type, status, result_count) VALUES ($1, $2, $3, $4, $5)",
            job_id, req.query, req.search_type, "completed", len(MOCK_RESULTS)
        )
        return {"job_id": job_id, "status": "completed", "results": MOCK_RESULTS}
    finally:
        await db.close()

@app.get("/api/search/{job_id}")
async def get_search(job_id: str):
    db = await get_db()
    try:
        job = await db.fetchrow("SELECT * FROM search_jobs WHERE id=$1", job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Not found")
        return {"job_id": job_id, "status": "completed", "results": MOCK_RESULTS}
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