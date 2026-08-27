from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    full_name: str | None = None


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: str | None

    model_config = ConfigDict(from_attributes=True)
