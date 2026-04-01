from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
from datetime import datetime
from typing import Optional

# Initialize FastAPI app
app = FastAPI(title="CleanSpace API")

# Enable CORS 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"], 
)

# --- SQL DATABASE SETUP ---
def init_db():
    # Using 'with' context manager ensures the connection closes safely
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (email TEXT PRIMARY KEY, name TEXT, block TEXT, room TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS requests 
                     (req_id TEXT PRIMARY KEY, email TEXT, reason TEXT, is_emergency BOOLEAN, 
                      status TEXT, pool TEXT, staff_assigned TEXT, time_req TEXT, time_done TEXT)''')
        conn.commit()

init_db()

# --- HOSTEL STAFF (20 Workers) ---
staff_db = {
    "m_01": "Suresh", "m_02": "Ramesh", "m_03": "Raj", "m_04": "Karthik", "m_05": "Vijay",
    "m_06": "Ajith", "m_07": "Kumar", "m_08": "Arun", "m_09": "Vikram", "m_10": "Surya",
    "f_01": "Priya", "f_02": "Lakshmi", "f_03": "Anjali", "f_04": "Kavya", "f_05": "Sneha",
    "f_06": "Divya", "f_07": "Swathi", "f_08": "Meena", "f_09": "Roopa", "f_10": "Bhavani"
}

mens_blocks = ["Q", "P", "M", "N", "S", "T"]
womens_blocks = ["G", "J", "H"]

# --- DATA MODELS ---
class UserLogin(BaseModel):
    email: str
    name: Optional[str] = None
    block: Optional[str] = None
    room: Optional[str] = None

class RequestModel(BaseModel):
    email: str
    reason: str
    is_emergency: bool

# --- API ENDPOINTS ---

@app.post("/auth/student")
def student_auth(user: UserLogin):
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email=?", (user.email,))
        existing_user = c.fetchone()
        
        if existing_user:
            return {
                "status": "returning", 
                "data": {"email": existing_user[0], "name": existing_user[1], "block": existing_user[2], "room": existing_user[3]}
            }
        else:
            if not user.name or not user.block or not user.room:
                raise HTTPException(status_code=400, detail="New user detected. Please provide name, block, and room.")
            
            c.execute("INSERT INTO users VALUES (?, ?, ?, ?)", (user.email, user.name, user.block, user.room))
            conn.commit()
            
            return {
                "status": "new", 
                "data": {"email": user.email, "name": user.name, "block": user.block, "room": user.room}
            }

@app.post("/request")
def make_request(req: RequestModel):
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        c.execute("SELECT block FROM users WHERE email=?", (req.email,))
        user_data = c.fetchone()
        
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found.")
        
        block = user_data[0]
        # Added .upper() to prevent case-sensitivity issues
        pool = "MENS_POOL" if block.upper() in mens_blocks else "WOMENS_POOL"
        
        # Added %f for microseconds to prevent primary key collision (duplicate IDs)
        req_id = f"REQ_{datetime.now().strftime('%H%M%S%f')}"
        time_req = datetime.now().strftime("%I:%M %p")
        
        c.execute("INSERT INTO requests VALUES (?, ?, ?, ?, 'PENDING', ?, NULL, ?, NULL)", 
                  (req_id, req.email, req.reason, req.is_emergency, pool, time_req))
        conn.commit()
        
    return {"req_id": req_id, "status": "Added to Queue"}

@app.get("/student/history/{email}")
def get_student_history(email: str):
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        c.execute("""
            SELECT req_id, reason, status, time_req, time_done 
            FROM requests 
            WHERE email=? ORDER BY req_id DESC
        """, (email,))
        rows = c.fetchall()
        
    return [{"req_id": r[0], "reason": r[1], "status": r[2], "time_req": r[3], "time_done": r[4]} for r in rows]

@app.get("/staff/pool/{staff_id}")
def get_pool(staff_id: str):
    if staff_id not in staff_db:
        raise HTTPException(status_code=400, detail="Invalid Staff ID")

    pool = "MENS_POOL" if staff_id.startswith("m_") else "WOMENS_POOL"
    
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        c.execute("""
            SELECT r.req_id, u.room, u.block, r.reason, r.is_emergency, r.status 
            FROM requests r JOIN users u ON r.email = u.email 
            WHERE ((r.pool=? AND r.staff_assigned IS NULL) OR r.staff_assigned=?)
            AND r.status != 'COMPLETED'
        """, (pool, staff_id))
        rows = c.fetchall()
        
    return [{"req_id": r[0], "room": r[1], "block": r[2], "reason": r[3], "emergency": r[4], "status": r[5]} for r in rows]

@app.post("/staff/accept/{req_id}/{staff_id}")
def accept_job(req_id: str, staff_id: str):
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        c.execute("UPDATE requests SET status='ACCEPTED', staff_assigned=? WHERE req_id=?", (staff_id, req_id))
        conn.commit()
        
    return {"message": "Job Accepted"}

@app.post("/staff/pass/{req_id}")
def pass_job(req_id: str):
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        c.execute("UPDATE requests SET status='PENDING', staff_assigned=NULL WHERE req_id=?", (req_id,))
        conn.commit()
        
    return {"message": "Job Passed back to Queue"}

@app.post("/complete/{req_id}")
def complete_job(req_id: str):
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        time_done = datetime.now().strftime("%I:%M %p")
        c.execute("UPDATE requests SET status='COMPLETED', time_done=? WHERE req_id=?", (time_done, req_id))
        conn.commit()
        
    return {"message": "Job Completed!", "time": time_done}