from unittest import TestCase

from app.models.user import User, UserCreate, UserResponse


class UserModelTests(TestCase):
    def test_user_table_has_password_without_full_name(self) -> None:
        self.assertEqual(
            set(User.__table__.columns.keys()),
            {"id", "username", "email", "password", "created_at", "updated_at"},
        )


class UserSchemaTests(TestCase):
    def test_user_schemas_exclude_full_name(self) -> None:
        created = UserCreate(
            username="reval",
            email="reval@example.com",
            password="secret",
        )
        response = UserResponse(id=1, username="reval", email="reval@example.com")

        self.assertEqual(
            created.model_dump(),
            {
                "username": "reval",
                "email": "reval@example.com",
                "password": "secret",
            },
        )
        self.assertEqual(
            response.model_dump(),
            {"id": 1, "username": "reval", "email": "reval@example.com"},
        )
