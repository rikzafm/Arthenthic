import uuid
from datetime import datetime, timezone
from server.db.database import SessionLocal, Base, engine
from server.db.models import User, RoleAssignment
from server.auth.password import hash_password

SEED_USERS = [
    {
        "email": "collector@arthentic.io",
        "display_name": "Dev Collector",
        "password": "Collector123!",
        "roles": [],
    },
    {
        "email": "artist@arthentic.io",
        "display_name": "Elena Rostova (Artist)",
        "password": "Artist123!",
        "roles": ["Artist"],
    },
    {
        "email": "gallery@arthentic.io",
        "display_name": "Hauser & Wirth Verifier",
        "password": "Gallery123!",
        "roles": ["Gallery"],
    },
    {
        "email": "conservator@arthentic.io",
        "display_name": "Tate Conservation Lab",
        "password": "Conservator123!",
        "roles": ["Conservator"],
    },
    {
        "email": "admin@arthentic.io",
        "display_name": "Arthentic Admin",
        "password": "Admin123!",
        "roles": ["Admin"],
    },
    {
        "email": "multirole@arthentic.io",
        "display_name": "Multi-Role Operator",
        "password": "MultiRole123!",
        "roles": ["Artist", "Conservator", "Gallery"],
    },
]

def seed_dev_users():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        for u in SEED_USERS:
            user = db.query(User).filter(User.email == u["email"]).first()
            if not user:
                user = User(
                    id=str(uuid.uuid4()),
                    email=u["email"],
                    display_name=u["display_name"],
                    password_hash=hash_password(u["password"]),
                    status="active",
                    email_verified_at=now,
                    created_at=now,
                    last_login_at=now,
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            else:
                user.status = "active"
                user.password_hash = hash_password(u["password"])
                db.commit()

            # Ensure roles exist
            for role_name in u.get("roles", []):
                existing_role = db.query(RoleAssignment).filter(
                    RoleAssignment.user_id == user.id,
                    RoleAssignment.role == role_name,
                    RoleAssignment.status == "active",
                ).first()
                if not existing_role:
                    assignment = RoleAssignment(
                        id=str(uuid.uuid4()),
                        user_id=user.id,
                        role=role_name,
                        status="active",
                        granted_at=now,
                    )
                    db.add(assignment)
            db.commit()
    finally:
        db.close()

if __name__ == "__main__":
    seed_dev_users()
    print("Dev users seeded successfully.")
