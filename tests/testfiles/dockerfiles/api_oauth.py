"""Fastapi-based API used for testing with mock OAuth protection."""

import os
import subprocess

from fastapi import Body, Depends, FastAPI, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

app = FastAPI()

# ---- Mock OAuth2 / Bearer auth ----
security = HTTPBearer()

MOCK_TOKEN = "mock-token"


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Verify the token."""
    token = credentials.credentials

    if token != MOCK_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
        )

    return token


# ---- Protected endpoints ----


@app.get("/greet")
def greet(
    name: str = Query(..., description="Name of the person"),
    age: int = Query(..., ge=0, description="Age of the person"),
    token: str = Depends(verify_token),
):
    """Greet endpoint that returns name and age."""
    return {"message": f"Hello {name}, you are {age} years old!"}


@app.get("/user")
def get_user(
    user_id: int = Query(..., ge=1, description="ID of the user"),
    token: str = Depends(verify_token),
):
    """Mock endpoint for obtaining a user."""
    return {"user_id": user_id, "info": "This is a GET request returning user info"}


@app.post("/user")
def create_user(
    name: str = Body(...),
    age: int = Body(..., ge=0),
    token: str = Depends(verify_token),
):
    """Mock endpoint for creating a user."""
    return {"message": f"User {name} ({age} years old) created successfully!"}


if __name__ == "__main__":
    port = os.getenv("HOST_PORT", "8001")
    subprocess.run(["fastapi", "run", __file__, "--port", port])
