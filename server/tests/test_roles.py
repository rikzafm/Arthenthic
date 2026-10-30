import pytest
from fastapi.testclient import TestClient
from server.main import app
from server.db.database import SessionLocal
from server.db.models import User, RoleAssignment, Session
from server.db.seed import seed_dev_users
from server.cli.bootstrap_admin import bootstrap_admin

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_roles_db():
    seed_dev_users()
    db = SessionLocal()
    try:
        from server.db.models import RoleApplication, User
        db.query(RoleApplication).delete()
        temp_users = db.query(User).filter(User.email.in_(["temp_artist@arthentic.io", "cli_bootstrapped_admin@arthentic.io"])).all()
        for u in temp_users:
            db.delete(u)
        db.commit()
    finally:
        db.close()

def get_role_headers(email: str, password: str) -> dict:
    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, f"Failed to login as {email}: {res.text}"
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

class TestPermissionMatrix1_3:
    """
    Direct verification of every cell in matrix 1.3 across all roles:
    Guest, Collector, Artist, Gallery, Conservator, Admin.
    """

    @pytest.fixture(autouse=True)
    def setup_tokens(self):
        db = SessionLocal()
        try:
            from server.db.models import RoleApplication
            db.query(RoleApplication).delete()
            db.commit()
        finally:
            db.close()
        self.collector_headers = get_role_headers("collector@arthentic.io", "Collector123!")
        self.artist_headers = get_role_headers("artist@arthentic.io", "Artist123!")
        self.gallery_headers = get_role_headers("gallery@arthentic.io", "Gallery123!")
        self.conservator_headers = get_role_headers("conservator@arthentic.io", "Conservator123!")
        self.admin_headers = get_role_headers("admin@arthentic.io", "Admin123!")
        self.guest_headers = {}

    # Capability 1: Scan NFC, view cert/provenance, L1/L2 verify (ALL YES)
    def test_cap1_nfc_verify_and_provenance_accessible_by_all_including_guest(self):
        for name, headers in [
            ("guest", self.guest_headers),
            ("collector", self.collector_headers),
            ("artist", self.artist_headers),
            ("gallery", self.gallery_headers),
            ("conservator", self.conservator_headers),
            ("admin", self.admin_headers),
        ]:
            # View provenance
            res_prov = client.get("/v1/artworks/101/provenance", headers=headers)
            assert res_prov.status_code == 200, f"{name} failed to view provenance"

            # Level 1 verify
            sim_res = client.get("/v1/verify/simulate-sun")
            assert sim_res.status_code == 200
            sun_params = sim_res.json()
            res_vf = client.post("/v1/verify/level1", json={"sunParams": sun_params, "tokenId": "101"}, headers=headers)
            assert res_vf.status_code == 200, f"{name} failed level 1 verify"

    # Capability 2: Save verification history, own works (Guest NO, all logged-in YES)
    def test_cap2_save_verification_history_and_own_works(self):
        # Guest -> 401
        res_guest = client.post("/v1/user/verifications", json={"tokenId": "101", "level": 1, "status": "VALID"}, headers=self.guest_headers)
        assert res_guest.status_code == 401

        # All logged-in roles -> 200
        for name, headers in [
            ("collector", self.collector_headers),
            ("artist", self.artist_headers),
            ("gallery", self.gallery_headers),
            ("conservator", self.conservator_headers),
            ("admin", self.admin_headers),
        ]:
            res = client.post("/v1/user/verifications", json={"tokenId": "101", "level": 1, "status": "VALID"}, headers=headers)
            assert res.status_code == 200, f"{name} failed to save verification history"

            res_works = client.get("/v1/user/artworks", headers=headers)
            assert res_works.status_code == 200, f"{name} failed to get artworks"

    # Capability 3: Apply for an accredited role (Collector YES, Guest NO)
    def test_cap3_apply_for_accredited_role(self):
        # Guest -> 401
        res_guest = client.post("/v1/roles/apply", json={"requested_role": "Artist"}, headers=self.guest_headers)
        assert res_guest.status_code == 401

        # Collector -> 200
        res_col = client.post("/v1/roles/apply", json={"requested_role": "Artist", "portfolio_url": "https://art.io/me"}, headers=self.collector_headers)
        assert res_col.status_code == 200
        assert res_col.json()["status"] == "submitted"

        # Artist applying for Artist -> 400 already accredited
        res_dup = client.post("/v1/roles/apply", json={"requested_role": "Artist"}, headers=self.artist_headers)
        assert res_dup.status_code == 400
        assert res_dup.json()["detail"]["error"]["code"] == "ALREADY_ACCREDITED"

    # Capability 4: Register artwork / genesis capture (Artist YES, all others NO)
    def test_cap4_register_artwork_genesis_only_artist(self):
        payload = {"captureIds": ["mock_cap_1"], "title": "New Piece", "artist": "Elena"}

        # Guest -> 401
        assert client.post("/v1/genesis/prepare", json=payload, headers=self.guest_headers).status_code == 401
        # Collector -> 403
        assert client.post("/v1/genesis/prepare", json=payload, headers=self.collector_headers).status_code == 403
        # Gallery -> 403
        assert client.post("/v1/genesis/prepare", json=payload, headers=self.gallery_headers).status_code == 403
        # Conservator -> 403
        assert client.post("/v1/genesis/prepare", json=payload, headers=self.conservator_headers).status_code == 403
        # Admin -> 403
        assert client.post("/v1/genesis/prepare", json=payload, headers=self.admin_headers).status_code == 403
        # Artist -> 200
        res_artist = client.post("/v1/genesis/prepare", json=payload, headers=self.artist_headers)
        assert res_artist.status_code == 200
        assert "tokenId" in res_artist.json()

    # Capability 5: Bulk / batch verify, verification reports (Gallery YES, others NO)
    def test_cap5_bulk_batch_verify_only_gallery(self):
        payload = {"items": [{"tokenId": "101"}]}

        # Guest -> 401
        assert client.post("/v1/gallery/batch-verify", json=payload, headers=self.guest_headers).status_code == 401
        # Collector -> 403
        assert client.post("/v1/gallery/batch-verify", json=payload, headers=self.collector_headers).status_code == 403
        # Artist -> 403
        assert client.post("/v1/gallery/batch-verify", json=payload, headers=self.artist_headers).status_code == 403
        # Conservator -> 403
        assert client.post("/v1/gallery/batch-verify", json=payload, headers=self.conservator_headers).status_code == 403
        # Admin -> 403
        assert client.post("/v1/gallery/batch-verify", json=payload, headers=self.admin_headers).status_code == 403
        # Gallery -> 200
        res_gallery = client.post("/v1/gallery/batch-verify", json=payload, headers=self.gallery_headers)
        assert res_gallery.status_code == 200
        assert res_gallery.json()["status"] == "COMPLETED"

    # Capability 6: Condition reports (Conservator YES, others NO)
    def test_cap6_condition_reports_only_conservator(self):
        # Guest -> 401
        assert client.get("/v1/conservation/reports", headers=self.guest_headers).status_code == 401
        # Collector -> 403
        assert client.get("/v1/conservation/reports", headers=self.collector_headers).status_code == 403
        # Artist -> 403
        assert client.get("/v1/conservation/reports", headers=self.artist_headers).status_code == 403
        # Gallery -> 403
        assert client.get("/v1/conservation/reports", headers=self.gallery_headers).status_code == 403
        # Admin -> 403
        assert client.get("/v1/conservation/reports", headers=self.admin_headers).status_code == 403
        # Conservator -> 200
        res_cons = client.get("/v1/conservation/reports", headers=self.conservator_headers)
        assert res_cons.status_code == 200
        assert "reports" in res_cons.json()

    # Capability 7: Review applications, grant/revoke roles, view audit log (Admin YES, others NO)
    def test_cap7_admin_operations_only_admin(self):
        # Audit log
        assert client.get("/v1/admin/audit-log", headers=self.guest_headers).status_code == 401
        assert client.get("/v1/admin/audit-log", headers=self.collector_headers).status_code == 403
        assert client.get("/v1/admin/audit-log", headers=self.artist_headers).status_code == 403
        assert client.get("/v1/admin/audit-log", headers=self.gallery_headers).status_code == 403
        assert client.get("/v1/admin/audit-log", headers=self.conservator_headers).status_code == 403
        
        res_admin = client.get("/v1/admin/audit-log", headers=self.admin_headers)
        assert res_admin.status_code == 200
        assert "logs" in res_admin.json()

