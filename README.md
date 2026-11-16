# HireRank

HireRank is a Flask-based recruitment and hiring dashboard for managing vacancies, uploading resumes, scoring candidates, and generating interview questions using AI.

It helps hiring teams:
- create and track job openings
- upload and parse PDF resumes
- extract candidate information and skills
- compare applicants against job requirements
- validate candidate fit against a vacancy
- shortlist candidates and generate interview questions

## Tech Stack

- Python 3.11+
- Flask
- Flask-SQLAlchemy
- Flask-Login
- Flask-WTF
- SQLite
- PyMuPDF for PDF parsing
- scikit-learn / NumPy / Pandas for matching and scoring
- Google GenAI for interview question generation

## Features

### Vacancy management
- Add, edit, deactivate, and delete job openings
- Store role requirements, education, experience range, and preferred skills
- Track active vs inactive vacancies

### Resume intake and extraction
- Upload multiple PDF resumes at once
- Validate file format and size
- Extract text from PDFs using PyMuPDF
- Clean extracted text and identify candidate name, email, phone, skills, education, work experience, projects, and certifications
- Configure technical skill terms in `skills.json`
- Keep the original uploaded PDF available for recruiter review

### Candidate matching
- Compare resume and vacancy text using TF-IDF and cosine similarity
- Calculate separate 0–100 components for description similarity, required skills, experience, education, and preferred skills
- Combine components using configurable weights (defaults: 35%, 30%, 20%, 10%, and 5%)
- Show matched/missing skills, requirement counts, and experience/education explanations
- Rank candidates by the stored weighted score

### Candidate validation
- Generate structured, vacancy-specific reports from resume evidence
- Flag missing details, unsupported skill mentions, inconsistencies, and possible duplicate profiles
- Use `Passed`, `Needs Review`, and `Warning` statuses as decision support; candidates are never automatically rejected

### Account data isolation
- Associate vacancies and candidate profiles with the signed-in HR account
- Scope candidate, resume, vacancy, interview, and dashboard queries to that account
- Preserve legacy database records; automatically assign them only when the database contains exactly one HR account

### Interview preparation
- Generate role-specific interview questions for shortlisted candidates
- Support multiple difficulty levels: Beginner, Intermediate, and Advanced
- Include technical, practical, scenario-based, and experience-based questions
- Save generated questions to the database for reuse
- Keep the Gemini key on the server and show API failures in the UI

## Project Structure

```text
HireRank/
├── app.py                     # Main Flask app and routes
├── database.py               # SQLAlchemy models
├── candidate_validation.py    # Candidate validation logic
├── ml_engine.py              # Resume extraction and candidate scoring
├── interview_ai.py           # AI-powered interview question generation
├── skills.json               # Configurable technical skills
├── requirements.txt          # Python dependencies
├── hirerank.db               # SQLite database
├── .env.example              # Sample environment configuration
├── static/                   # CSS/JS assets
├── templates/                # Flask HTML templates
├── uploads/resumes/          # Stored uploaded resume PDFs
├── tests/                    # Automated tests
└── README.md                 # Project documentation
```

## Prerequisites

Before running the app, make sure you have:

- Python 3.11 or newer
- pip
- A valid Google Gemini API key if you want AI-generated interview questions

## Installation

1. Clone the repository

```bash
git clone <your-repository-url>
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

4. Set up environment variables

Create a `.env` file from the sample:

```bash
cp .env.example .env
```

Then update `.env` with your values:

```env
SECRET_KEY=your-long-random-secret
GEMINI_API_KEY=your_google_gemini_api_key
```

Optional settings:

```env
# JSON weights must use these exact keys and sum to 1.0.
HIRERANK_SCORING_WEIGHTS='{"description_similarity":0.35,"required_skills":0.30,"experience_match":0.20,"education_match":0.10,"preferred_skills":0.05}'
# Use a custom JSON skill dictionary if desired.
HIRERANK_SKILLS_FILE=skills.json
```

## Running the App

Start the app in development mode:

```bash
python app.py
```

The app will run by default at:

```text
http://localhost:5000
```

You can also run it with Flask directly:

```bash
export FLASK_APP=app.py
flask run
```

## First-Time Usage

1. Open the app in your browser.
2. Register a recruiter account.
3. Create a vacancy.
4. Upload candidate resumes for that vacancy.
5. Review extracted candidate details and rankings.
6. Validate applicants and shortlist the best matches.
7. Generate interview questions for shortlisted candidates.

## Notes

- Uploaded files are validated for PDF type and size before processing.
- Resume extraction and scoring are performed automatically after upload; extracted details and matching scores should be reviewed by HR.
- Interview question generation depends on the configured Gemini API key.
- The app stores data in SQLite and applies additive, backward-compatible schema updates at startup.
- If a database has multiple HR accounts and ownerless legacy records, those records remain preserved but hidden until explicitly assigned.
## Tests

Run the automated test suite with:

```bash
python -m unittest discover -s tests -v
```

## License

This project is currently unlicensed unless you explicitly add a license file or update this section.

## Contributing

Pull requests and improvements are welcome. For larger changes, please open an issue first to discuss the approach.
