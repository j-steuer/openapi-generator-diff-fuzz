"""Fastapi-based API used for testing."""

import subprocess

from fastapi import Body, FastAPI, Query

app = FastAPI()


@app.get("/greet")
def greet(
    name: str = Query(..., description="Name of the person"),
    age: int = Query(..., ge=0, description="Age of the person"),
):
    """Greet endpoint that returns name and age."""
    return {"message": f"Hello {name}, you are {age} years old!"}


# GET method for /user
@app.get("/user")
def get_user(user_id: int = Query(..., ge=1, description="ID of the user")):
    """Mock endpoint for obtaining a user."""
    return {"user_id": user_id, "info": "This is a GET request returning user info"}


# POST method for /user
@app.post("/user")
def create_user(name: str = Body(...), age: int = Body(..., ge=0)):
    """Mock endpoint for creating a user."""
    return {"message": f"User {name} ({age} years old) created successfully!"}


if __name__ == "__main__":
    subprocess.run(["fastapi", "run", __file__])
