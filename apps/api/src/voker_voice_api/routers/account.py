"""Google-authenticated dashboard session endpoints."""

from typing import Any

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from voker_voice_api.config import get_settings
from voker_voice_api.database import get_db
from voker_voice_api.models import Organization, OrganizationMember, User

router = APIRouter(prefix="/auth", tags=["account"])


def google_oauth() -> OAuth:
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth


@router.get("/google/login")
async def google_login(request: Request) -> RedirectResponse:
    callback = request.url_for("google_callback")
    return await google_oauth().google.authorize_redirect(request, callback)


@router.get("/google/callback", name="google_callback")
async def google_callback(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    token: dict[str, Any] = await google_oauth().google.authorize_access_token(request)
    claims = token.get("userinfo") or await google_oauth().google.userinfo(token=token)
    subject, email = claims.get("sub"), claims.get("email")
    if (
        not isinstance(subject, str)
        or not isinstance(email, str)
        or not claims.get("email_verified")
    ):
        raise HTTPException(status_code=403, detail="A verified Google email is required")
    user = db.scalar(select(User).where(User.google_subject == subject))
    if user is None:
        user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, google_subject=subject, display_name=claims.get("name"))
        db.add(user)
        db.flush()
    else:
        user.google_subject = subject
        user.display_name = claims.get("name") or user.display_name
    if get_settings().app_env == "development":
        organization = db.scalar(
            select(Organization).where(Organization.name == "Voker Development")
        )
        if (
            organization is not None
            and db.scalar(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == organization.id,
                    OrganizationMember.user_id == user.id,
                )
            )
            is None
        ):
            db.add(
                OrganizationMember(organization_id=organization.id, user_id=user.id, role="owner")
            )
    db.commit()
    request.session["user_id"] = str(user.id)
    return RedirectResponse(url=get_settings().dashboard_url, status_code=303)


@router.get("/me")
def current_account(request: Request, db: Session = Depends(get_db)) -> dict[str, str | None]:
    user = require_dashboard_user(request, db)
    return {"id": str(user.id), "email": user.email, "display_name": user.display_name}


def require_dashboard_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Require an authenticated signed browser session for dashboard data."""

    user_id = request.session.get("user_id")
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in required")
    return user


@router.post("/logout")
def logout(request: Request) -> dict[str, str]:
    request.session.clear()
    return {"status": "signed_out"}
