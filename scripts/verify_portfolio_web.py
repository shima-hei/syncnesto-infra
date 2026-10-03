"""公開URLの接続境界・Cookie・CSRF・署名付きアップロードを検証する。"""

import http.cookiejar
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

from state_environment import state_environment

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = "https://syncnesto-portfolio.vercel.app"
BACKEND = "https://syncnesto-portfolio-api-shima-hei.vercel.app"


def fetch(opener, url, *, method="GET", data=None, headers=None):
    """URL・Cookie・応答の秘密を表示せずにHTTP通信する。"""
    body = json.dumps(data).encode() if data is not None else None
    request_headers = {"Content-Type": "application/json"} if body else {}
    request_headers.update(headers or {})
    request = urllib.request.Request(
        url, data=body, headers=request_headers, method=method
    )
    try:
        with opener.open(request, timeout=45) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read()


def expect(status: int, expected: int, label: str) -> None:
    """失敗時もレスポンス本文や署名URLは表示しない。"""
    if status != expected:
        raise RuntimeError(f"{label}: expected HTTP {expected}, got {status}")


def main() -> int:
    """初期管理者のアバターを検証後にデフォルトへ戻し、ログアウトする。"""
    outputs = json.loads(
        subprocess.check_output(
            [
                "terraform",
                f"-chdir={ROOT / 'terraform' / 'portfolio'}",
                "output",
                "-json",
            ],
            env=state_environment(),
        )
    )
    bff = {"X-Syncnesto-BFF-Key": outputs["backend_bff_secret"]["value"]}
    plain = urllib.request.build_opener()
    expect(fetch(plain, BACKEND + "/")[0], 200, "backend health")
    expect(fetch(plain, BACKEND + "/auth/me")[0], 403, "direct API denial")
    for path in ("/docs", "/openapi.json", "/redoc"):
        expect(fetch(plain, BACKEND + path, headers=bff)[0], 404, "closed API docs")
    print("PASS: backend health, direct API denial, closed API documentation")

    cookies = http.cookiejar.CookieJar()
    browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    expect(fetch(browser, FRONTEND + "/login")[0], 200, "frontend login page")
    status, _, _ = fetch(
        browser,
        FRONTEND + "/api/auth/me",
        headers={"X-Syncnesto-BFF-Key": "browser-supplied-invalid-key"},
    )
    expect(status, 401, "unauthenticated BFF and internal-header overwrite")
    credentials = dotenv_values(ROOT / ".env.portfolio-admin.local")
    status, headers, body = fetch(
        browser,
        FRONTEND + "/api/auth/login",
        method="POST",
        data={
            "email": credentials["INITIAL_ADMIN_EMAIL"],
            "password": credentials["INITIAL_ADMIN_PASSWORD"],
        },
    )
    expect(status, 200, "login")
    if "access_token" in json.loads(body):
        raise RuntimeError("Login exposed a bearer token")
    cookie_headers = headers.get_all("Set-Cookie", [])
    auth = next(value for value in cookie_headers if value.startswith("access_token="))
    csrf_cookie = next(
        value for value in cookie_headers if value.startswith("csrf_token=")
    )
    if (
        not all(part in auth for part in ("HttpOnly", "Secure", "SameSite=lax"))
        or "Secure" not in csrf_cookie
    ):
        raise RuntimeError("Production cookie attributes are incomplete")
    status, _, body = fetch(browser, FRONTEND + "/api/auth/me")
    expect(status, 200, "authenticated profile")
    if json.loads(body)["email"] != credentials["INITIAL_ADMIN_EMAIL"]:
        raise RuntimeError("Authenticated identity differs")
    if not urlsplit(json.loads(body)["avatar_url"]).path.endswith(
        "/default-avatar.png"
    ):
        raise RuntimeError(
            "Use an account with the default avatar for this verification"
        )
    csrf = next(cookie.value for cookie in cookies if cookie.name == "csrf_token")
    update_headers = {"X-CSRF-Token": csrf, "Origin": FRONTEND}
    expect(
        fetch(browser, FRONTEND + "/api/auth/logout", method="POST", data={})[0],
        403,
        "missing CSRF denial",
    )
    print(
        "PASS: login, Secure/HttpOnly cookies, server-only token, BFF authentication and CSRF denial"
    )

    try:
        content = (ROOT / "default-avatar.png").read_bytes()
        status, _, body = fetch(
            browser,
            FRONTEND + "/api/auth/me/avatar/upload-plan",
            method="POST",
            headers=update_headers,
            data={
                "filename": "verification.png",
                "content_type": "image/png",
                "byte_size": len(content),
            },
        )
        expect(status, 200, "upload plan")
        plan = json.loads(body)
        if plan["mode"] != "presigned":
            raise RuntimeError("Deployment did not use presigned uploads")
        request = urllib.request.Request(
            plan["url"], data=content, method="PUT", headers=plan["headers"]
        )
        with plain.open(request, timeout=30) as response:
            expect(response.status, 200, "direct storage upload")
        status, _, body = fetch(
            browser,
            FRONTEND + "/api/auth/me/avatar/upload-complete",
            method="POST",
            headers=update_headers,
            data={"upload_token": plan["upload_token"]},
        )
        expect(status, 200, "upload completion")
        with plain.open(json.loads(body)["avatar_url"], timeout=30) as response:
            if response.read() != content:
                raise RuntimeError("Completed avatar differs from uploaded bytes")
        print(
            "PASS: authenticated plan, signed S3 PUT, completion, private image download"
        )
    finally:
        expect(
            fetch(
                browser,
                FRONTEND + "/api/auth/me/avatar",
                method="DELETE",
                headers=update_headers,
            )[0],
            200,
            "restore default avatar",
        )
        expect(
            fetch(
                browser,
                FRONTEND + "/api/auth/logout",
                method="POST",
                headers=update_headers,
                data={},
            )[0],
            204,
            "logout",
        )
    expect(fetch(browser, FRONTEND + "/api/auth/me")[0], 401, "logged out session")

    # 存在しない入力なのでアカウントの失敗回数を増やさない。
    budget_headers = {**bff, "X-Syncnesto-Client-IP": "203.0.113.99"}
    for _ in range(10):
        expect(
            fetch(
                plain,
                BACKEND + "/auth/login",
                method="POST",
                headers=budget_headers,
                data={},
            )[0],
            422,
            "login budget",
        )
    status, headers, _ = fetch(
        plain, BACKEND + "/auth/login", method="POST", headers=budget_headers, data={}
    )
    expect(status, 429, "login budget exhaustion")
    if not headers.get("Retry-After"):
        raise RuntimeError("429 response has no Retry-After")
    print(
        "PASS: logout invalidates session; login rate limit returns 429 and Retry-After"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, KeyError, urllib.error.URLError) as error:
        label = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print("Web verification failed: " + label, file=sys.stderr)
        raise SystemExit(1) from None
