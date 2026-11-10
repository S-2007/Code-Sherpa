from contextlib import asynccontextmanager
import logging

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

# Load your environment variables for OpenRouter and Chroma
load_dotenv()

# Import your separated routers
from app.api.sherpachat import router as chat_router
from app.api.gitclone import router as clone_router
from app.engine_rag.vector_db import ChromaCloudDB
from app.engine_rag.retriever import GraphRetriever

retriever: GraphRetriever = None

logger = logging.getLogger(__name__)

# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     # Startup logic
#     yield
#     # Shutdown logic: wipe out the temporary vector data
#     logger.info("Server is shutting down. Clearing ChromaDB collections...")
#     try:
#         db = ChromaCloudDB(collection_name="codesherpa_real_repo")
#         db.clear_collection()
#     except Exception as e:
#         logger.error(f"Error while cleaning collection 'codesherpa_real_repo': {e}")
        
#     try:
#         db_ast = ChromaCloudDB(collection_name="codesherpa_ast")
#         db_ast.clear_collection()
#     except Exception as e:
#         logger.error(f"Error while cleaning collection 'codesherpa_ast': {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global retriever
    try:
        db = ChromaCloudDB(collection_name="codesherpa_real_repo")
        
        # Clear any stale data from previous session (crash recovery)
        db.clear_collection()
        logger.info("Cleared stale collection on startup.")
        
        retriever = GraphRetriever(db)
        logger.info("Connected to Chroma Cloud successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize on startup: {e}")
        retriever = None

    yield

    # Clean shutdown
    logger.info("Server shutting down. Clearing collections...")
    try:
        db = ChromaCloudDB(collection_name="codesherpa_real_repo")
        db.clear_collection()
    except Exception as e:
        logger.error(f"Error clearing collection on shutdown: {e}")

app = FastAPI(title="CODE Sherpa API", version="1.0", lifespan=lifespan)

# -------------------------------------------------------------------
# CORS — Allow the Vite frontend (and any origin in dev) to talk to us
# -------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://code-sherpa.vercel.app",
    ],
    allow_origin_regex=r"https://.*(\.vercel\.app|\.onrender\.com)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Plug the routes into the web server
app.include_router(chat_router, prefix="/api/v1/sherpachat", tags=["Conversational AI"])
app.include_router(clone_router, prefix="/api/v1/ingest", tags=["Repository Processing"])

# -------------------------------------------------------------------
# Serve Frontend Static Assets if available (Single Web Service mode)
# -------------------------------------------------------------------
possible_dist_dirs = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend", "dist"),
    os.path.join(os.getcwd(), "frontend", "dist"),
    os.path.join(os.getcwd(), "dist"),
]

frontend_dist = next((d for d in possible_dist_dirs if os.path.isdir(d) and os.path.exists(os.path.join(d, "index.html"))), None)

if frontend_dist:
    logger.info(f"Serving frontend static build from: {frontend_dist}")
    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if full_path.startswith("api/"):
            return {"error": "API route not found"}
        file_path = os.path.join(frontend_dist, full_path)
        if full_path and os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dist, "index.html"))
else:
    @app.get("/")
    async def health_check():
        return {"status": "online", "message": "CODE Sherpa Web Server is running!"}