from datetime import datetime, timezone

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Vacancy(db.Model):
    __tablename__ = "vacancies"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    department = db.Column(db.String(120), nullable=False, default="")
    location = db.Column(db.String(120), nullable=False, default="")
    employment_type = db.Column(db.String(60), nullable=False, default="Full-Time")
    min_experience = db.Column(db.Float, nullable=False, default=0)
    max_experience = db.Column(db.Float, nullable=False, default=0)
    required_skills = db.Column(db.Text, nullable=False, default="")
    preferred_skills = db.Column(db.Text, nullable=False, default="")
    education = db.Column(db.Text, nullable=False, default="")
    description = db.Column(db.Text, nullable=False, default="")
    responsibilities = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="Active")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    applications = db.relationship(
        "CandidateApplication", back_populates="vacancy", cascade="all, delete-orphan"
    )


class Candidate(db.Model):
    __tablename__ = "candidates"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False, default="Unidentified candidate")
    email = db.Column(db.String(255), nullable=False, default="")
    phone = db.Column(db.String(60), nullable=False, default="")
    education = db.Column(db.Text, nullable=False, default="")
    experience_years = db.Column(db.Float)
    experience_summary = db.Column(db.Text, nullable=False, default="")
    projects = db.Column(db.Text, nullable=False, default="")
    certifications = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    resumes = db.relationship("Resume", back_populates="candidate", cascade="all, delete-orphan")
    skills = db.relationship(
        "CandidateSkill", back_populates="candidate", cascade="all, delete-orphan"
    )
    applications = db.relationship(
        "CandidateApplication", back_populates="candidate", cascade="all, delete-orphan"
    )


class Resume(db.Model):
    __tablename__ = "resumes"

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(
        db.Integer, db.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    filename = db.Column(db.String(255), nullable=False)
    stored_path = db.Column(db.String(500), nullable=False)
    sha256 = db.Column(db.String(64), unique=True, nullable=False, index=True)
    extracted_text = db.Column(db.Text, nullable=False, default="")
    extraction_status = db.Column(db.String(40), nullable=False, default="Processed")
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    candidate = db.relationship("Candidate", back_populates="resumes")


class CandidateSkill(db.Model):
    __tablename__ = "candidate_skills"

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(
        db.Integer, db.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    name = db.Column(db.String(100), nullable=False)
    __table_args__ = (db.UniqueConstraint("candidate_id", "name"),)
    candidate = db.relationship("Candidate", back_populates="skills")


class CandidateApplication(db.Model):
    __tablename__ = "candidate_applications"

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(
        db.Integer, db.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    vacancy_id = db.Column(
        db.Integer, db.ForeignKey("vacancies.id", ondelete="CASCADE"), nullable=False
    )
    status = db.Column(db.String(30), nullable=False, default="Applied")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    candidate = db.relationship("Candidate", back_populates="applications")
    vacancy = db.relationship("Vacancy", back_populates="applications")
    score = db.relationship(
        "CandidateScore", back_populates="application", uselist=False, cascade="all, delete-orphan"
    )
    status_history = db.relationship(
        "ApplicationStatusHistory", back_populates="application", cascade="all, delete-orphan"
    )
    interview_questions = db.relationship(
        "InterviewQuestion", back_populates="application", cascade="all, delete-orphan"
    )
    __table_args__ = (db.UniqueConstraint("candidate_id", "vacancy_id"),)


class CandidateScore(db.Model):
    __tablename__ = "candidate_scores"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(
        db.Integer,
        db.ForeignKey("candidate_applications.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    description_similarity = db.Column(db.Float, nullable=False, default=0)
    required_skills = db.Column(db.Float, nullable=False, default=0)
    experience_match = db.Column(db.Float, nullable=False, default=0)
    education_match = db.Column(db.Float, nullable=False, default=0)
    preferred_skills = db.Column(db.Float, nullable=False, default=0)
    final_score = db.Column(db.Float, nullable=False, default=0)
    explanation = db.Column(db.Text, nullable=False, default="{}")
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    application = db.relationship("CandidateApplication", back_populates="score")


class InterviewQuestion(db.Model):
    __tablename__ = "interview_questions"

    id = db.Column(db.Integer, primary_key=True)
    vacancy_id = db.Column(
        db.Integer, db.ForeignKey("vacancies.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id = db.Column(
        db.Integer, db.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    application_id = db.Column(
        db.Integer,
        db.ForeignKey("candidate_applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    category = db.Column(db.String(60), nullable=False, default="Technical")
    question = db.Column(db.Text, nullable=False)
    difficulty = db.Column(db.String(30), nullable=False, default="Intermediate")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    application = db.relationship("CandidateApplication", back_populates="interview_questions")
    vacancy = db.relationship("Vacancy")
    candidate = db.relationship("Candidate")


class ApplicationStatusHistory(db.Model):
    __tablename__ = "application_status_history"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(
        db.Integer,
        db.ForeignKey("candidate_applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    old_status = db.Column(db.String(30), nullable=False)
    new_status = db.Column(db.String(30), nullable=False)
    changed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    application = db.relationship("CandidateApplication", back_populates="status_history")


class CandidateValidation(db.Model):
    __tablename__ = "candidate_validations"

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(
        db.Integer, db.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    vacancy_id = db.Column(
        db.Integer, db.ForeignKey("vacancies.id", ondelete="CASCADE"), nullable=False
    )
    report = db.Column(db.Text, nullable=False)
    generated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    __table_args__ = (
        db.UniqueConstraint("candidate_id", "vacancy_id", name="uq_candidate_validation_pair"),
    )
