import json
import math
import os
import re
import unicodedata
from pathlib import Path
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

DEFAULT_SKILLS_PATH = Path(__file__).resolve().with_name("skills.json")


def load_skill_dictionary(path: str | Path | None = None) -> dict[str, list[str]]:
    skills_path = Path(path or os.getenv("HIRERANK_SKILLS_FILE", DEFAULT_SKILLS_PATH))
    with skills_path.open(encoding="utf-8") as skills_file:
        groups = json.load(skills_file)
    if not isinstance(groups, dict) or not groups:
        raise ValueError(f"Skill dictionary must be a non-empty JSON object: {skills_path}")
    validated = {}
    for group, skills in groups.items():
        if (
            not isinstance(group, str)
            or not group.strip()
            or not isinstance(skills, list)
            or not all(isinstance(skill, str) and skill.strip() for skill in skills)
        ):
            raise ValueError(f"Invalid skill group in dictionary: {skills_path}")
        validated[group.strip()] = list(dict.fromkeys(skill.strip() for skill in skills))
    return validated


SKILL_GROUPS = load_skill_dictionary()
SKILL_NAMES = list(dict.fromkeys(skill for values in SKILL_GROUPS.values() for skill in values))
DEFAULT_SCORING_WEIGHTS = {
    "description_similarity": 0.35,
    "required_skills": 0.30,
    "experience_match": 0.20,
    "education_match": 0.10,
    "preferred_skills": 0.05,
}
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


def clean_resume_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", normalized)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in normalized.split("\n")]
    return "\n".join(line for line in lines if line)


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


def extract_skills(text: str, skill_groups: dict[str, list[str]] | None = None) -> list[str]:
    normalized = (text or "").lower()
    found = []
    names = list(dict.fromkeys(
        skill for values in (skill_groups or SKILL_GROUPS).values() for skill in values
    ))
    for skill in names:
        pattern = rf"(?<![\w+#]){re.escape(skill.lower())}(?![\w+#])"
        if re.search(pattern, normalized):
            canonical = "Scikit-learn" if skill.casefold() == "scikit learn" else skill
            if canonical not in found:
                found.append(canonical)
    return found


def extract_resume_information(text: str) -> dict[str, Any]:
    text = clean_resume_text(text)
    lines = [line.strip(" |•\t") for line in text.splitlines()]
    email_match = re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text, re.I)
    phone_match = re.search(
        r"(?<!\w)(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,5}\)?[\s.-]?)?"
        r"\d(?:[\s.-]?\d){7,13}(?!\w)",
        text,
    )
    name = ""
    for line in lines[:12]:
        if (
            "@" in line
            or re.search(r"\d", line)
            or len(line) > 70
            or _is_section_heading(line)
        ):
            continue
        words = line.split()
        if 2 <= len(words) <= 5 and all(re.fullmatch(r"[A-Za-z][A-Za-z'.-]*", word) for word in words):
            name = line.title()
            break
    exp_match = re.search(
        r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:professional\s+)?experience",
        text, re.I,
    )
    experience_years = float(exp_match.group(1)) if exp_match else None
    education_section = _section_text(
        lines, ("education", "academic background", "educational background"),
        ("experience", "projects", "skills", "certification"),
    )
    education_lines = [
        line for line in lines
        if re.search(r"\b(B\.?\s?Tech|B\.?\s?E\.?|BCA|MCA|M\.?\s?Tech|M\.?\s?E\.?|B\.?\s?Sc|M\.?\s?Sc|MBA|bachelor|master|degree|diploma|university)\b", line, re.I)
    ]
    projects = _section_text(
        lines, ("projects", "project experience", "academic projects"),
        ("education", "certification", "skills", "experience"),
    )
    certifications = _section_text(
        lines, ("certifications", "certificates"), ("projects", "education", "skills", "experience"),
    )
    experience = _section_text(
        lines,
        (
            "professional experience", "work experience", "work history",
            "employment history", "internship experience", "experience", "internships",
        ),
        ("education", "projects", "certifications", "skills"),
    )
    education = education_section or "\n".join(dict.fromkeys(education_lines[:8]))
    return {
        "name": name or "Unidentified candidate",
        "email": email_match.group(0) if email_match else "",
        "phone": re.sub(r"\s+", " ", phone_match.group(0)).strip() if phone_match else "",
        "skills": extract_skills(text),
        "education": education,
        "experience_years": experience_years,
        "experience_summary": experience or (exp_match.group(0) if exp_match else ""),
        "projects": projects,
        "certifications": certifications,
    }


