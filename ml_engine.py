import re
from typing import Any

from nltk.tokenize import TreebankWordTokenizer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

TOKENIZER = TreebankWordTokenizer()
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "have", "in", "into", "is", "it", "of", "on", "or", "that", "the", "to",
    "was", "were", "will", "with", "you", "your", "we", "our", "this", "their",
}

SKILL_GROUPS = {
    "Programming": ["Python", "Java", "C", "C++", "JavaScript", "PHP"],
    "Databases": ["SQL", "MySQL", "PostgreSQL", "MongoDB", "SQLite"],
    "Machine Learning": [
        "Machine Learning", "Deep Learning", "NLP", "TensorFlow", "PyTorch",
        "Scikit-learn", "scikit learn",
    ],
    "Web Development": [
        "HTML", "CSS", "JavaScript", "Flask", "Django", "React", "REST API",
    ],
    "Tools": ["Git", "GitHub", "Docker", "Power BI", "Excel"],
}
SKILL_NAMES = list(dict.fromkeys(skill for values in SKILL_GROUPS.values() for skill in values))
EDUCATION_EQUIVALENCES = {
    "b.tech": ("b.tech", "btech", "b.e", "be", "bachelor", "engineering"),
    "b.e.": ("b.e", "be", "b.tech", "btech", "bachelor", "engineering"),
    "m.tech": ("m.tech", "mtech", "m.e", "me", "master", "postgraduate"),
    "mca": ("mca", "master", "postgraduate"),
    "bca": ("bca", "bachelor", "undergraduate"),
    "mba": ("mba", "master", "postgraduate"),
}


def normalize_text(text: str) -> str:
    tokens = TOKENIZER.tokenize((text or "").lower())
    return " ".join(
        token for token in tokens
        if token not in STOPWORDS and re.search(r"[a-z0-9]", token)
    )


def text_similarity(first_text: str, second_text: str) -> float:
    normalized_first = normalize_text(first_text)
    normalized_second = normalize_text(second_text)
    if not normalized_first or not normalized_second:
        return 0.0
    try:
        vectors = TfidfVectorizer(token_pattern=r"(?u)\b\w+\b").fit_transform(
            [normalized_first, normalized_second]
        )
    except ValueError:
        return 0.0
    return float(cosine_similarity(vectors[0:1], vectors[1:2])[0][0] * 100)


def extract_skills(text: str) -> list[str]:
    normalized = (text or "").lower()
    found = []
    for skill in SKILL_NAMES:
        pattern = rf"(?<![a-z0-9]){re.escape(skill.lower())}(?![a-z0-9])"
        if re.search(pattern, normalized):
            canonical = "Scikit-learn" if skill == "scikit learn" else skill
            if canonical not in found:
                found.append(canonical)
    return found


def extract_resume_information(text: str) -> dict[str, Any]:
    lines = [re.sub(r"\s+", " ", line).strip(" |•\t") for line in (text or "").splitlines()]
    lines = [line for line in lines if line]
    email_match = re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text or "", re.I)
    phone_match = re.search(r"(?<!\w)(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,5}\)?[\s.-]?)?\d{5}[\d\s.-]{3,}\d(?!\w)", text or "")
    name = ""
    for line in lines[:12]:
        if "@" in line or re.search(r"\d", line) or len(line) > 70:
            continue
        words = line.split()
        if 2 <= len(words) <= 5 and all(re.fullmatch(r"[A-Za-z][A-Za-z'.-]*", word) for word in words):
            name = line.title()
            break
    exp_match = re.search(
        r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:professional\s+)?experience",
        text or "", re.I,
    )
    experience_years = float(exp_match.group(1)) if exp_match else None
    education_lines = [
        line for line in lines
        if re.search(r"\b(B\.?\s?Tech|B\.?\s?E\.?|BCA|MCA|M\.?\s?Tech|M\.?\s?E\.?|B\.?\s?Sc|M\.?\s?Sc|MBA|bachelor|master|degree|diploma|university)\b", line, re.I)
    ]
    projects = _section_text(lines, ("projects", "project experience"), ("education", "certification", "skills", "experience"))
    certifications = _section_text(lines, ("certifications", "certificates"), ("projects", "education", "skills", "experience"))
    return {
        "name": name or "Unidentified candidate",
        "email": email_match.group(0) if email_match else "",
        "phone": re.sub(r"\s+", " ", phone_match.group(0)).strip() if phone_match else "",
        "skills": extract_skills(text or ""),
        "education": "\n".join(education_lines[:8]),
        "experience_years": experience_years,
        "experience_summary": exp_match.group(0) if exp_match else "",
        "projects": projects,
        "certifications": certifications,
    }


