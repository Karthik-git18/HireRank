import hashlib
import json
import math
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import fitz
from dotenv import load_dotenv
from email_validator import EmailNotValidError, validate_email
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event, inspect, or_, text
from sqlalchemy.engine import Engine
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from database import (
    ApplicationStatusHistory,
    Candidate,
    CandidateApplication,
    CandidateScore,
    CandidateSkill,
    CandidateValidation,
    InterviewQuestion,
    Resume,
    User,
    Vacancy,
    db,
)
from interview_ai import (
    QUESTION_CATEGORIES,
    InterviewGenerationError,
    generate_questions,
)
from candidate_validation import build_validation_report
from ml_engine import calculate_match, extract_resume_information

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads" / "resumes"
MAX_FILE_SIZE = 8 * 1024 * 1024
ALLOWED_STATUSES = {"Applied", "Under Review", "Shortlisted", "Selected", "Rejected"}
configured_secret = os.getenv("SECRET_KEY", "").strip()
if configured_secret == "replace-this-with-a-long-random-secret":
    configured_secret = ""

app = Flask(__name__)
app.config.update(
    SECRET_KEY=configured_secret or os.urandom(32),
    SQLALCHEMY_DATABASE_URI=f"sqlite:///{BASE_DIR / 'hirerank.db'}",
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
    UPLOAD_FOLDER=str(UPLOAD_DIR),
)
db.init_app(app)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message_category = "warning"


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(connection, _):
    if connection.__class__.__module__ == "sqlite3":
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@app.context_processor
def inject_current_time():
    return {"now": datetime.now()}


def _csv_list(value):
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def _normalized_email(value):
    try:
        return validate_email(value, check_deliverability=False).normalized
    except EmailNotValidError:
        return None


def _save_score(application):
    resume = application.candidate.resumes[-1] if application.candidate.resumes else None
    result = calculate_match(resume.extracted_text if resume else "", application.candidate, application.vacancy)
    score = application.score or CandidateScore(application=application)
    for key in (
        "description_similarity", "required_skills", "experience_match",
        "education_match", "preferred_skills", "final_score",
    ):
        setattr(score, key, result[key])
    score.explanation = json.dumps(result["explanation"])
    score.updated_at = datetime.utcnow()
    db.session.add(score)
    return score


def _application_query():
    return CandidateApplication.query.join(Candidate).join(Vacancy).outerjoin(CandidateScore)


