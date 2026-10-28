"""
Arthenthic Mobile Backend Server
FastAPI v1 API Implementation
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from server.routes.auth import router as auth_router
from server.routes.verify import router as verify_router
from server.routes.captures import router as captures_router
from server.routes.genesis import router as genesis_router
from server.crypto.attestation import CHAIN_ID, VERIFYING_CONTRACT
from server.ml.embedder import EXTRACTOR_VERSION
from server.ml.similarity import DEFAULT_MIN_SIMILARITY_BPS

app = FastAPI(
    title="Arthentic Authentication Engine",
    description="Backend API for iPhone LiDAR + Canvas Fingerprint and NFC Verification",
    version="1.0.0"
)

# Enable CORS for Flutter web / mobile network testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register route modules
app.include_router(auth_router)
app.include_router(verify_router)
app.include_router(captures_router)
app.include_router(genesis_router)

@app.get("/")
def root():
    return {"status": "ok", "service": "Arthentic Backend", "version": "1.0.0"}

@app.get("/v1/config")
def get_config():
    """
    Public configuration endpoint.
    Provides extractor version, threshold, chain ID, and contract addresses.
    """
    return {
        "extractorVersion": EXTRACTOR_VERSION,
        "minSimilarityBps": DEFAULT_MIN_SIMILARITY_BPS,
        "minSimilarityPercent": DEFAULT_MIN_SIMILARITY_BPS / 100.0,
        "chainId": CHAIN_ID,
        "contracts": {
            "verifyingContract": VERIFYING_CONTRACT,
            "arthenticNFT": "0x5FbDB2315678afecb367f032d93F642f64180aa3"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.main.py:app", host="0.0.0.0", port=8000, reload=True)