def _is_section_heading(line: str) -> bool:
    heading_names = {
        "education", "experience", "work experience", "professional experience",
        "work history", "employment history", "internship experience", "internships",
        "projects", "project experience",
        "academic projects", "skills", "technical skills", "certifications",
        "certificates", "summary", "professional summary", "contact",
    }
    heading = re.sub(r"[^a-z]+", " ", line.casefold()).strip()
    if heading in heading_names:
        return True
    inline_heading = re.split(r"\s*:\s*", line, maxsplit=1)[0]
    normalized_inline = re.sub(r"[^a-z]+", " ", inline_heading.casefold()).strip()
    return ":" in line and normalized_inline in heading_names


def _section_text(lines: list[str], headings: tuple[str, ...], stop_headings: tuple[str, ...]) -> str:
    start = None
    inline_content = ""
    for index, line in enumerate(lines):
        content = _inline_heading_content(line, headings)
        if content is not None:
            start = index + 1
            inline_content = content
            break
        if _is_matching_heading(line, headings):
            start = index + 1
            break
    if start is None:
        return ""
    selected = [inline_content] if inline_content else []
    for line in lines[start:]:
        if _is_section_heading(line) or _is_matching_heading(line, stop_headings):
            break
        selected.append(line)
        if len(selected) == 10:
            break
    return "\n".join(selected)


def _inline_heading_content(line: str, headings: tuple[str, ...]) -> str | None:
    for heading in headings:
        pattern = re.escape(heading).replace(r"\ ", r"\s+")
        match = re.match(rf"^\s*{pattern}\s*:\s*(.*)$", line, re.I)
        if match:
            return match.group(1).strip()
    return None


def _is_matching_heading(line: str, headings: tuple[str, ...]) -> bool:
    normalized = re.sub(r"[^a-z]+", " ", line.casefold()).strip()
    return any(
        normalized == re.sub(r"[^a-z]+", " ", heading.casefold()).strip()
        for heading in headings
    )


def _skill_score(candidate_skills: list[str], vacancy_skills: list[str]) -> tuple[float, list[str], list[str]]:
    requested_by_name = {}
    for skill in vacancy_skills:
        normalized = skill.strip()
        if normalized:
            requested_by_name.setdefault(normalized.casefold(), normalized)
    requested = list(requested_by_name.values())
    if not requested:
        return 100.0, [], []
    candidate_lookup = {skill.name.casefold() if hasattr(skill, "name") else str(skill).casefold()
                        for skill in candidate_skills}
    matched = [skill for skill in requested if skill.casefold() in candidate_lookup]
    missing = [skill for skill in requested if skill.casefold() not in candidate_lookup]
    return 100 * len(matched) / len(requested), matched, missing


def load_scoring_weights(value: str | dict[str, float] | None = None) -> dict[str, float]:
    configured = value if value is not None else os.getenv("HIRERANK_SCORING_WEIGHTS", "")
    if isinstance(configured, str):
        if not configured.strip():
            return DEFAULT_SCORING_WEIGHTS.copy()
        try:
            configured = json.loads(configured)
        except json.JSONDecodeError as error:
            raise ValueError("HIRERANK_SCORING_WEIGHTS must be a JSON object.") from error
    if not isinstance(configured, dict) or set(configured) != set(DEFAULT_SCORING_WEIGHTS):
        raise ValueError(
            "Scoring weights must define exactly: "
            + ", ".join(DEFAULT_SCORING_WEIGHTS)
        )
    weights = {}
    for name, weight in configured.items():
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise ValueError(f"Scoring weight {name!r} must be a number.")
        if not math.isfinite(weight) or weight < 0:
            raise ValueError(f"Scoring weight {name!r} must be finite and non-negative.")
        weights[name] = float(weight)
    if not math.isclose(sum(weights.values()), 1.0, rel_tol=0, abs_tol=1e-9):
        raise ValueError("Scoring weights must sum to 1.0.")
    return weights


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


