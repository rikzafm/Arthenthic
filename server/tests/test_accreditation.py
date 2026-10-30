import io
import uuid
import pytest
from fastapi.testclient import TestClient
from server.main import app
from server.db.seed import seed_dev_users
from server.auth.limiter import limiter

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    limiter.clear_all()
    seed_dev_users()
    yield
    limiter.clear_all()

@pytest.fixture(autouse=True)
def clear_rate_limits():
    limiter.clear_all()
    yield
    limiter.clear_all()

def login_and_get_auth(email: str, password: str) -> dict:
    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200
    data = res.json()
    return {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
        "user": data["user"],
    }

class TestAccreditationFlowM5:
    """
    Milestone 5 exit test:
    End-to-end apply -> approve -> role appears after token refresh.
    Role-specific feature verifications (Artist genesis, Conservator condition reports, Gallery batch verify).
    """

    def test_document_upload_endpoint(self):
        collector_auth = login_and_get_auth("collector@arthentic.io", "Collector123!")
        file_content = b"PDF Mock Portfolio and Artist Statement credentials"
        files = {"file": ("portfolio.pdf", io.BytesIO(file_content), "application/pdf")}

        res = client.post("/v1/roles/apply/upload", files=files, headers=collector_auth["headers"])
        assert res.status_code == 200
        data = res.json()
        assert "storage_key" in data
        assert "sha256" in data
        assert data["filename"] == "portfolio.pdf"
        assert data["size_bytes"] == len(file_content)

    def test_end_to_end_apply_approve_refresh_cycle(self):
        # 1. Sign up a fresh Collector
        fresh_email = f"applicant_{uuid.uuid4().hex[:8]}@arthentic.io"
        signup_res = client.post("/auth/signup", json={"email": fresh_email, "password": "ApplicantPass123!"})
        assert signup_res.status_code == 200
        signup_data = signup_res.json()
        applicant_refresh = signup_data["refresh_token"]
        applicant_headers = {"Authorization": f"Bearer {signup_data['access_token']}"}

        # Initially, applicant has ONLY Collector role
        assert signup_data["user"]["roles"] == ["Collector"]

        # Applicant cannot register artwork yet (returns 403)
        res_genesis_fail = client.post("/v1/genesis/prepare", json={"captureIds": ["mock_cid"]}, headers=applicant_headers)
        assert res_genesis_fail.status_code == 403

        # 2. Collector submits accreditation application for "Artist"
        app_payload = {
            "requested_role": "Artist",
            "portfolio_url": "https://arthentic.io/artists/new_applicant",
            "bio_or_org": "Contemporary oil on canvas painter",
            "notes": "Represented by White Cube gallery",
            "documents": [
                {
                    "storage_key": "accreditation/docs/sample_doc_1.pdf",
                    "filename": "sample_doc_1.pdf",
                    "mime": "application/pdf",
                    "sha256": "abcdef1234567890abcdef1234567890",
                }
            ],
        }
        res_apply = client.post("/v1/roles/apply", json=app_payload, headers=applicant_headers)
        assert res_apply.status_code == 200
        apply_data = res_apply.json()
        application_id = apply_data["application"]["id"]
        assert apply_data["application"]["status"] == "pending"

        # Check /my-applications lists this pending application
        res_my_apps = client.get("/v1/roles/my-applications", headers=applicant_headers)
        assert res_my_apps.status_code == 200
        my_apps = res_my_apps.json()["applications"]
        assert any(a["id"] == application_id for a in my_apps)

        # Duplicate pending application for same role returns 400
        res_dup = client.post("/v1/roles/apply", json=app_payload, headers=applicant_headers)
        assert res_dup.status_code == 400
        assert res_dup.json()["detail"]["error"]["code"] == "APPLICATION_PENDING"

        # 3. Admin logs in and reviews applications
        admin_auth = login_and_get_auth("admin@arthentic.io", "Admin123!")

        # Admin lists applications
        res_admin_list = client.get("/v1/admin/applications", headers=admin_auth["headers"])
        assert res_admin_list.status_code == 200
        all_apps = res_admin_list.json()["applications"]
        target_app = next((a for a in all_apps if a["id"] == application_id), None)
        assert target_app is not None
        assert target_app["requested_role"] == "Artist"
        assert len(target_app["documents"]) == 1

        # 4. Admin approves application
        res_review = client.post(
            f"/v1/admin/applications/{application_id}/review",
            json={"decision": "approve", "review_note": "Verified exhibition history and credentials."},
            headers=admin_auth["headers"],
        )
        assert res_review.status_code == 200
        assert res_review.json()["application_status"] == "approved"

        # 5. Milestone 5 Exit: Applicant calls /auth/refresh -> newly granted "Artist" role appears in JWT!
        res_refresh = client.post("/auth/refresh", json={"refresh_token": applicant_refresh})
        assert res_refresh.status_code == 200
        refreshed_data = res_refresh.json()
        new_access_token = refreshed_data["access_token"]
        new_applicant_headers = {"Authorization": f"Bearer {new_access_token}"}

        # Check /auth/me returns the newly granted Artist role
        res_me = client.get("/auth/me", headers=new_applicant_headers)
        assert res_me.status_code == 200
        roles_me = res_me.json()["roles"]
        assert "Artist" in roles_me
        assert "Collector" in roles_me

        # 6. Now applicant can successfully register artwork (genesis)
        res_genesis = client.post(
            "/v1/genesis/prepare",
            json={"captureIds": ["mock_cap_99"], "title": "First Masterpiece", "artist": "New Accredited Artist"},
            headers=new_applicant_headers,
        )
        assert res_genesis.status_code == 200
        token_id = res_genesis.json()["tokenId"]

        # 7. Check artist artworks
        res_artworks = client.get("/v1/artist/artworks", headers=new_applicant_headers)
        assert res_artworks.status_code == 200
        artworks = res_artworks.json()["artworks"]
        assert any(a["tokenId"] == token_id for a in artworks)

    def test_admin_more_info_and_rejection_flow(self):
        # Create applicant
        applicant = login_and_get_auth("artist@arthentic.io", "Artist123!")
        # Apply for Conservator
        res_apply = client.post(
            "/v1/roles/apply",
            json={"requested_role": "Conservator", "notes": "Applied for second accreditation"},
            headers=applicant["headers"],
        )
        assert res_apply.status_code == 200
        app_id = res_apply.json()["application"]["id"]

        admin_auth = login_and_get_auth("admin@arthentic.io", "Admin123!")

        # Request more info
        res_more_info = client.post(
            f"/v1/admin/applications/{app_id}/review",
            json={"decision": "more_info", "review_note": "Please submit museum affiliation certificate."},
            headers=admin_auth["headers"],
        )
        assert res_more_info.status_code == 200
        assert res_more_info.json()["application_status"] == "more_info"

        # Check applicant sees more_info in my-applications
        res_my = client.get("/v1/roles/my-applications", headers=applicant["headers"])
        target = next((a for a in res_my.json()["applications"] if a["id"] == app_id), None)
        assert target is not None
        assert target["status"] == "more_info"
        assert "museum affiliation" in target["review_note"]

        # Reject
        res_reject = client.post(
            f"/v1/admin/applications/{app_id}/review",
            json={"decision": "reject", "review_note": "Insufficient laboratory certification."},
            headers=admin_auth["headers"],
        )
        assert res_reject.status_code == 200
        assert res_reject.json()["application_status"] == "rejected"

    def test_conservator_condition_reporting(self):
        conservator_auth = login_and_get_auth("conservator@arthentic.io", "Conservator123!")

        # Submit condition report
        report_payload = {
            "tokenId": "101",
            "condition_grade": "Stable",
            "notes": "Surface varnish stable; micro-craquelure consistent with age.",
            "treatment_performed": "Dust removal with conservation air pump",
        }
        res_report = client.post("/v1/conservation/reports", json=report_payload, headers=conservator_auth["headers"])
        assert res_report.status_code == 200
        assert res_report.json()["status"] == "RECORDED"

        # List condition reports
        res_list = client.get("/v1/conservation/reports", headers=conservator_auth["headers"])
        assert res_list.status_code == 200
        reports = res_list.json()["reports"]
        assert len(reports) > 0
