import json
import os
from pydantic import BaseModel
from typing import Optional, List
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_FILE = "database.json"

if not os.path.exists(DB_FILE):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump({"users": {}, "wishes": [], "archive": []}, f, ensure_ascii=False, indent=4)

def read_db():
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"users": {}, "wishes": [], "archive": []}

def write_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

class AuthRequest(BaseModel):
    type: str
    is_anon: bool
    password: str
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None

class WishCreateRequest(BaseModel):
    uid: str
    title: str
    items: List[str]

class SendGiftRequest(BaseModel):
    wid: str
    item_index: int
    sponsor_name: str
    company_photo: str

class ConfirmGiftRequest(BaseModel):
    wid: str
    item_index: int
    user_photo: str

@app.post("/api/auth")
def authenticate_user(req: AuthRequest):
    db = read_db()
    
    if not req.password or len(req.password.strip()) < 4:
        raise HTTPException(status_code=400, detail="Пароль должен быть не менее 4 символов")

    if req.type == "user":
        f_name = req.firstname or "User"
        l_name = req.lastname or "Unknown"
        uid = f"u_{f_name}_{l_name}".lower().replace(" ", "_")
        display_name = f"{f_name} {l_name}"
    else:
        c_name = req.company_name or "Company"
        uid = f"c_{c_name}".lower().replace(" ", "_")
        display_name = c_name

    if uid in db["users"]:
        if db["users"][uid].get("password") != req.password:
            raise HTTPException(status_code=400, detail="Неверный пароль для этого аккаунта!")
        return db["users"][uid]
    
    db["users"][uid] = {
        "uid": uid,
        "type": req.type,
        "display_name": display_name,
        "password": req.password,
        "is_anon": req.is_anon,
        "phone": req.phone if req.type == "user" else "Не указан",
        "has_active_wish": False,
        "help_count": 0
    }
    write_db(db)
    return db["users"][uid]

@app.get("/api/wishes")
def get_wishes():
    db = read_db()
    active_wishes = db.get("wishes", [])
    for wish in active_wishes:
        author_user = db["users"].get(wish["author_uid"])
        if author_user:
            wish["author_phone"] = author_user.get("phone", "+")
        else:
            wish["author_phone"] = "+"
    return {"active": active_wishes, "archive": db.get("archive", [])}

@app.get("/api/leaders")
def get_leaders():
    db = read_db()
    users = list(db.get("users", {}).values())
    sorted_users = sorted(users, key=lambda x: x.get("help_count", 0), reverse=True)
    return sorted_users[:3]

@app.post("/api/wishes/create")
def create_wish(req: WishCreateRequest):
    db = read_db()
    user = db["users"].get(req.uid)
    if not user:
        return {"status": "error", "message": "Пользователь не найден"}

    items_structure = []
    for i in req.items:
        if i.strip():
            items_structure.append({
                "name": i.strip(),
                "status": "active",
                "sponsor": None,
                "company_photo": None,
                "user_photo": None
            })

    new_wish = {
        "wid": f"w_{len(db.get('wishes', [])) + len(db.get('archive', [])) + 1}",
        "author_uid": req.uid,
        "author": "Аноним" if user["is_anon"] else user["display_name"],
        "title": req.title,
        "items": items_structure
    }
    db["wishes"].append(new_wish)
    db["users"][req.uid]["has_active_wish"] = True
    write_db(db)
    return {"status": "success"}

@app.post("/api/wishes/send_gift")
def send_gift(req: SendGiftRequest):
    db = read_db()
    for wish in db.get("wishes", []):
        if wish["wid"] == req.wid:
            item = wish["items"][req.item_index]
            item["status"] = "sent"
            item["sponsor"] = req.sponsor_name
            item["company_photo"] = req.company_photo
            write_db(db)
            return {"status": "success"}
    return {"status": "error", "message": "Сбор не найден"}

@app.post("/api/wishes/confirm_gift")
def confirm_gift(req: ConfirmGiftRequest):
    db = read_db()
    wish_to_archive = None
    wishes = db.get("wishes", [])

    for idx, wish in enumerate(wishes):
        if wish["wid"] == req.wid:
            item = wish["items"][req.item_index]
            item["status"] = "confirmed"
            item["user_photo"] = req.user_photo
            
            sponsor_uid = f"c_{item['sponsor']}".lower().replace(" ", "_")
            if sponsor_uid not in db["users"]:
                sponsor_uid = f"u_{item['sponsor']}".lower().replace(" ", "_")
                
            if sponsor_uid in db["users"]:
                db["users"][sponsor_uid]["help_count"] += 1

            all_done = all(i["status"] == "confirmed" for i in wish["items"])
            if all_done:
                wish_to_archive = wish
                author_uid = wish["author_uid"]
                if author_uid in db["users"]:
                    db["users"][author_uid]["has_active_wish"] = False
                wishes.pop(idx)
                break

    if wish_to_archive:
        if "archive" not in db:
            db["archive"] = []
        db["archive"].append(wish_to_archive)
        write_db(db)
        return {"status": "success", "archive": True}
        
    write_db(db)
    return {"status": "success", "archive": False}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)