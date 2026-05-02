"""Fastapi-based API used for testing with OAuth2 authentication."""

import subprocess

from fastapi import Body, Depends, FastAPI, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

app = FastAPI()

# Fake user "database"
fake_users_db = {
    "alice": {
        "username": "alice",
        "password": "secret",
    }
}

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def authenticate_user(username: str, password: str):
    """Authenticate the user with oauth2."""
    user = fake_users_db.get(username)
    if not user or user["password"] != password:
        return None
    return user


def get_current_user(token: str = Depends(oauth2_scheme)):
    """Obtain the current user based on token."""
    user = fake_users_db.get(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    return user


@app.post("/token")
def login(form_data: OAuth2PasswordRequestForm | None = None):
    """Login endpoint."""
    if form_data is None:
        form_data = Depends()
        assert form_data is not None

    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    return {"access_token": user["username"], "token_type": "bearer"}


@app.get("/greet")
def greet(
    name: str = Query(..., description="Name of the person"),
    age: int = Query(..., ge=0, description="Age of the person"),
    current_user: dict | None = None,
):
    """Greet endpoint that returns name and age."""
    if current_user is None:
        current_user = Depends(get_current_user)
        assert current_user is not None

    return {
        "message": f"Hello {name}, you are {age} years old!",
        "authenticated_as": current_user["username"],
    }


@app.get("/user")
def get_user(
    user_id: int = Query(..., ge=1, description="ID of the user"),
    current_user: dict | None = None,
):
    """Mock endpoint for obtaining a user."""
    if current_user is None:
        current_user = Depends(get_current_user)
        assert current_user is not None

    return {
        "user_id": user_id,
        "info": "This is a GET request returning user info",
        "requested_by": current_user["username"],
    }


@app.post("/user")
def create_user(
    name: str = Body(...),
    age: int = Body(..., ge=0),
    current_user: dict | None = None,
):
    """Mock endpoint for creating a user."""
    if current_user is None:
        current_user = Depends(get_current_user)
        assert current_user is not None

    return {
        "message": f"User {name} ({age} years old) created successfully!",
        "created_by": current_user["username"],
    }


if __name__ == "__main__":
    subprocess.run(["fastapi", "run", __file__])
