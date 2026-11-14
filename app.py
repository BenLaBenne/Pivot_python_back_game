"""PIVOT Python backend: REST API, authentication and minimal playable game API."""
import os, re, secrets, string
from datetime import datetime, timedelta, timezone
from functools import wraps

import bcrypt
import jwt
import psycopg
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO
from psycopg.rows import dict_row

from game import apply_action, new_game, public_state

load_dotenv()
app = Flask(__name__, static_folder="static")
app.config["SECRET_KEY"] = os.getenv("JWT_SECRET", "local-development-only-change-me")
socketio = SocketIO(app, cors_allowed_origins="*")
DATABASE_URL = os.getenv("DATABASE_URL")
GAMES = {}  # Ephemeral: active games are lost when the service restarts.

def db():
    if not DATABASE_URL: raise RuntimeError("DATABASE_URL is not configured")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=8)

def initialize_database():
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            id BIGSERIAL PRIMARY KEY, pseudo VARCHAR(24) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")

def token_for(user):
    return jwt.encode({"sub":str(user["id"]),"pseudo":user["pseudo"],"exp":datetime.now(timezone.utc)+timedelta(days=7)}, app.config["SECRET_KEY"], algorithm="HS256")

def current_user():
    header=request.headers.get("Authorization", "")
    if not header.startswith("Bearer "): return None
    try:
        claims=jwt.decode(header[7:], app.config["SECRET_KEY"], algorithms=["HS256"])
        with db() as conn: return conn.execute("SELECT id,pseudo,created_at FROM users WHERE id=%s",(claims["sub"],)).fetchone()
    except (jwt.PyJWTError, psycopg.Error, RuntimeError): return None

def auth_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        user=current_user()
        if not user: return jsonify(error="Authentification requise."),401
        return fn(user,*args,**kwargs)
    return wrapped

@app.get("/api/health")
def health():
    try:
        with db() as conn: conn.execute("SELECT 1")
        return jsonify(ok=True, database="ready")
    except Exception as exc:
        return jsonify(ok=False, database="unavailable", error=str(exc)),503

@app.post("/api/auth/signup")
def signup():
    data=request.get_json(silent=True) or {}; pseudo=data.get("pseudo","").strip(); password=data.get("password","")
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,24}",pseudo): return jsonify(error="Pseudo: 3-24 caractères (lettres, chiffres, _ ou -)."),400
    if not isinstance(password,str) or len(password)<8: return jsonify(error="Mot de passe: 8 caractères minimum."),400
    hashed=bcrypt.hashpw(password.encode(),bcrypt.gensalt()).decode()
    try:
        with db() as conn: user=conn.execute("INSERT INTO users(pseudo,password_hash) VALUES(%s,%s) RETURNING id,pseudo,created_at",(pseudo,hashed)).fetchone()
    except psycopg.errors.UniqueViolation: return jsonify(error="Ce pseudo est déjà utilisé."),409
    return jsonify(token=token_for(user),user={"id":user["id"],"pseudo":user["pseudo"]}),201

@app.post("/api/auth/login")
def login():
    data=request.get_json(silent=True) or {}; pseudo=data.get("pseudo",""); password=data.get("password","")
    with db() as conn: row=conn.execute("SELECT id,pseudo,password_hash,created_at FROM users WHERE pseudo=%s",(pseudo,)).fetchone()
    if not row or not bcrypt.checkpw(str(password).encode(),row["password_hash"].encode()): return jsonify(error="Identifiants incorrects."),401
    return jsonify(token=token_for(row),user={"id":row["id"],"pseudo":row["pseudo"]})

@app.get("/api/auth/me")
@auth_required
def me(user): return jsonify(user={"id":user["id"],"pseudo":user["pseudo"],"created_at":user["created_at"].isoformat()})

@app.post("/api/games")
@auth_required
def create_game(user):
    game_id=secrets.token_urlsafe(12)
    game=new_game({"R":user["pseudo"],"B":"Joueur 2"})
    GAMES[game_id]={"state":game,"players":{"R":user["id"],"B":None}}
    return jsonify(gameId=game_id,role="R",state=public_state(game)),201

@app.get("/api/games/<game_id>")
@auth_required
def get_game(user,game_id):
    game=GAMES.get(game_id)
    if not game: return jsonify(error="Partie introuvable."),404
    if user["id"] not in game["players"].values():
        if game["players"]["B"] is not None: return jsonify(error="Partie complète."),409
        game["players"]["B"]=user["id"]; game["state"]["noms"]["B"]=user["pseudo"]
    role="R" if game["players"]["R"]==user["id"] else "B"
    return jsonify(gameId=game_id,role=role,state=public_state(game["state"]))

@app.post("/api/games/<game_id>/actions")
@auth_required
def game_action(user,game_id):
    item=GAMES.get(game_id)
    if not item: return jsonify(error="Partie introuvable."),404
    roles=[role for role,uid in item["players"].items() if uid==user["id"]]
    if not roles: return jsonify(error="Vous ne participez pas à cette partie."),403
    result=apply_action(item["state"],roles[0],request.get_json(silent=True) or {})
    if not result["ok"]: return jsonify(result),400
    return jsonify(result,state=public_state(item["state"]))

@app.get("/")
def home():
    if os.path.isfile(os.path.join(app.static_folder,"index.html")): return send_from_directory(app.static_folder,"index.html")
    return jsonify(name="PIVOT Python backend",docs="See README.md",health="/api/health")

if __name__ == "__main__":
    initialize_database()
    socketio.run(app,host="0.0.0.0",port=int(os.getenv("PORT","5000")),debug=False)