def _section_text(lines: list[str], headings: tuple[str, ...], stop_headings: tuple[str, ...]) -> str:
    start = None
    for index, line in enumerate(lines):
        if any(heading in line.lower() for heading in headings):
            start = index + 1
            break
    if start is None:
        return ""
    selected = []
    for line in lines[start:]:
        if any(heading in line.lower() for heading in stop_headings):
            break
        selected.append(line)
        if len(selected) == 10:
            break
    return "\n".join(selected)


def _skill_score(candidate_skills: list[str], vacancy_skills: list[str]) -> tuple[float, list[str], list[str]]:
    requested = [skill.strip() for skill in vacancy_skills if skill.strip()]
    if not requested:
        return 0.0, [], []
    candidate_lookup = {skill.casefold() for skill in candidate_skills}
    matched = [skill for skill in requested if skill.casefold() in candidate_lookup]
    missing = [skill for skill in requested if skill.casefold() not in candidate_lookup]
    return 100 * len(matched) / len(requested), matched, missing


def _education_match(candidate_education: str, required_education: str) -> float:
    required = [part.strip().lower() for part in re.split(r"[,;\n]", required_education) if part.strip()]
    if not required:
        return 100.0
    candidate = (candidate_education or "").lower()
    if not candidate:
        return 0.0
    for qualification in required:
        options = EDUCATION_EQUIVALENCES.get(qualification, (qualification,))
        if any(option in candidate for option in options):
            return 100.0
    return 0.0


def calculate_match(resume_text: str, candidate: Any, vacancy: Any) -> dict[str, Any]:
    vacancy_text = " ".join(
        (vacancy.description or "", vacancy.responsibilities or "", vacancy.title or "")
    ).strip()
    description_score = text_similarity(resume_text, vacancy_text)

    skills = [item.name for item in candidate.skills]
    required_score, matched_required, missing_required = _skill_score(
        skills, (vacancy.required_skills or "").split(",")
    )
    preferred_score, matched_preferred, missing_preferred = _skill_score(
        skills, (vacancy.preferred_skills or "").split(",")
    )
    years = candidate.experience_years
    minimum = max(0.0, float(vacancy.min_experience or 0))
    maximum = max(minimum, float(vacancy.max_experience or 0))
    if years is None:
        experience_score = 0.0
    elif years >= minimum:
        experience_score = 100.0
    elif minimum > 0:
        experience_score = max(0.0, min(100.0, years / minimum * 100))
    else:
        experience_score = 100.0
    education_score = _education_match(candidate.education, vacancy.education or "")

    final_score = (
        description_score * 0.35
        + required_score * 0.30
        + experience_score * 0.20
        + education_score * 0.10
        + preferred_score * 0.05
    )
    return {
        "description_similarity": round(description_score, 2),
        "required_skills": round(required_score, 2),
        "experience_match": round(experience_score, 2),
        "education_match": round(education_score, 2),
        "preferred_skills": round(preferred_score, 2),
        "final_score": round(max(0.0, min(100.0, final_score)), 2),
        "explanation": {
            "matched_required_skills": matched_required,
            "missing_required_skills": missing_required,
            "matched_preferred_skills": matched_preferred,
            "missing_preferred_skills": missing_preferred,
            "experience_years": years,
            "required_experience": {"minimum": minimum, "maximum": maximum},
            "education_found": candidate.education or "",
            "education_required": vacancy.education or "",
            "notes": [
                "Missing resume evidence receives no points for that criterion.",
                "No listed education requirement is treated as unconstrained (100%).",
                "Experience above the listed range is not penalized.",
            ],
        },
    }