def calculate_match(
    resume_text: str,
    candidate: Any,
    vacancy: Any,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    weights = load_scoring_weights(weights)
    vacancy_text = " ".join(
        (vacancy.description or "", vacancy.responsibilities or "", vacancy.title or "")
    ).strip()
    description_score = text_similarity(resume_text, vacancy_text)

    skills = [
        item.name if hasattr(item, "name") else str(item)
        for item in candidate.skills
    ]
    required_score, matched_required, missing_required = _skill_score(
        skills, (vacancy.required_skills or "").split(",")
    )
    preferred_score, matched_preferred, missing_preferred = _skill_score(
        skills, (vacancy.preferred_skills or "").split(",")
    )
    years = candidate.experience_years
    minimum = max(0.0, float(vacancy.min_experience or 0))
    maximum = max(minimum, float(vacancy.max_experience or 0))
    if minimum == 0:
        experience_score = 100.0
    elif years is None:
        experience_score = 0.0
    elif years >= minimum:
        experience_score = 100.0
    else:
        experience_score = max(0.0, min(100.0, years / minimum * 100))
    education_score = _education_match(candidate.education, vacancy.education or "")

    components = {
        "description_similarity": description_score,
        "required_skills": required_score,
        "experience_match": experience_score,
        "education_match": education_score,
        "preferred_skills": preferred_score,
    }
    final_score = sum(components[name] * weights[name] for name in weights)
    required_skill_total = len(matched_required) + len(missing_required)
    experience_status = (
        "No minimum experience requirement"
        if minimum == 0
        else "Experience information not identified"
        if years is None
        else "Requirement satisfied"
        if years >= minimum
        else "Below minimum requirement"
    )
    education_status = (
        "No education requirement"
        if not (vacancy.education or "").strip()
        else "Requirement satisfied"
        if education_score == 100
        else "Education requirement not identified or not matched"
    )
    explanation_text = (
        f"{len(matched_required)} of {required_skill_total} unique required skills matched; "
        f"experience: {experience_status.lower()}; education: {education_status.lower()}. "
        "The final score is the weighted sum of the displayed component scores."
    )
    return {
        "description_similarity": round(description_score, 2),
        "required_skills": round(required_score, 2),
        "experience_match": round(experience_score, 2),
        "education_match": round(education_score, 2),
        "preferred_skills": round(preferred_score, 2),
        "final_score": round(max(0.0, min(100.0, final_score)), 2),
        "weights": weights,
        "explanation": {
            "matched_required_skills": matched_required,
            "missing_required_skills": missing_required,
            "matched_preferred_skills": matched_preferred,
            "missing_preferred_skills": missing_preferred,
            "required_skills_matched_count": len(matched_required),
            "required_skills_total": required_skill_total,
            "required_skill_match_percentage": round(required_score, 2),
            "experience_years": years,
            "required_experience": {"minimum": minimum, "maximum": maximum},
            "experience_status": experience_status,
            "education_found": candidate.education or "",
            "education_required": vacancy.education or "",
            "education_status": education_status,
            "component_scores": {name: round(value, 2) for name, value in components.items()},
            "weights": weights,
            "summary": explanation_text,
            "notes": [
                "Missing resume evidence receives no points for that criterion.",
                "Unspecified skill, experience, or education requirements are treated as unconstrained (100%).",
                "Experience above the minimum is not penalized.",
            ],
        },
    }
