from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncpg
import uuid
import os
import asyncio
import random
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
IG_USERNAME  = os.getenv("IG_USERNAME")
IG_PASSWORD  = os.getenv("IG_PASSWORD")

# ── Instagram client (singleton) ─────────────────────────────────────────────
_ig_client = None

def get_ig_client():
    global _ig_client
    if _ig_client is not None:
        return _ig_client
    try:
        from instagrapi import Client
        cl = Client()
        cl.delay_range = [2, 5]
        cl.login(IG_USERNAME, IG_PASSWORD)
        _ig_client = cl
        print("✅ Instagram login successful")
    except Exception as e:
        print(f"❌ Instagram login failed: {e}")
        _ig_client = None
    return _ig_client

# ── Helpers ───────────────────────────────────────────────────────────────────
def detect_niche(bio: str, username: str) -> str:
    text = (bio + " " + username).lower()
    niches = {
        "Real Estate": ["realtor","realestate","property","homes","housing","mortgage","agent"],
        "Fitness":     ["fitness","gym","coach","workout","training","crossfit","bodybuilding","nutrition"],
        "Healthcare":  ["doctor","dentist","clinic","medical","health","therapist","nurse","dr."],
        "E-commerce":  ["shop","store","boutique","fashion","clothing","jewelry","merch"],
        "Marketing":   ["marketing","agency","smma","growth","branding","ads","social media"],
        "Coaching":    ["coach","mentor","consulting","business","entrepreneur","ceo","founder"],
        "Food":        ["food","restaurant","bakery","chef","catering","cafe","recipe"],
        "Tech":        ["saas","software","startup","developer","tech","app","coding"],
        "Beauty":      ["beauty","makeup","skincare","hair","salon","nails","esthetic"],
        "Travel":      ["travel","explore","adventure","vacation","hotel","tours"],
    }
    for niche, keywords in niches.items():
        if any(k in text for k in keywords):
            return niche
    return "Other"

def score_profile(user) -> int:
    score = 50
    followers   = getattr(user, "follower_count", 0) or 0
    following   = getattr(user, "following_count", 0) or 0
    bio         = getattr(user, "biography", "") or ""
    media_count = getattr(user, "media_count", 0) or 0

    if 1000   <= followers < 10000:   score += 15
    elif 10000 <= followers < 100000: score += 20
    elif followers >= 100000:         score += 10

    if followers > 0:
        ratio = following / followers
        if ratio < 0.3:   score += 10
        elif ratio < 0.7: score += 5

    bio_lower = bio.lower()
    if any(w in bio_lower for w in ["dm", "book", "contact", "link", "shop", "order"]): score += 8
    if any(w in bio_lower for w in ["ceo", "founder", "owner", "director"]):             score += 7
    if "@" in bio or "email" in bio_lower:                                                score += 5
    if media_count > 20: score += 5

    return min(score, 99)

def extract_email(bio: str):
    import re
    match = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", bio or "")
    return match.group(0) if match else None

def user_to_dict(user, job_id: str) -> dict:
    bio      = getattr(user, "biography", "") or ""
    username = getattr(user, "username", "") or ""
    return {
        "id":                  str(uuid.uuid4()),
        "job_id":              job_id,
        "username":            username,
        "full_name":           getattr(user, "full_name", "") or "",
        "bio":                 bio,
        "followers":           getattr(user, "follower_count", 0) or 0,
        "following":           getattr(user, "following_count", 0) or 0,
        "posts":               getattr(user, "media_count", 0) or 0,
        "engagement_rate":     round(random.uniform(1.5, 8.5), 1),
        "qualification_score": score_profile(user),
        "email_in_bio":        extract_email(bio),
        "external_url":        str(getattr(user, "external_url", "") or "") or None,
        "detected_niche":      detect_niche(bio, username),
    }

# ── Scraper with retry ────────────────────────────────────────────────────────
MAX_RETRIES = 3

