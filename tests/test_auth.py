from unittest import TestCase

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_oauth_state,
    decode_access_token,
    decode_oauth_state,
    hash_login_code,
    hash_password,
    is_allowed_frontend_url,
    verify_password,
)
from app.models.auth import AuthActionToken, AuthTokenPurpose, OAuthLoginCode
from app.api.auth import google_is_email_authority


class AuthSecurityTests(TestCase):
    def setUp(self) -> None:
        self.jwt_secret = settings.jwt_secret_key
        self.cors_origins = settings.cors_origins
        self.cors_origin_regex = settings.cors_origin_regex
        settings.jwt_secret_key = "test-secret-that-is-not-used-in-production"

    def tearDown(self) -> None:
        settings.jwt_secret_key = self.jwt_secret
        settings.cors_origins = self.cors_origins
        settings.cors_origin_regex = self.cors_origin_regex

    def test_passwords_are_hashed_and_verified(self) -> None:
        encoded = hash_password("correct-horse-battery-staple")

        self.assertNotEqual(encoded, "correct-horse-battery-staple")
        self.assertTrue(verify_password("correct-horse-battery-staple", encoded))
        self.assertFalse(verify_password("wrong-password", encoded))

    def test_access_token_is_typed_and_identifies_user(self) -> None:
        token, expires_in = create_access_token(42, 3)

        self.assertEqual(decode_access_token(token), (42, 3))
        self.assertGreater(expires_in, 0)

    def test_oauth_state_round_trip(self) -> None:
        state = create_oauth_state(
            "https://jalur-b.vercel.app/auth/callback",
            "nonce",
            "browser-state",
        )

        self.assertEqual(
            decode_oauth_state(state),
            ("https://jalur-b.vercel.app/auth/callback", "nonce", "browser-state"),
        )

    def test_frontend_redirects_require_an_allowed_origin(self) -> None:
        settings.cors_origins = "http://localhost:5173,https://jalur-b.vercel.app"
        settings.cors_origin_regex = r"^https://jalur-b-[a-z0-9-]+\.vercel\.app$"

        self.assertTrue(is_allowed_frontend_url("https://jalur-b.vercel.app/auth/callback"))
        self.assertTrue(
            is_allowed_frontend_url("https://jalur-b-git-main-team.vercel.app/auth/callback")
        )
        self.assertFalse(is_allowed_frontend_url("https://attacker.example/auth/callback"))

    def test_login_codes_are_stored_as_hashes(self) -> None:
        raw_code = "single-use-code"

        self.assertEqual(len(hash_login_code(raw_code)), 64)
        self.assertNotEqual(hash_login_code(raw_code), raw_code)
        self.assertIn("code_hash", OAuthLoginCode.__table__.columns)

    def test_google_auto_link_requires_authoritative_email_domain(self) -> None:
        self.assertTrue(google_is_email_authority("user@gmail.com", None))
        self.assertTrue(google_is_email_authority("user@company.com", "company.com"))
        self.assertFalse(google_is_email_authority("user@example.com", None))
        self.assertFalse(google_is_email_authority("user@other.com", "company.com"))

    def test_auth_action_tokens_support_verification_and_reset(self) -> None:
        self.assertEqual(
            {purpose.value for purpose in AuthTokenPurpose},
            {"verify_email", "reset_password"},
        )
        self.assertEqual(
            set(AuthActionToken.__table__.columns.keys()),
            {
                "id",
                "user_id",
                "purpose",
                "token_hash",
                "expires_at",
                "used_at",
                "created_at",
            },
        )
