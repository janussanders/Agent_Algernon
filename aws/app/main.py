import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from config import ENVIRONMENT, PORT, API_SETTINGS
# ... other imports ...

app = FastAPI(
    title="Algernon",
    description="Algernon RAG API",
    version="1.0.0",
    docs_url=API_SETTINGS[ENVIRONMENT]["docs_url"],
    redoc_url=API_SETTINGS[ENVIRONMENT]["redoc_url"]
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins in dev, could be restricted in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ... rest of your existing routes and code ...

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        reload=False
    ) 