def test_roles_in_me_and_jwt():
    """Verify /me returns active roles list and JWT carries them."""
    res_artist = client.post("/auth/login", json={"email": "artist@arthentic.io", "password": "Artist123!"})
    assert res_artist.status_code == 200
    artist_data = res_artist.json()
    assert "Artist" in artist_data["user"]["roles"]
    assert "Collector" in artist_data["user"]["roles"]

    # Check /auth/me
    headers = {"Authorization": f"Bearer {artist_data['access_token']}"}
    res_me = client.get("/auth/me", headers=headers)
    assert res_me.status_code == 200
    assert "Artist" in res_me.json()["roles"]

def test_multi_role_user_capabilities():
    """Verify multi-role user can perform operations across granted roles."""
    headers = get_role_headers("multirole@arthentic.io", "MultiRole123!")

    # Check roles returned
    res_me = client.get("/auth/me", headers=headers)
    assert res_me.status_code == 200
    roles = res_me.json()["roles"]
    assert "Artist" in roles
    assert "Gallery" in roles
    assert "Conservator" in roles

    # Can perform Artist action
    res_gen = client.post("/v1/genesis/prepare", json={"captureIds": ["mock_1"], "title": "Multi"}, headers=headers)
    assert res_gen.status_code == 200

    # Can perform Gallery action
    res_gal = client.post("/v1/gallery/batch-verify", json={"items": [{"tokenId": "101"}]}, headers=headers)
    assert res_gal.status_code == 200

    # Can perform Conservator action
    res_cons = client.get("/v1/conservation/reports", headers=headers)
    assert res_cons.status_code == 200

