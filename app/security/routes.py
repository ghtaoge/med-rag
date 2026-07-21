"""本地账户认证 API。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Cookie, Depends, Header, Request, Response
from pydantic import BaseModel, Field

from app.core.dependencies import get_auth_service
from app.core.exceptions import AuthenticationError
from app.security.auth_service import AuthService, AuthTokens
from app.security.principal import Principal, get_current_principal
from app.security.permissions import ROLE_PERMISSIONS

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])
_REFRESH_COOKIE = "med_rag_refresh"


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=512)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=12, max_length=512)


class ReauthenticateRequest(BaseModel):
    password: str = Field(min_length=1, max_length=512)


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-ID") or str(uuid.uuid4())


def _set_refresh_cookie(response: Response, tokens: AuthTokens, service: AuthService) -> None:
    response.set_cookie(
        _REFRESH_COOKIE,
        tokens.refresh_token,
        httponly=True,
        secure=service.config["auth"]["secure_cookies"],
        samesite="strict",
        max_age=service.config["auth"]["refresh_ttl_seconds"],
        path="/api/v1/auth",
    )


def _token_response(tokens: AuthTokens) -> dict:
    return {
        "access_token": tokens.access_token,
        "csrf_token": tokens.csrf_token,
        "token_type": "bearer",
        "expires_in": tokens.expires_in,
    }


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
):
    tokens = service.login(payload.username, payload.password, _request_id(request))
    _set_refresh_cookie(response, tokens, service)
    return _token_response(tokens)


@router.post("/refresh")
def refresh(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=_REFRESH_COOKIE),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    service: AuthService = Depends(get_auth_service),
):
    if not refresh_token or not csrf_token:
        raise AuthenticationError("刷新令牌无效")
    tokens = service.refresh(refresh_token, csrf_token, _request_id(request))
    _set_refresh_cookie(response, tokens, service)
    return _token_response(tokens)


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=_REFRESH_COOKIE),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    service: AuthService = Depends(get_auth_service),
):
    if refresh_token and csrf_token:
        service.logout(refresh_token, csrf_token, _request_id(request))
    response.delete_cookie(_REFRESH_COOKIE, path="/api/v1/auth")


@router.post("/change-password", status_code=204)
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    service: AuthService = Depends(get_auth_service),
):
    service.change_password(
        principal.user_id,
        payload.current_password,
        payload.new_password,
        principal.session_id,
        _request_id(request),
    )


@router.post("/reauthenticate")
def reauthenticate(
    payload: ReauthenticateRequest,
    principal: Principal = Depends(get_current_principal),
    service: AuthService = Depends(get_auth_service),
):
    return {
        "reauthentication_token": service.reauthenticate(
            principal.user_id,
            principal.session_id,
            payload.password,
        ),
        "expires_in": 300,
    }


@router.get("/me")
def me(principal: Principal = Depends(get_current_principal)):
    permissions = sorted(
        {
            permission.value
            for membership in principal.memberships
            for permission in ROLE_PERMISSIONS[membership.role]
        }
    )
    return {
        "user_id": principal.user_id,
        "username": principal.username,
        "memberships": [
            {"department_id": item.department_id, "role": item.role.value}
            for item in principal.memberships
        ],
        "permissions": permissions,
    }
