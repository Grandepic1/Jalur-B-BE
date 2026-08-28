from unittest import TestCase

from app.models.user import User, UserCreate, UserResponse


class UserModelTests(TestCase):
    def test_user_table_has_password_without_full_name(self) -> None:
        self.assertEqual(
            set(User.__table__.columns.keys()),
            {
                "id",
                "username",
                "email",
                "password",
                "google_sub",
                "email_verified",
                "token_version",
                "created_at",
                "updated_at",
            },
        )


class UserSchemaTests(TestCase):
    def test_user_schemas_exclude_full_name(self) -> None:
        created = UserCreate(
            username="reval",
            email="reval@example.com",
            password="secret123",
        )
        response = UserResponse(
            id=1,
            username="reval",
            email="reval@example.com",
            email_verified=False,
        )

        self.assertEqual(
            created.model_dump(),
            {
                "username": "reval",
                "email": "reval@example.com",
                "password": "secret123",
            },
        )
        self.assertEqual(
            response.model_dump(),
            {
                "id": 1,
                "username": "reval",
                "email": "reval@example.com",
                "email_verified": False,
            },
        )
