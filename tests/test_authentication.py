import os
import tempfile
import unittest
import uuid

_test_directory = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{_test_directory.name}/authentication-tests.db"
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-authentication-tests")

from app import app, db
from database import User
from werkzeug.security import check_password_hash, generate_password_hash


class AuthenticationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    def setUp(self):
        self.client = app.test_client()
        self.email = f"auth-{uuid.uuid4().hex}@gmail.com"

    def tearDown(self):
        with app.app_context():
            User.query.filter(User.email.in_((self.email, self.email.replace("@gmail.com", "@example.org")))).delete(
                synchronize_session=False
            )
            db.session.commit()

    def test_registration_accepts_gmail_normalizes_email_and_hashes_password(self):
        response = self.client.post(
            "/register",
            data={
                "name": "Test User",
                "email": self.email.upper(),
                "password": "secure-password",
            },
        )

        self.assertEqual(response.status_code, 302)
        with app.app_context():
            user = User.query.filter_by(email=self.email).one()
            self.assertTrue(check_password_hash(user.password_hash, "secure-password"))
            self.assertNotEqual(user.password_hash, "secure-password")

    def test_registration_rejects_non_gmail_addresses(self):
        response = self.client.post(
            "/register",
            data={"name": "Test User", "email": self.email.replace("@gmail.com", "@yahoo.com"), "password": "secure-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Please use a Gmail address ending with @gmail.com.", response.data)

    def test_registration_prevents_duplicate_gmail_accounts_case_insensitively(self):
        first_response = self.client.post(
            "/register",
            data={"name": "Test User", "email": self.email, "password": "secure-password"},
        )
        self.assertEqual(first_response.status_code, 302)
        self.client.post("/logout")

        duplicate_response = self.client.post(
            "/register",
            data={"name": "Another User", "email": self.email.upper(), "password": "secure-password"},
        )

        self.assertEqual(duplicate_response.status_code, 200)
        self.assertIn(b"An account already exists for that email.", duplicate_response.data)
        with app.app_context():
            self.assertEqual(User.query.filter_by(email=self.email).count(), 1)

    def test_login_accepts_registered_gmail_and_rejects_wrong_password(self):
        with app.app_context():
            db.session.add(
                User(
                    name="Test User",
                    email=self.email,
                    password_hash=generate_password_hash("secure-password"),
                )
            )
            db.session.commit()

        success = self.client.post(
            "/login", data={"email": self.email.upper(), "password": "secure-password"}
        )
        self.assertEqual(success.status_code, 302)
        self.client.post("/logout")
        wrong_password = self.client.post(
            "/login", data={"email": self.email, "password": "incorrect-password"}
        )

        self.assertEqual(wrong_password.status_code, 200)
        self.assertIn(b"The email or password was not recognised.", wrong_password.data)

    def test_login_rejects_non_gmail_accounts_even_if_present_in_database(self):
        non_gmail = self.email.replace("@gmail.com", "@example.org")
        with app.app_context():
            db.session.add(
                User(
                    name="Legacy User",
                    email=non_gmail,
                    password_hash=generate_password_hash("secure-password"),
                )
            )
            db.session.commit()

        response = self.client.post(
            "/login", data={"email": non_gmail, "password": "secure-password"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Please use a Gmail address ending with @gmail.com.", response.data)


if __name__ == "__main__":
    unittest.main()
