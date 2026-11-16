# HireRank — Complete Project Details

## 1. Project Overview

HireRank is a full-stack recruitment management web application designed for hiring teams to streamline resume screening, candidate evaluation, vacancy management, and interview preparation. The application helps recruiters handle the end-to-end hiring process from job posting to final shortlisting.

The system allows HR users to:
- create and manage job vacancies
- upload candidate resumes in bulk
- parse resume content automatically
- clean and preprocess text extracted from PDFs
- extract key candidate information
- match candidates against open positions
- validate candidate profiles with explainable, advisory evidence checks
- shortlist the best applicants
- generate intelligent interview questions for shortlisted candidates
- evaluate ranking, extraction, and duplicate detection from human-reviewed annotations

This project is built with Python and Flask, and uses SQLite as the database. It is meant to be a practical recruitment dashboard suitable for startups, HR teams, or internal hiring workflows.

---

## 2. Problem It Solves

Recruiting teams often struggle with:
- manual tracking of vacancies and applicants
- repetitive resume review work
- inconsistent comparison of candidates against job requirements
- difficulty ranking applicants based on skills and experience
- lack of structured evaluation before interviews

HireRank addresses these pain points by centralizing hiring data and automating candidate screening and matching.

---

## 3. Key Features

### 3.1 User Authentication
- Recruiter registration and login
- Secure password hashing with Werkzeug
- Session-based authentication using Flask-Login
- Role-based access to recruiter-only pages

### 3.2 Vacancy Management
- Add new job vacancies
- Edit vacancy details
- Activate or deactivate roles
- Delete vacancies if no longer needed
- Store:
  - title
  - department
  - location
  - employment type
  - required skills
  - preferred skills
  - education requirements
  - job description
  - responsibilities
  - experience range
  - status

### 3.3 Resume Upload and Processing
- Upload multiple PDF resumes at once
- Validate:
  - file type
  - file size
  - valid PDF structure
- Prevent duplicate uploads using SHA-256 checksum
- Extract text from PDFs using PyMuPDF
- Recognize candidate details such as:
  - name
  - email
  - phone number
  - education
  - years of experience
  - summary
  - projects
  - certifications
  - skills
- Maintain the original uploaded PDF for review
- Configure the technical skill vocabulary in `skills.json`

### 3.4 Candidate Matching and Scoring
The application compares resume text with vacancy text using TF-IDF vectorization and cosine similarity. It calculates independent 0–100 component scores and combines them using configurable weights:

| Component | Default weight |
|---|---:|
| Job description similarity | 35% |
| Required skills match | 30% |
| Experience match | 20% |
| Education match | 10% |
| Preferred skills match | 5% |

Duplicate skill requirements are counted once. Candidate profiles show matched/missing skills, counts, requirement status, and the score weights used. When a vacancy has no constraint for a component, that component is treated as unconstrained rather than penalizing applicants.

This helps recruiters see the strongest applicants at a glance.

### 3.5 Candidate Validation
- Build a structured validation report per candidate-vacancy pair
- Flag missing information, skills without project/experience evidence, profile discrepancies, and possible duplicate profiles
- Report `Passed`, `Needs Review`, or `Warning` with explanations and source context
- Treat every warning as a prompt for human review; validation never rejects a candidate
- Compare potential duplicate profiles only within the signed-in HR account

### 3.6 Candidate Dashboard and Detail Views
- Browse all candidates and their applications
- Search by name or email
- Filter by status and vacancy
- View detailed resume-derived candidate information
- Edit candidate info manually when needed
- Review score explanations and evaluation details

### 3.7 Application Status Tracking
- Candidate applications can move through statuses such as:
  - Applied
  - Under Review
  - Shortlisted
  - Selected
  - Rejected
- Status updates are tracked in status history

### 3.8 Interview Question Generation
- Generate interview questions based on:
  - role title
  - job description
  - required skills
  - preferred skills
  - candidate skills
  - experience summary
  - projects
  - skill level difficulty
- Supports difficulty settings:
  - Beginner
  - Intermediate
  - Advanced
- Saves generated questions to the database for future reference
- Requires technical, practical, and experience-based coverage for question sets of three or more
- Sends candidate experience/project text as untrusted evidence and redacts contact identifiers before API requests

### 3.9 HR Account Isolation
- Vacancies and candidate profiles are associated with the authenticated HR account
- Queries and resume downloads are scoped to that account
- Legacy unowned records are assigned automatically only if exactly one HR account exists; otherwise they remain preserved and hidden

---

## 4. Architecture

### 4.1 Frontend
The app uses:
- Flask templates
- HTML
- CSS
- JavaScript

Templates are stored in the `templates/` folder, and static assets are stored in `static/`.

### 4.2 Backend
The backend is powered by:
- Flask
- Flask-SQLAlchemy for ORM and database handling
- Flask-Login for user authentication
- Flask-WTF for CSRF protection

### 4.3 Data Layer
The project uses SQLite via the file:
- `hirerank.db`

Database models include:
- `User`
- `Vacancy`
- `Candidate`
- `Resume`
- `CandidateSkill`
- `CandidateApplication`
- `CandidateScore`
- `InterviewQuestion`
- `ApplicationStatusHistory`
- `CandidateValidation`

### 4.4 Core Modules
- `app.py` — main Flask application and routes
- `database.py` — database schema and ORM models
- `ml_engine.py` — resume extraction and candidate score generation
- `candidate_validation.py` — validation logic for candidate-job fit
- `interview_ai.py` — AI-based question generation

