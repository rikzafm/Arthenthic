import argparse
import sys
import uuid
from datetime import datetime, timezone
from server.db.database import SessionLocal, Base, engine
from server.db.models import User, RoleAssignment
from server.auth.password import hash_password
from server.auth.service import grant_user_role, create_audit_entry

def bootstrap_admin(email: str, password: str, display_name: str = "Admin"):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        norm_email = email.strip().lower()

        user = db.query(User).filter(User.email == norm_email).first()
        if not user:
            user = User(
                id=str(uuid.uuid4()),
                email=norm_email,
                display_name=display_name,
                password_hash=hash_password(password),
                status="active",
                email_verified_at=now,
                created_at=now,
                last_login_at=now,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"[+] Created new admin user: {norm_email} ({user.id})")
        else:
            if password:
                user.password_hash = hash_password(password)
            user.status = "active"
            db.commit()
            print(f"[*] Found existing user: {norm_email} ({user.id})")

        # Grant Admin role
        existing_assignment = db.query(RoleAssignment).filter(
            RoleAssignment.user_id == user.id,
            RoleAssignment.role == "Admin",
            RoleAssignment.status == "active",
        ).first()

        if not existing_assignment:
            assignment = RoleAssignment(
                id=str(uuid.uuid4()),
                user_id=user.id,
                role="Admin",
                status="active",
                granted_by=None,
                granted_at=now,
            )
            db.add(assignment)
            create_audit_entry(
                db,
                action="ADMIN_BOOTSTRAP",
                actor_user_id=user.id,
                target_type="role_assignment",
                target_id=assignment.id,
                meta={"email": norm_email},
            )
            db.commit()
            print(f"[+] Granted Admin role to: {norm_email}")
        else:
            print(f"[*] User {norm_email} already has an active Admin role.")

        print(f"[SUCCESS] Admin account ready for {norm_email}.")
        return user
    finally:
        db.close()

def main():
    parser = argparse.ArgumentParser(description="Bootstrap the initial Arthentic Admin account via CLI.")
    parser.add_argument("--email", default="admin@arthentic.io", help="Admin email address")
    parser.add_argument("--password", default="Admin123!", help="Admin account password")
    parser.add_argument("--display-name", default="Arthentic Admin", help="Display name for admin")

    args = parser.parse_args()
    bootstrap_admin(email=args.email, password=args.password, display_name=args.display_name)

if __name__ == "__main__":
    main()