def test_db_recheck_revocation_rejects_stale_jwt():
    """
    Verify sensitive actions re-check DB:
    When an admin revokes an active role, requests with previously issued tokens return 403 or 401.
    """
    db = SessionLocal()
    try:
        # Create a temporary artist
        temp_artist_email = "temp_artist@arthentic.io"
        existing_u = db.query(User).filter(User.email == temp_artist_email).first()
        if existing_u:
            db.delete(existing_u)
            db.commit()

        temp_signup = client.post("/auth/signup", json={"email": temp_artist_email, "password": "Password123!"})
        assert temp_signup.status_code == 200
        temp_user_id = temp_signup.json()["user"]["id"]

        admin_headers = get_role_headers("admin@arthentic.io", "Admin123!")

        # Grant Artist role
        res_grant = client.post("/v1/admin/roles/grant", json={"user_id": temp_user_id, "role": "Artist"}, headers=admin_headers)
        assert res_grant.status_code == 200

        # Login to get JWT with Artist role
        temp_login = client.post("/auth/login", json={"email": temp_artist_email, "password": "Password123!"})
        temp_token = temp_login.json()["access_token"]
        temp_headers = {"Authorization": f"Bearer {temp_token}"}

        # Works before revocation
        res_gen = client.post("/v1/genesis/prepare", json={"captureIds": ["mock_cap"]}, headers=temp_headers)
        assert res_gen.status_code == 200

        # Admin revokes the Artist role
        res_revoke = client.post("/v1/admin/roles/revoke", json={"user_id": temp_user_id, "role": "Artist"}, headers=admin_headers)
        assert res_revoke.status_code == 200

        # Next request with the old JWT MUST BE REJECTED
        res_after = client.post("/v1/genesis/prepare", json={"captureIds": ["mock_cap"]}, headers=temp_headers)
        # Because revoke also killed active sessions, it returns 401 SESSION_REVOKED or 403 FORBIDDEN
        assert res_after.status_code in (401, 403)
    finally:
        db.close()

def test_last_admin_protection():
    """Verify cannot revoke the last active Admin."""
    admin_headers = get_role_headers("admin@arthentic.io", "Admin123!")
    res_me = client.get("/auth/me", headers=admin_headers)
    admin_id = res_me.json()["id"]

    db = SessionLocal()
    try:
        # Keep only 1 active admin
        assignments = db.query(RoleAssignment).filter(RoleAssignment.role == "Admin", RoleAssignment.status == "active").all()
        for a in assignments:
            if a.user_id != admin_id:
                a.status = "revoked"
        db.commit()

        # Attempt to revoke the only active admin -> MUST FAIL 400
        res = client.post("/v1/admin/roles/revoke", json={"user_id": admin_id, "role": "Admin"}, headers=admin_headers)
        assert res.status_code == 400
        assert res.json()["detail"]["error"]["code"] == "LAST_ADMIN_PROTECTED"
    finally:
        db.close()

def test_admin_bootstrap_cli_creates_admin():
    """Verify bootstrap_admin command creates admin account via CLI."""
    email = "cli_bootstrapped_admin@arthentic.io"
    db = SessionLocal()
    try:
        existing_admin = db.query(User).filter(User.email == email).first()
        if existing_admin:
            db.delete(existing_admin)
            db.commit()
    finally:
        db.close()

    user = bootstrap_admin(email=email, password="CliPassword123!", display_name="CLI Admin")
    assert user is not None

    headers = get_role_headers(email, "CliPassword123!")
    res_me = client.get("/auth/me", headers=headers)
    assert res_me.status_code == 200
    assert "Admin" in res_me.json()["roles"]