@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = _normalized_email(request.form.get("email", "").strip())
        password = request.form.get("password", "")
        if not name or len(name) > 120 or not email:
            flash("Enter a name and a valid email address.", "error")
        elif len(password) < 8:
            flash("Choose a password with at least 8 characters.", "error")
        elif User.query.filter_by(email=email).first():
            flash("An account already exists for that email.", "error")
        else:
            user = User(name=name, email=email, password_hash=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Your HR account is ready.", "success")
            return redirect(url_for("dashboard"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, request.form.get("password", "")):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("The email or password was not recognised.", "error")
    return render_template("login.html")


@app.post("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    total_vacancies = Vacancy.query.count()
    active_vacancies = Vacancy.query.filter_by(status="Active").count()
    total_candidates = Candidate.query.count()
    total_resumes = Resume.query.count()
    shortlisted = CandidateApplication.query.filter_by(status="Shortlisted").count()
    selected = CandidateApplication.query.filter_by(status="Selected").count()
    recent_vacancies = Vacancy.query.order_by(Vacancy.created_at.desc()).limit(5).all()
    recent_resumes = Resume.query.order_by(Resume.uploaded_at.desc()).limit(5).all()
    recent_applications = CandidateApplication.query.order_by(
        CandidateApplication.created_at.desc()
    ).limit(5).all()
    pipeline = {
        status: CandidateApplication.query.filter_by(status=status).count()
        for status in ("Applied", "Under Review", "Shortlisted", "Selected", "Rejected")
    }
    scores = [row[0] for row in db.session.query(CandidateScore.final_score).all()]
    score_buckets = {
        "0–39": sum(1 for score in scores if score < 40),
        "40–59": sum(1 for score in scores if 40 <= score < 60),
        "60–79": sum(1 for score in scores if 60 <= score < 80),
        "80–100": sum(1 for score in scores if score >= 80),
    }
    return render_template(
        "dashboard.html",
        stats={
            "vacancies": total_vacancies, "active": active_vacancies,
            "candidates": total_candidates, "resumes": total_resumes,
            "shortlisted": shortlisted, "selected": selected,
        },
        recent_vacancies=recent_vacancies,
        recent_resumes=recent_resumes,
        recent_applications=recent_applications,
        pipeline=pipeline,
        score_buckets=score_buckets,
    )


@app.route("/vacancies")
@login_required
def vacancies():
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    query = Vacancy.query
    if search:
        query = query.filter(or_(Vacancy.title.ilike(f"%{search}%"), Vacancy.department.ilike(f"%{search}%")))
    if status in {"Active", "Inactive"}:
        query = query.filter_by(status=status)
    rows = query.order_by(Vacancy.created_at.desc()).all()
    return render_template("vacancies.html", vacancies=rows, search=search, selected_status=status)


def _vacancy_form(vacancy=None):
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        minimum = request.form.get("min_experience", "0").strip()
        maximum = request.form.get("max_experience", "0").strip()
        try:
            minimum_value, maximum_value = float(minimum or 0), float(maximum or 0)
        except ValueError:
            flash("Experience values must be numeric.", "error")
            return None
        if not title:
            flash("Job title is required.", "error")
            return None
        if (
            not math.isfinite(minimum_value)
            or not math.isfinite(maximum_value)
            or minimum_value < 0
            or maximum_value < minimum_value
        ):
            flash("Enter a valid experience range.", "error")
            return None
        fields = {
            "title": title,
            "department": request.form.get("department", "").strip(),
            "location": request.form.get("location", "").strip(),
            "employment_type": request.form.get("employment_type", "Full-Time"),
            "min_experience": minimum_value,
            "max_experience": maximum_value,
            "required_skills": request.form.get("required_skills", "").strip(),
            "preferred_skills": request.form.get("preferred_skills", "").strip(),
            "education": request.form.get("education", "").strip(),
            "description": request.form.get("description", "").strip(),
            "responsibilities": request.form.get("responsibilities", "").strip(),
            "status": request.form.get("status", "Active"),
        }
        if fields["status"] not in {"Active", "Inactive"}:
            fields["status"] = "Active"
        if vacancy is None:
            vacancy = Vacancy(**fields)
            db.session.add(vacancy)
        else:
            for key, value in fields.items():
                setattr(vacancy, key, value)
        db.session.flush()
        for application in vacancy.applications:
            _save_score(application)
        db.session.commit()
        flash("Vacancy saved.", "success")
        return redirect(url_for("vacancies"))
    return vacancy


@app.route("/vacancies/new", methods=["GET", "POST"])
@login_required
def vacancy_new():
    vacancy = _vacancy_form()
    if request.method == "POST" and vacancy:
        return redirect(url_for("vacancies"))
    return render_template("create_vacancy.html", vacancy=vacancy, is_edit=False)


@app.route("/vacancies/<int:vacancy_id>/edit", methods=["GET", "POST"])
@login_required
def vacancy_edit(vacancy_id):
    vacancy = db.get_or_404(Vacancy, vacancy_id)
    updated = _vacancy_form(vacancy)
    if request.method == "POST" and updated:
        return redirect(url_for("vacancies"))
    return render_template("create_vacancy.html", vacancy=vacancy, is_edit=True)


@app.post("/vacancies/<int:vacancy_id>/toggle")
@login_required
def vacancy_toggle(vacancy_id):
    vacancy = db.get_or_404(Vacancy, vacancy_id)
    vacancy.status = "Inactive" if vacancy.status == "Active" else "Active"
    db.session.commit()
    flash(f"{vacancy.title} is now {vacancy.status.lower()}.", "success")
    return redirect(url_for("vacancies"))


@app.post("/vacancies/<int:vacancy_id>/delete")
@login_required
def vacancy_delete(vacancy_id):
    vacancy = db.get_or_404(Vacancy, vacancy_id)
    db.session.delete(vacancy)
    db.session.commit()
    flash("Vacancy and its applications were deleted.", "success")
    return redirect(url_for("vacancies"))


@app.route("/resumes", methods=["GET", "POST"])
@login_required
def resumes():
    if request.method == "POST":
        vacancy_id = request.form.get("vacancy_id", type=int)
        vacancy = db.session.get(Vacancy, vacancy_id) if vacancy_id else None
        files = [file for file in request.files.getlist("files") if file and file.filename]
        if not vacancy or vacancy.status != "Active":
            flash("Select an active vacancy before uploading resumes.", "error")
        elif not files:
            flash("Choose at least one PDF resume.", "error")
        else:
            accepted = 0
            for file in files:
                original_name = file.filename
                if not original_name.lower().endswith(".pdf"):
                    flash(f"{original_name}: only PDF files are accepted.", "error")
                    continue
                content = file.read(MAX_FILE_SIZE + 1)
                if len(content) > MAX_FILE_SIZE:
                    flash(f"{original_name}: file exceeds the 8 MB limit.", "error")
                    continue
                if not content.startswith(b"%PDF"):
                    flash(f"{original_name}: file is not a valid PDF.", "error")
                    continue
                digest = hashlib.sha256(content).hexdigest()
                if Resume.query.filter_by(sha256=digest).first():
                    flash(f"{original_name}: this exact file has already been uploaded.", "warning")
                    continue
                try:
                    document = fitz.open(stream=content, filetype="pdf")
                    extracted_text = "\n".join(page.get_text() for page in document).strip()
                    document.close()
                except (fitz.FileDataError, RuntimeError, ValueError):
                    flash(f"{original_name}: the PDF could not be read.", "error")
                    continue
                if not extracted_text:
                    flash(f"{original_name}: no selectable text was found in the PDF.", "warning")
                info = extract_resume_information(extracted_text)
                candidate = Candidate(
                    name=info["name"], email=info["email"], phone=info["phone"],
                    education=info["education"], experience_years=info["experience_years"],
                    experience_summary=info["experience_summary"], projects=info["projects"],
                    certifications=info["certifications"],
                )
                candidate.skills.extend(CandidateSkill(name=skill) for skill in info["skills"])
                stored_name = f"{uuid.uuid4().hex}_{secure_filename(original_name)}"
                stored_path = UPLOAD_DIR / stored_name
                UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
                stored_path.write_bytes(content)
                resume = Resume(
                    filename=secure_filename(original_name) or "resume.pdf",
                    stored_path=str(stored_path.relative_to(BASE_DIR)),
                    sha256=digest,
                    extracted_text=extracted_text,
                    extraction_status="Processed" if extracted_text else "No text found",
                )
                candidate.resumes.append(resume)
                application = CandidateApplication(candidate=candidate, vacancy=vacancy)
                db.session.add(application)
                db.session.flush()
                _save_score(application)
                accepted += 1
            db.session.commit()
            if accepted:
                flash(f"Processed {accepted} resume{'s' if accepted != 1 else ''}. Review extracted details for accuracy.", "success")
        return redirect(url_for("resumes", vacancy_id=vacancy_id or ""))

    vacancy_id = request.args.get("vacancy_id", type=int)
    query = Resume.query.join(Candidate).order_by(Resume.uploaded_at.desc())
    if vacancy_id:
        query = query.join(CandidateApplication).filter(CandidateApplication.vacancy_id == vacancy_id)
    return render_template(
        "resumes.html",
        resumes=query.all(),
        vacancies=Vacancy.query.order_by(Vacancy.title).all(),
        selected_vacancy=vacancy_id,
    )


@app.route("/resumes/<int:resume_id>/download")
@login_required
def resume_download(resume_id):
    resume = db.get_or_404(Resume, resume_id)
    path = (BASE_DIR / resume.stored_path).resolve()
    if not path.is_relative_to(UPLOAD_DIR.resolve()) or not path.is_file():
        abort(404)
    return send_file(path, as_attachment=True, download_name=resume.filename)


@app.route("/candidates")
@login_required
def candidates():
    query = _application_query()
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    vacancy_id = request.args.get("vacancy_id", type=int)
    if search:
        query = query.filter(or_(Candidate.name.ilike(f"%{search}%"), Candidate.email.ilike(f"%{search}%")))
    if status in ALLOWED_STATUSES:
        query = query.filter(CandidateApplication.status == status)
    if vacancy_id:
        query = query.filter(CandidateApplication.vacancy_id == vacancy_id)
    rows = query.order_by(Candidate.created_at.desc()).all()
    return render_template(
        "candidates.html", applications=rows, vacancies=Vacancy.query.order_by(Vacancy.title).all(),
        search=search, selected_status=status, selected_vacancy=vacancy_id,
    )


@app.route("/candidate-validation")
@login_required
def candidate_validation_page():
    applications = _application_query().order_by(CandidateApplication.created_at.desc()).all()
    reports_by_pair = {}
    for saved_report in CandidateValidation.query.all():
        report_data = json.loads(saved_report.report)
        report_data["generated_at_display"] = saved_report.generated_at
        reports_by_pair[(saved_report.candidate_id, saved_report.vacancy_id)] = report_data
    validation_reports = {
        application.id: reports_by_pair.get(
            (application.candidate_id, application.vacancy_id)
        )
        for application in applications
    }
    return render_template(
        "candidate_validation.html",
        applications=applications,
        validation_reports=validation_reports,
    )


@app.route("/candidates/<int:candidate_id>")
@login_required
def candidate_details(candidate_id):
    candidate = db.get_or_404(Candidate, candidate_id)
    application_id = request.args.get("application_id", type=int)
    applications = CandidateApplication.query.filter_by(candidate_id=candidate_id).all()
    application = next((item for item in applications if item.id == application_id), None)
    if application is None:
        application = applications[0] if applications else None
    explanation = json.loads(application.score.explanation) if application and application.score else {}
    validation = (
        CandidateValidation.query.filter_by(
            candidate_id=candidate.id, vacancy_id=application.vacancy_id
        ).first()
        if application else None
    )
    validation_report = json.loads(validation.report) if validation else None
    if not isinstance(validation_report, dict) or validation_report.get("schema_version") != 2:
        validation_report = None
    return render_template(
        "candidate_details.html", candidate=candidate, application=application,
        applications=applications, explanation=explanation,
        validation_report=validation_report,
    )


@app.post("/api/applications/<int:application_id>/validate")
@login_required
def validate_candidate(application_id):
    application = db.get_or_404(CandidateApplication, application_id)
    resume = (
        Resume.query.filter_by(candidate_id=application.candidate_id)
        .order_by(Resume.uploaded_at.desc(), Resume.id.desc())
        .first()
    )
    report = build_validation_report(
        resume.extracted_text if resume else "",
        application.candidate,
        application.vacancy,
    )
    validation = CandidateValidation.query.filter_by(
        candidate_id=application.candidate_id,
        vacancy_id=application.vacancy_id,
    ).first()
    if validation is None:
        validation = CandidateValidation(
            candidate_id=application.candidate_id,
            vacancy_id=application.vacancy_id,
            report="{}",
        )
        db.session.add(validation)
    validation.report = json.dumps(report)
    validation.generated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.session.commit()
    return jsonify(report=report)


@app.post("/candidates/<int:candidate_id>/edit")
@login_required
def candidate_edit(candidate_id):
    candidate = db.get_or_404(Candidate, candidate_id)
    candidate.name = request.form.get("name", "").strip() or "Unidentified candidate"
    entered_email = request.form.get("email", "").strip()
    normalized_email = _normalized_email(entered_email) if entered_email else ""
    if entered_email and not normalized_email:
        flash("Enter a valid email address or leave the field blank.", "error")
        return redirect(url_for("candidate_details", candidate_id=candidate_id))
    candidate.email = normalized_email
    candidate.phone = request.form.get("phone", "").strip()
    candidate.education = request.form.get("education", "").strip()
    raw_experience = request.form.get("experience_years", "").strip()
    try:
        candidate.experience_years = float(raw_experience) if raw_experience else None
    except ValueError:
        flash("Experience must be a number of years.", "error")
        return redirect(url_for("candidate_details", candidate_id=candidate_id))
    if candidate.experience_years is not None and (
        not math.isfinite(candidate.experience_years) or candidate.experience_years < 0
    ):
        flash("Experience cannot be negative.", "error")
        return redirect(url_for("candidate_details", candidate_id=candidate_id))
    candidate.experience_summary = request.form.get("experience_summary", "").strip()
    candidate.projects = request.form.get("projects", "").strip()
    candidate.certifications = request.form.get("certifications", "").strip()
    for skill in list(candidate.skills):
        db.session.delete(skill)
    db.session.flush()
    unique_skills = {}
    for name in _csv_list(request.form.get("skills")):
        unique_skills.setdefault(name.casefold(), name)
    candidate.skills.extend(CandidateSkill(name=name) for name in unique_skills.values())
    for application in candidate.applications:
        _save_score(application)
    db.session.commit()
    flash("Candidate information and matching scores were updated.", "success")
    return redirect(url_for("candidate_details", candidate_id=candidate_id))


@app.post("/applications/<int:application_id>/status")
@login_required
def application_status(application_id):
    application = db.get_or_404(CandidateApplication, application_id)
    status = request.form.get("status", "")
    if status not in ALLOWED_STATUSES:
        abort(400)
    if status != application.status:
        previous = application.status
        application.status = status
        application.status_history.append(
            ApplicationStatusHistory(old_status=previous, new_status=status)
        )
        db.session.commit()
        flash("Candidate status updated.", "success")
    referrer = request.referrer
    if referrer:
        parsed = urlsplit(referrer)
        if parsed.scheme in {"http", "https"} and parsed.netloc == request.host:
            return redirect(referrer)
    return redirect(url_for("candidates"))


@app.route("/rankings")
@login_required
def rankings():
    query = _application_query()
    vacancy_id = request.args.get("vacancy_id", type=int)
    status = request.args.get("status", "")
    min_score = request.args.get("min_score", type=float)
    min_experience = request.args.get("min_experience", type=float)
    max_experience = request.args.get("max_experience", type=float)
    skill = request.args.get("skill", "").strip()
    if vacancy_id:
        query = query.filter(CandidateApplication.vacancy_id == vacancy_id)
    if status in ALLOWED_STATUSES:
        query = query.filter(CandidateApplication.status == status)
    if min_score is not None:
        query = query.filter(CandidateScore.final_score >= max(0, min(100, min_score)))
    if min_experience is not None:
        query = query.filter(Candidate.experience_years >= max(0, min_experience))
    if max_experience is not None:
        query = query.filter(Candidate.experience_years <= max(0, max_experience))
    rows = query.order_by(CandidateScore.final_score.desc().nullslast(), Candidate.created_at.desc()).all()
    if skill:
        rows = [row for row in rows if any(skill.casefold() in item.name.casefold() for item in row.candidate.skills)]
    return render_template(
        "rankings.html", applications=rows, vacancies=Vacancy.query.order_by(Vacancy.title).all(),
        selected_vacancy=vacancy_id, selected_status=status, min_score=min_score, skill=skill,
        min_experience=min_experience, max_experience=max_experience,
    )


@app.get("/interviews")
@login_required
def interviews():
    questions = InterviewQuestion.query.order_by(InterviewQuestion.created_at.desc()).limit(100).all()
    return render_template(
        "interviews.html",
        vacancies=Vacancy.query.order_by(Vacancy.title).all(),
        questions=questions,
        question_categories=QUESTION_CATEGORIES,
    )


def _interview_question_data(question):
    return {
        "id": question.id,
        "vacancy_id": question.vacancy_id,
        "candidate_id": question.candidate_id,
        "candidate": question.candidate.name,
        "vacancy": question.vacancy.title,
        "category": question.category,
        "question": question.question,
        "difficulty": question.difficulty,
        "generated_at": question.created_at.isoformat(),
    }


def _interview_form_ids(payload):
    if not isinstance(payload, dict):
        return None

    def parse_id(value):
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdecimal():
            return int(value)
        return None

    vacancy_id = parse_id(payload.get("vacancy_id"))
    candidate_id = parse_id(payload.get("candidate_id"))
    if vacancy_id is None or candidate_id is None:
        return None
    return (vacancy_id, candidate_id) if vacancy_id > 0 and candidate_id > 0 else None


@app.post("/api/interview-questions/generate")
@login_required
def generate_interview_questions():
    payload = request.get_json(silent=True)
    identifiers = _interview_form_ids(payload)
    if identifiers is None:
        return jsonify(error="Select a vacancy and shortlisted candidate."), 400
    vacancy_id, candidate_id = identifiers
    vacancy = db.session.get(Vacancy, vacancy_id)
    if vacancy is None:
        return jsonify(error="The selected vacancy was not found."), 404
    if not vacancy.title.strip() or not any(
        (value or "").strip()
        for value in (vacancy.description, vacancy.required_skills, vacancy.preferred_skills)
    ):
        return jsonify(error="The selected vacancy has no description or skill requirements."), 400
    candidate = db.session.get(Candidate, candidate_id)
    if candidate is None:
        return jsonify(error="The selected candidate was not found."), 404
    application = CandidateApplication.query.filter_by(
        vacancy_id=vacancy_id, candidate_id=candidate_id, status="Shortlisted"
    ).first()
    if application is None:
        return jsonify(error="Select a candidate shortlisted for this vacancy."), 400
    if not (
        candidate.skills
        or candidate.experience_summary.strip()
        or candidate.projects.strip()
        or candidate.experience_years is not None
    ):
        return jsonify(
            error="The candidate profile has no saved skills, experience, or projects."
        ), 400

    difficulty = payload.get("difficulty")
    count = payload.get("count")
    if not isinstance(difficulty, str) or difficulty not in {
        "Beginner", "Intermediate", "Advanced"
    }:
        return jsonify(error="Choose a valid difficulty level."), 400
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 25:
        return jsonify(error="Choose a number of questions between 1 and 25."), 400

    candidate_experience = candidate.experience_summary
    if candidate.experience_years is not None:
        candidate_experience = (
            f"{candidate.experience_years:g} years. {candidate_experience}".strip()
        )
    try:
        result = generate_questions(
            job_title=vacancy.title,
            job_description=vacancy.description,
            required_skills=vacancy.required_skills,
            preferred_skills=vacancy.preferred_skills,
            candidate_skills=[skill.name for skill in candidate.skills],
            candidate_experience=candidate_experience,
            candidate_projects=candidate.projects,
            difficulty=difficulty,
            count=count,
            candidate_identifiers=[candidate.name, candidate.email, candidate.phone],
        )
    except InterviewGenerationError as error:
        app.logger.warning(
            "Interview question generation failed (status=%s)", error.status_code
        )
        return jsonify(error=str(error)), error.status_code
    return jsonify(
        vacancy_id=vacancy.id,
        candidate_id=candidate.id,
        difficulty=difficulty,
        questions=result["questions"],
    )


@app.post("/api/interview-questions/save")
@login_required
def save_interview_questions():
    payload = request.get_json(silent=True)
    identifiers = _interview_form_ids(payload)
    if identifiers is None:
        return jsonify(error="Select a vacancy and shortlisted candidate."), 400
    vacancy_id, candidate_id = identifiers
    application = CandidateApplication.query.filter_by(
        vacancy_id=vacancy_id, candidate_id=candidate_id, status="Shortlisted"
    ).first()
    if application is None:
        return jsonify(error="Select a candidate shortlisted for this vacancy."), 400

    difficulty = payload.get("difficulty")
    questions = payload.get("questions")
    if not isinstance(difficulty, str) or difficulty not in {
        "Beginner", "Intermediate", "Advanced"
    }:
        return jsonify(error="Choose a valid difficulty level."), 400
    if not isinstance(questions, list) or not 1 <= len(questions) <= 25:
        return jsonify(error="There are no valid generated questions to save."), 400

    validated = []
    for item in questions:
        if not isinstance(item, dict):
            return jsonify(error="A generated question has an invalid format."), 400
        category = item.get("category")
        question = item.get("question")
        if (
            category not in QUESTION_CATEGORIES
            or not isinstance(question, str)
            or not question.strip()
            or len(question.strip()) > 2000
        ):
            return jsonify(error="A generated question has an invalid category or text."), 400
        validated.append(
            InterviewQuestion(
                vacancy_id=vacancy_id,
                candidate_id=candidate_id,
                application_id=application.id,
                category=category,
                question=question.strip(),
                difficulty=difficulty,
            )
        )

    db.session.add_all(validated)
    db.session.commit()
    return jsonify(
        message=f"Saved {len(validated)} interview questions.",
        questions=[_interview_question_data(question) for question in validated],
    ), 201


@app.get("/api/interview-questions")
@login_required
def saved_interview_questions():
    query = InterviewQuestion.query
    vacancy_id = request.args.get("vacancy_id", type=int)
    candidate_id = request.args.get("candidate_id", type=int)
    if vacancy_id:
        query = query.filter_by(vacancy_id=vacancy_id)
    if candidate_id:
        query = query.filter_by(candidate_id=candidate_id)
    questions = query.order_by(InterviewQuestion.created_at.desc()).limit(100).all()
    return jsonify(questions=[_interview_question_data(question) for question in questions])


@app.route("/api/vacancies/<int:vacancy_id>/shortlisted")
@login_required
def shortlisted_candidates(vacancy_id):
    applications = CandidateApplication.query.filter_by(
        vacancy_id=vacancy_id, status="Shortlisted"
    ).order_by(CandidateApplication.created_at.desc()).all()
    return {
        "applications": [
            {
                "id": item.candidate.id,
                "candidate_id": item.candidate.id,
                "application_id": item.id,
                "candidate": item.candidate.name,
                "email": item.candidate.email,
            }
            for item in applications
        ]
    }


@app.errorhandler(413)
def request_too_large(_error):
    flash("The upload exceeds the 16 MB request limit.", "error")
    return redirect(url_for("resumes")), 303


with app.app_context():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    db.create_all()
    interview_columns = {
        column["name"] for column in inspect(db.engine).get_columns("interview_questions")
    }
    with db.engine.begin() as connection:
        if "vacancy_id" not in interview_columns:
            connection.exec_driver_sql(
                "ALTER TABLE interview_questions ADD COLUMN "
                "vacancy_id INTEGER REFERENCES vacancies(id) ON DELETE CASCADE"
            )
        if "candidate_id" not in interview_columns:
            connection.exec_driver_sql(
                "ALTER TABLE interview_questions ADD COLUMN "
                "candidate_id INTEGER REFERENCES candidates(id) ON DELETE CASCADE"
            )
        connection.exec_driver_sql(
            "UPDATE interview_questions SET vacancy_id = "
            "(SELECT vacancy_id FROM candidate_applications "
            "WHERE candidate_applications.id = interview_questions.application_id) "
            "WHERE vacancy_id IS NULL"
        )
        connection.exec_driver_sql(
            "UPDATE interview_questions SET candidate_id = "
            "(SELECT candidate_id FROM candidate_applications "
            "WHERE candidate_applications.id = interview_questions.application_id) "
            "WHERE candidate_id IS NULL"
        )
    if "user" in inspect(db.engine).get_table_names():
        db.session.execute(
            text(
                'INSERT OR IGNORE INTO users (id, name, email, password_hash, created_at) '
                'SELECT id, name, email, password_hash, created_at FROM "user"'
            )
        )
        db.session.commit()
if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
