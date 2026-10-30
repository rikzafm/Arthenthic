"""
server/tests/test_wave2_milestone4.py
TDD Test Suite for Wave 2 Milestone 4 (Containerized Stack, CI/CD & E2E Staging - Phase QA & Ops):
1. docker-compose.yml & Dockerfile orchestration for postgres:16-alpine, redis:7-alpine, anvil (Deploy.s.sol), and server (Alembic startup).
2. .github/workflows/ci.yml pipeline executing forge test, pytest, flutter test, and flutter build web.
3. Redis 7 Lua script & REDIS_URL client support in redis_hotpath.py + /health & /v1/health readiness endpoints.
4. scripts/verify_full_stack.py end-to-end 6-layer architecture smoke runner verification.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from server.main import app
from server.db.redis_hotpath import InMemoryRedisHotPath, redis_hotpath

REPO_ROOT = Path(__file__).resolve().parents[2]
client = TestClient(app)


def test_docker_compose_and_dockerfile_orchestration_spec():
    """
    Verifies docker-compose.yml and Dockerfile exist and orchestrate:
    - postgres:16-alpine
    - redis:7-alpine
    - anvil (ghcr.io/foundry-rs/foundry auto-deploying Deploy.s.sol)
    - server (Dockerfile + Alembic upgrade head startup)
    """
    compose_path = REPO_ROOT / "docker-compose.yml"
    dockerfile_path = REPO_ROOT / "Dockerfile"
    entrypoint_path = REPO_ROOT / "scripts" / "docker_entrypoint.sh"

    assert compose_path.exists(), "docker-compose.yml must exist at repository root"
    assert dockerfile_path.exists(), "Dockerfile must exist at repository root"
    assert entrypoint_path.exists(), "scripts/docker_entrypoint.sh must exist"

    compose_text = compose_path.read_text()
    assert "postgres:16-alpine" in compose_text
    assert "redis:7-alpine" in compose_text
    assert "ghcr.io/foundry-rs/foundry" in compose_text
    assert "Deploy.s.sol" in compose_text
    assert "server:" in compose_text
    assert "DATABASE_URL" in compose_text
    assert "REDIS_URL" in compose_text

    entrypoint_text = entrypoint_path.read_text()
    assert "alembic upgrade head" in entrypoint_text
    assert "uvicorn" in entrypoint_text


def test_github_actions_ci_workflow_spec():
    """
    Verifies .github/workflows/ci.yml exists and executes:
    - forge test (Pillar 3: Solidity Smart Contracts)
    - pytest (Pillar 2: FastAPI Backend Monolith)
    - flutter test & flutter build web (Pillar 1: Unified iOS + Web Client)
    """
    ci_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert ci_path.exists(), ".github/workflows/ci.yml must exist"

    ci_text = ci_path.read_text()
    assert "forge test" in ci_text
    assert "pytest" in ci_text
    assert "flutter test" in ci_text
    assert "flutter build web" in ci_text
    assert "verify_full_stack.py" in ci_text


def test_redis7_lua_hotpath_and_health_endpoint():
    """
    Verifies:
    1. redis_hotpath defines atomic SUN_COUNTER_LUA_SCRIPT and delegates to live Redis 7
       client when attached, with seamless fallback to in-memory store.
    2. GET /health and GET /v1/health return 200 OK with database, redis, chain_client,
       and paymaster readiness telemetry.
    """
    assert hasattr(redis_hotpath, "SUN_COUNTER_LUA_SCRIPT")
    assert "tonumber" in redis_hotpath.SUN_COUNTER_LUA_SCRIPT

    mock_redis = MagicMock()
    mock_redis.eval.return_value = 1
    mock_redis.set.return_value = True
    mock_redis.incr.return_value = 1

    engine = InMemoryRedisHotPath(redis_client=mock_redis)
    ok, err = engine.check_and_update_sun_counter("04A1B2C3D4E580", 42)
    assert ok is True
    assert err is None
    assert mock_redis.eval.called

    nonce_ok = engine.set_attestation_nonce("0xnonce_m4_test", ttl_seconds=120)
    assert nonce_ok is True
    assert mock_redis.set.called

    # Health check endpoints
    for path in ("/health", "/v1/health"):
        resp = client.get(path)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "checks" in body
        assert body["checks"]["database"] == "ok"
        assert body["checks"]["redis"] in ("ok", "in_memory_fallback")
        assert "chain_client" in body["checks"]
        assert "paymaster" in body["checks"]


def test_verify_full_stack_e2e_smoke_script():
    """
    Executes scripts/verify_full_stack.py end-to-end smoke runner and verifies all
    6 architecture layers pass their smoke assertions.
    """
    smoke_script_path = REPO_ROOT / "scripts" / "verify_full_stack.py"
    assert smoke_script_path.exists(), "scripts/verify_full_stack.py must exist"

    from scripts.verify_full_stack import run_full_stack_smoke_verification

    report = run_full_stack_smoke_verification()
    assert report["all_passed"] is True
    steps = report["steps"]
    assert steps["layer1_contracts_and_abis"]["passed"] is True
    assert steps["layer2_orm_and_redis_hotpath"]["passed"] is True
    assert steps["layer3_genesis_coa_and_storage"]["passed"] is True
    assert steps["layer3_nfc_sun_and_optical_verify"]["passed"] is True
    assert steps["layer1_3_escrow_split_and_c12_refund"]["passed"] is True
    assert steps["layer1_5_restoration_and_f05_chip_swap"]["passed"] is True
    assert steps["layer4_5_indexer_merkle_and_paymaster"]["passed"] is True
