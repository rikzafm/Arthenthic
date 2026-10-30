"""
Arthenthic Mobile Backend Server
FastAPI v1 API Implementation
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
import os

from server.routes.auth import router as auth_router
from server.routes.verify import router as verify_router
from server.routes.captures import router as captures_router
from server.routes.genesis import router as genesis_router
from server.routes.gallery import router as gallery_router
from server.routes.admin import router as admin_router
from server.routes.roles import router as roles_router
from server.routes.marketplace import router as marketplace_router
from server.routes.conservation import router as conservation_router
from server.db.database import Base, engine
from server.crypto.attestation import CHAIN_ID, VERIFYING_CONTRACT
from server.ml.embedder import EXTRACTOR_VERSION
from server.ml.similarity import DEFAULT_MIN_SIMILARITY_BPS

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan handler: safe schema initialization decoupled from module import.
    In development and testing, automatically creates tables when AUTO_CREATE_TABLES is enabled.
    In production, migrations are managed via Alembic.
    """
    if os.getenv("AUTO_CREATE_TABLES", "true").lower() in ("true", "1", "yes"):
        Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(
    title="Arthentic Authentication Engine",
    description="Backend API for iPhone LiDAR + Canvas Fingerprint and NFC Verification",
    version="1.0.0",
    lifespan=lifespan,
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
app.include_router(gallery_router)
app.include_router(admin_router)
app.include_router(roles_router)
app.include_router(marketplace_router)
app.include_router(conservation_router)

os.makedirs("server/static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="server/static"), name="static")

@app.get("/")
def root():
    return {"status": "ok", "service": "Arthentic Backend", "version": "1.0.0"}


@app.get("/health")
@app.get("/v1/health")
def health_check():
    """
    Container & CI/CD readiness check across PostgreSQL/SQLite, Redis 7 hot-path,
    EVM Chain Client, and ERC-4337 Paymaster EntryPoint monitor.
    """
    from sqlalchemy import text
    from server.db.database import SessionLocal
    from server.db.redis_hotpath import redis_hotpath
    from server.node.chain_client import chain_client
    from server.paymaster.balance_monitor import balance_monitor

    db_status = "ok"
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "degraded"
    finally:
        db.close()

    pm_health = balance_monitor.check_balance_health()
    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "service": "Arthentic Modular Monolith",
        "version": "1.0.0",
        "checks": {
            "database": db_status,
            "redis": redis_hotpath.health_check(),
            "chain_client": {
                "base_chain_id": chain_client.base_chain_id,
                "l1_chain_id": chain_client.l1_chain_id,
                "arthentic_nft": chain_client.nft_address,
                "arthentic_escrow": chain_client.escrow_address,
                "merkle_anchor": chain_client.merkle_anchor_address,
            },
            "paymaster": pm_health.get("status", "ok"),
        },
    }

@app.get("/v1/config")
def get_config():
    """
    Public configuration endpoint.
    Provides extractor version, threshold, chain ID, and contract addresses.
    """
    from server.node.chain_client import chain_client
    return {
        "extractorVersion": EXTRACTOR_VERSION,
        "minSimilarityBps": DEFAULT_MIN_SIMILARITY_BPS,
        "minSimilarityPercent": DEFAULT_MIN_SIMILARITY_BPS / 100.0,
        "chainId": CHAIN_ID,
        "contracts": {
            "verifyingContract": VERIFYING_CONTRACT,
            "arthenticNFT": chain_client.nft_address,
            "arthenticEscrow": chain_client.escrow_address,
            "merkleAnchor": chain_client.merkle_anchor_address,
        }
    }

@app.get("/v1/contracts/config")
def get_contracts_config():
    """
    Returns Base Sepolia (84532) and Ethereum Sepolia (11155111) contract deployment
    manifest and function selectors for Mobile & Web clients.
    """
    from server.node.chain_client import chain_client
    return chain_client.get_contract_deployment_manifest()

@app.post("/v1/paymaster/sponsor")
async def sponsor_erc4337_user_operation(request: Request):
    """
    K-01..K-05: ERC-4337 UserOperation Paymaster Sponsorship endpoint.
    Evaluates method allow-list, per-wallet monthly quota, EntryPoint treasury balance,
    and returns signed paymasterAndData via Bundler RPC or HSM signer.
    """
    from server.paymaster.policy_engine import paymaster_engine
    body = await request.json()
    return paymaster_engine.sponsor_user_operation(
        user_op=body.get("user_op", {}),
        wallet_address=body.get("wallet_address", "0x0000000000000000000000000000000000000000"),
        method_name=body.get("method_name", "claim"),
        user_roles=body.get("user_roles", ["Collector"]),
    )

@app.get("/metrics", response_class=PlainTextResponse)
def get_prometheus_metrics():
    """
    Standard Prometheus metrics export endpoint for monitoring security indicators:
    - auth_login_successes_total / auth_login_failures_total
    - auth_refresh_successes_total / auth_refresh_failures_total
    - auth_token_reuse_events_total
    - app_lock_bypass_reports_total
    - rate_limited_requests_total
    """
    from server.auth.monitoring import monitoring
    return monitoring.get_prometheus_metrics()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=True)