---

## 5. Main Workflow

A typical recruiter workflow in HireRank is:

1. Register or log in as a recruiter.
2. Create one or more vacancies.
3. Upload resumes for a selected active vacancy.
4. System parses the PDF, extracts candidate data, and stores the resume.
5. Candidate is matched against the role based on skills, background, and experience.
6. Final score is computed and saved.
7. Recruiter reviews the candidate details and validation report.
8. Update status to Under Review, Shortlisted, Selected, or Rejected.
9. Generate interview questions for shortlisted candidates.
10. Save and reuse interview questions for later review.

---

## 6. Project Structure

```text
HireRank/
├── app.py
├── database.py
├── candidate_validation.py
├── ml_engine.py
├── interview_ai.py
├── skills.json
├── requirements.txt
├── .env
├── .env.example
├── .gitignore
├── hirerank.db
├── README.md
├── PROJECT_DETAILS.md
├── static/
│   ├── css/
│   ├── images/
│   └── js/
├── templates/
│   ├── base.html
│   ├── candidate_details.html
│   ├── candidate_validation.html
│   ├── candidates.html
│   ├── create_vacancy.html
│   ├── dashboard.html
│   ├── interviews.html
│   ├── login.html
│   ├── rankings.html
│   ├── register.html
│   ├── resumes.html
│   ├── vacancies.html
├── uploads/
│   └── resumes/
├── tests/
│   ├── test_candidate_validation.py
│   ├── test_interview_ai.py
│   ├── test_ml_engine.py
│   └── test_ownership.py
```

---

## 7. Technology Stack

### Backend
- Python 3.11+
- Flask
- Flask-SQLAlchemy
- Flask-Login
- Flask-WTF
- SQLite

### NLP / Data / ML
- PyMuPDF
- NumPy
- Pandas
- scikit-learn
- NLTK

### AI / External Services
- Google GenAI
- Gemini API integration for generating interview questions

### Security and Validation
- Werkzeug password hashing
- Email validation
- file upload validation
- CSRF protection

---

## 8. Environment Configuration

The app uses environment variables for configuration.

### Sample file
- `.env.example`

### Example values
```env
SECRET_KEY=replace-this-with-a-long-random-secret
GEMINI_API_KEY=your_google_gemini_api_key
```

### Important note
- `SECRET_KEY` should be a strong random secret in production.
- `GEMINI_API_KEY` is required for AI-powered interview question generation.

---

## 9. Installation Guide

### Prerequisites
- Python 3.11 or newer
- pip
- virtual environment support

### Steps

1. Clone the project
```bash
git clone <repository-url>
cd HireRank
```

2. Create a virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

4. Create environment file
```bash
cp .env.example .env
```

5. Update the `.env` file with your secret key and API key

6. Run the app
```bash
python app.py
```

The application will start on:
```text
http://localhost:5000
```

---

## 10. Usage Instructions

### Recruiter Registration
- Open the app in browser
- Register an HR account
- Log into the system

### Vacancy Setup
- Navigate to the vacancies page
- Create a role with required skills, experience, and job description

### Resume Upload
- Select an active vacancy
- Upload one or more PDF resumes
- Wait for automated extraction and scoring

### Candidate Review
- Open candidate details
- Check extracted info, skill list, and score explanation
- Validate candidate fit based on vacancy requirements

### Shortlisting
- Change candidate status to Shortlisted or move through the hiring pipeline

### Interview Generation
- Select a vacancy and shortlisted candidate
- Generate interview questions based on difficulty level
- Save generated questions for reuse

---

## 11. Business Value

HireRank adds value by making recruitment faster, more consistent, and more data-driven. It reduces the amount of manual work needed for screening candidates and helps recruiters focus on high-quality applicants instead of spending time on repetitive document review.

It is especially useful for:
- talent acquisition teams
- startups hiring quickly
- internal HR operations
- small to medium recruitment workflows

---

## 12. Current Status

This project is a working recruitment dashboard with core automation features already implemented, including:
- candidate registration and login
- vacancy creation and management
- resume extraction and parsing
- matching and ranking
- validation reports
- interview generation
- isolated HR workspaces for owned records

It is suitable for further enhancement with features such as:
- recruiter email integration
- PDF attachment previews
- analytics dashboards
- hiring pipeline reports
- better AI model tuning
- export to CSV/PDF reports
- administrator roles and permission management

---

## 13. Future Improvements

Possible enhancements for the next version include:
- drag-and-drop resume upload
- detailed recruiter dashboards with charts
- candidate history and analytics
- interview scheduler integration
- advanced scoring model improvements
- exportable reports for hiring managers
- better admin controls and permissions
- company branding and custom UI themes

---

## 14. Summary

HireRank is a practical AI-assisted hiring platform designed to simplify candidate evaluation and recruitment operations. It combines resume parsing, skill extraction, matching logic, validation reports, and AI-powered interview question generation into one web application.

It is a strong project for demonstrating Python web development, database design, document processing, and intelligent hiring automation.

---

## 15. Notes

- The app is configured for local development with SQLite.
- The system automatically creates database tables on first run.
- Some functionality, such as interview question generation, depends on a valid Gemini API key.
- Matching weights can be overridden using `HIRERANK_SCORING_WEIGHTS` with a JSON object whose five values sum to 1.0.
- The skill dictionary can be replaced using `HIRERANK_SKILLS_FILE`.
- Run tests with `python -m unittest discover -s tests -v`.
- This project is intended for practical use and further iterative development.
