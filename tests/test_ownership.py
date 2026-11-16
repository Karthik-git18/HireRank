import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

_test_directory = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{_test_directory.name}/ownership-tests.db"
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ownership-tests")

from app import BASE_DIR, app, db
from database import Candidate, CandidateApplication, InterviewQuestion, Resume, User, Vacancy
from werkzeug.security import generate_password_hash


class AccountIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    def setUp(self):
        with app.app_context():
            db.drop_all()
            db.create_all()
            self.owner_one = User(
                name="Owner One",
                email="one@example.org",
                password_hash=generate_password_hash("password-one"),
            )
            self.owner_two = User(
                name="Owner Two",
                email="two@example.org",
                password_hash=generate_password_hash("password-two"),
            )
            db.session.add_all([self.owner_one, self.owner_two])
            db.session.flush()
            self.owner_one_id = self.owner_one.id
            self.data_one = self._add_workspace_data(self.owner_one, "Private One")
            self.data_two = self._add_workspace_data(self.owner_two, "Private Two")
            db.session.commit()
        self.client = app.test_client()
        response = self.client.post(
            "/login",
            data={"email": "one@example.org", "password": "password-one"},
        )
        self.assertEqual(response.status_code, 302)

    def _add_workspace_data(self, owner, label):
        vacancy = Vacancy(
            owner_id=owner.id,
            title=f"{label} Vacancy",
            description="Python engineer",
            required_skills="Python",
        )
        candidate = Candidate(
            owner_id=owner.id,
            name=f"{label} Candidate",
            email=f"{label.lower().replace(' ', '.')}@example.org",
        )
        db.session.add_all([vacancy, candidate])
        db.session.flush()
        application = CandidateApplication(
            candidate_id=candidate.id,
            vacancy_id=vacancy.id,
            status="Shortlisted",
        )
        resume = Resume(
            candidate_id=candidate.id,
            filename="resume.pdf",
            stored_path="uploads/resumes/not-created-by-test.pdf",
            sha256=f"{owner.id:064x}",
            extracted_text="Python engineer",
        )
        db.session.add_all([application, resume])
        db.session.flush()
        db.session.add(
            InterviewQuestion(
                vacancy_id=vacancy.id,
                candidate_id=candidate.id,
                application_id=application.id,
                category="Technical",
                question=f"Discuss {label}.",
                difficulty="Beginner",
            )
        )
        return {
            "candidate_id": candidate.id,
            "vacancy_id": vacancy.id,
            "application_id": application.id,
            "resume_id": resume.id,
        }

    def test_workspace_pages_only_show_the_signed_in_accounts_records(self):
        for path in (
            "/dashboard",
            "/vacancies",
            "/candidates",
            "/rankings",
            "/resumes",
            "/candidate-validation",
            "/interviews",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn(b"Private Two", response.data)
                self.assertIn(b"Private One", response.data)

    def test_candidate_profile_renders_with_advisory_validation_fields(self):
        response = self.client.get(f"/candidates/{self.data_one['candidate_id']}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Private One Candidate", response.data)
        self.assertIn(b"Candidate validation report", response.data)

    def test_private_resources_and_mutations_are_not_accessible_cross_account(self):
        foreign = self.data_two
        responses = (
            self.client.get(f"/candidates/{foreign['candidate_id']}"),
            self.client.get(f"/vacancies/{foreign['vacancy_id']}/edit"),
            self.client.get(f"/resumes/{foreign['resume_id']}/download"),
            self.client.post(f"/applications/{foreign['application_id']}/status", data={"status": "Rejected"}),
            self.client.post(f"/api/applications/{foreign['application_id']}/validate", json={}),
            self.client.get(f"/api/vacancies/{foreign['vacancy_id']}/shortlisted"),
            self.client.post(
                "/api/interview-questions/generate",
                json={
                    "vacancy_id": foreign["vacancy_id"],
                    "candidate_id": foreign["candidate_id"],
                    "difficulty": "Beginner",
                    "count": 1,
                },
            ),
        )
        self.assertTrue(all(response.status_code == 404 for response in responses))

    def test_duplicate_profile_search_does_not_inspect_other_accounts(self):
        with app.app_context():
            candidate_one = db.session.get(Candidate, self.data_one["candidate_id"])
            candidate_two = db.session.get(Candidate, self.data_two["candidate_id"])
            candidate_two.email = candidate_one.email
            db.session.commit()

        response = self.client.post(
            f"/api/applications/{self.data_one['application_id']}/validate",
            json={},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["report"]["potential_duplicates"], [])

    def test_resume_upload_deduplicates_exact_bytes_not_same_person(self):
        def make_pdf(text):
            document = fitz.open()
            document.new_page().insert_text((72, 72), text)
            content = document.tobytes()
            document.close()
            return content

        candidate_text = (
            "Alex Morgan\nalex.morgan@example.org\nPython Developer\n"
            "Skills\nPython\nEducation\nB.Tech in Computer Science\n"
            "Projects\nInventory API\nBuilt an API using Python."
        )
        original_pdf = make_pdf(candidate_text)
        changed_pdf = make_pdf(candidate_text + "\nAdditional project details.")

        with tempfile.TemporaryDirectory(dir=BASE_DIR / "tests") as directory:
            with patch("app.UPLOAD_DIR", Path(directory)):
                self.client.post(
                    "/resumes",
                    data={
                        "vacancy_id": str(self.data_one["vacancy_id"]),
                        "files": (io.BytesIO(original_pdf), "alex.pdf"),
                    },
                    content_type="multipart/form-data",
                    follow_redirects=True,
                )
                duplicate_response = self.client.post(
                    "/resumes",
                    data={
                        "vacancy_id": str(self.data_one["vacancy_id"]),
                        "files": (io.BytesIO(original_pdf), "alex-copy.pdf"),
                    },
                    content_type="multipart/form-data",
                    follow_redirects=True,
                )
                self.assertIn(b"exact file has already been uploaded", duplicate_response.data)
                self.client.post(
                    "/resumes",
                    data={
                        "vacancy_id": str(self.data_one["vacancy_id"]),
                        "files": (io.BytesIO(changed_pdf), "alex-updated.pdf"),
                    },
                    content_type="multipart/form-data",
                    follow_redirects=True,
                )

        with app.app_context():
            resumes = Resume.query.join(Candidate).filter(
                Candidate.owner_id == self.owner_one_id
            ).count()
            self.assertEqual(resumes, 3)

    def test_created_vacancies_are_assigned_to_the_signed_in_hr_account(self):
        response = self.client.post(
            "/vacancies/new",
            data={"title": "New Private Vacancy"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        with app.app_context():
            vacancy = Vacancy.query.filter_by(title="New Private Vacancy").one()
            self.assertEqual(vacancy.owner_id, self.owner_one_id)


if __name__ == "__main__":
    unittest.main()