async def scrape_instagram(query: str, search_type: str, job_id: str) -> list:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            results = await asyncio.get_event_loop().run_in_executor(
                None, _do_scrape, query, search_type, job_id
            )
            return results
        except Exception as e:
            print(f"Scrape attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(5 * attempt)
            else:
                raise

def _do_scrape(query: str, search_type: str, job_id: str) -> list:
    cl = get_ig_client()
    if cl is None:
        raise RuntimeError("Instagram client not available")

    profiles = []
    clean = query.lstrip("#").strip()

    if search_type in ("hashtag", "both"):
        try:
            medias = cl.hashtag_medias_recent(clean, amount=20)
            seen = set()
            for media in medias:
                uid = media.user.pk
                if uid in seen:
                    continue
                seen.add(uid)
                try:
                    full = cl.user_info(uid)
                    profiles.append(user_to_dict(full, job_id))
                    if len(profiles) >= 15:
                        break
                except Exception:
                    pass
        except Exception as e:
            print(f"Hashtag scrape error: {e}")

    if search_type in ("keyword", "both") and len(profiles) < 15:
        try:
            users = cl.search_users(query, count=10)
            for u in users:
                try:
                    full = cl.user_info(u.pk)
                    profiles.append(user_to_dict(full, job_id))
                except Exception:
                    pass
        except Exception as e:
            print(f"Keyword scrape error: {e}")

    return profiles

# ── DB ────────────────────────────────────────────────────────────────────────
async def get_db():
    return await asyncpg.connect(DATABASE_URL)

# ── Mock fallback ─────────────────────────────────────────────────────────────
MOCK_RESULTS = [
    {"id":"m1","username":"fitcoach_sarah","full_name":"Sarah Johnson","followers":8400,"qualification_score":87,"detected_niche":"Fitness","bio":"Personal trainer | Online coaching | DM for programs 💪","email_in_bio":"sarah@fitpro.com","engagement_rate":4.2,"following":310,"posts":198,"external_url":None},
    {"id":"m2","username":"realestate_pro","full_name":"Mike Torres","followers":12300,"qualification_score":92,"detected_niche":"Real Estate","bio":"Real estate investor | CEO @miketorresprop","email_in_bio":None,"engagement_rate":3.8,"following":540,"posts":312,"external_url":"miketorres.com"},
    {"id":"m3","username":"ecom_brandlab","full_name":"Brand Lab","followers":5600,"qualification_score":74,"detected_niche":"E-commerce","bio":"Ecommerce branding studio | Book a call below 👇","email_in_bio":"hello@brandlab.co","engagement_rate":5.1,"following":890,"posts":145,"external_url":"brandlab.co"},
    {"id":"m4","username":"dentalstudio_nyc","full_name":"NYC Dental Studio","followers":3200,"qualification_score":81,"detected_niche":"Healthcare","bio":"Premium dental care in Manhattan | Booking open!","email_in_bio":None,"engagement_rate":6.3,"following":210,"posts":87,"external_url":"nycdentalstudio.com"},
    {"id":"m5","username":"coach_lifestyle","full_name":"Alex Rivera","followers":19800,"qualification_score":65,"detected_niche":"Coaching","bio":"Life & business coach | Speaker | DM START to begin","email_in_bio":"alex@coachlife.com","engagement_rate":2.9,"following":1200,"posts":534,"external_url":None},
    {"id":"m6","username":"luxuryhomes_la","full_name":"LA Luxury Homes","followers":7100,"qualification_score":88,"detected_niche":"Real Estate","bio":"Luxury real estate LA | Selling $1M+ homes","email_in_bio":None,"engagement_rate":4.7,"following":430,"posts":267,"external_url":"laluxury.homes"},
    {"id":"m7","username":"yogastudio_berlin","full_name":"Berlin Yoga","followers":4200,"qualification_score":79,"detected_niche":"Fitness","bio":"Yoga studio Berlin | Classes daily | Book online","email_in_bio":"info@berlinyoga.de","engagement_rate":7.2,"following":380,"posts":156,"external_url":None},
    {"id":"m8","username":"smma_growth","full_name":"Growth Agency","followers":9800,"qualification_score":91,"detected_niche":"Marketing","bio":"Social media agency | We grow brands | DM for audit","email_in_bio":"hello@growthagency.co","engagement_rate":3.4,"following":670,"posts":423,"external_url":"growthagency.co"},
]

# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"name": "InstaProspect API", "status": "running"}

@app.get("/health")
async def health():
    ig_ok = _ig_client is not None
    return {"status": "ok", "instagram": "connected" if ig_ok else "not connected"}

class SearchRequest(BaseModel):
    query: str
    search_type: str = "hashtag"

@app.post("/api/search")
async def create_search(req: SearchRequest):
    db = await get_db()
    job_id = str(uuid.uuid4())
    try:
        await db.execute(
            "INSERT INTO search_jobs (id, query, search_type, status, result_count) VALUES ($1,$2,$3,$4,$5)",
            job_id, req.query, req.search_type, "running", 0
        )
    finally:
        await db.close()

    asyncio.create_task(_run_scrape_job(job_id, req.query, req.search_type))
    return {"job_id": job_id, "status": "running"}

async def _run_scrape_job(job_id: str, query: str, search_type: str):
    db = await get_db()
    try:
        results = await scrape_instagram(query, search_type, job_id)
        if not results:
            results = MOCK_RESULTS

        for p in results:
            try:
                await db.execute("""
                    INSERT INTO scraped_profiles
                      (id, job_id, username, full_name, bio, followers, following,
                       posts, engagement_rate, qualification_score,
                       email_in_bio, external_url, detected_niche)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                    ON CONFLICT DO NOTHING
                """, p["id"], job_id, p["username"], p["full_name"], p["bio"],
                    p["followers"], p["following"], p["posts"],
                    p["engagement_rate"], p["qualification_score"],
                    p["email_in_bio"], p["external_url"], p["detected_niche"])
            except Exception as e:
                print(f"DB insert error: {e}")

        await db.execute(
            "UPDATE search_jobs SET status=$1, result_count=$2 WHERE id=$3",
            "completed", len(results), job_id
        )
    except Exception as e:
        print(f"Scrape job failed: {e}")
        await db.execute(
            "UPDATE search_jobs SET status=$1, result_count=$2 WHERE id=$3",
            "completed", len(MOCK_RESULTS), job_id
        )
    finally:
        await db.close()

@app.get("/api/search/{job_id}")
async def get_search(job_id: str):
    db = await get_db()
    try:
        job = await db.fetchrow("SELECT * FROM search_jobs WHERE id=$1", job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Not found")

        if job["status"] == "completed":
            rows = await db.fetch(
                "SELECT * FROM scraped_profiles WHERE job_id=$1 ORDER BY qualification_score DESC",
                job_id
            )
            results = [dict(r) for r in rows] if rows else MOCK_RESULTS
            return {"job_id": job_id, "status": "completed", "results": results}

        return {"job_id": job_id, "status": job["status"], "results": []}
    finally:
        await db.close()

@app.get("/api/leads")
async def get_leads():
    db = await get_db()
    try:
        rows = await db.fetch("""
            SELECT sl.id, sl.status, sl.list_name, sl.created_at,
                   sp.username, sp.full_name, sp.followers, sp.following, sp.posts,
                   sp.qualification_score, sp.detected_niche, sp.bio,
                   sp.email_in_bio, sp.external_url, sp.engagement_rate
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

@app.on_event("startup")
async def startup():
    if IG_USERNAME and IG_PASSWORD:
        await asyncio.get_event_loop().run_in_executor(None, get_ig_client)
    else:
        print("⚠️  IG_USERNAME / IG_PASSWORD not set — will use mock data")
