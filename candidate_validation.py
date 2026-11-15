import re
from datetime import datetime, timezone
from typing import Any

from ml_engine import extract_skills, normalize_text, text_similarity

SECTION_ALIASES = {
    "skills": {"skills", "technical skills", "core skills", "skill set", "core competencies"},
    "projects": {"projects", "project experience", "academic projects", "personal projects"},
    "experience": {"experience", "responsibilities", "achievements"},
    "professional_experience": {
        "work experience", "professional experience", "employment history", "work history",
    },
    "internship_experience": {
        "internship", "internships", "internship experience", "internship experience details",
    },
    "education": {"education", "academic background", "educational background"},
}
SECTION_HEADERS = {
    header: section
    for section, headers in SECTION_ALIASES.items()
    for header in headers
}
OTHER_SECTION_HEADERS = {
    "summary", "professional summary", "career objective", "objective",
    "certifications", "certification", "languages", "references",
}
PROJECT_METADATA_LABELS = {
    "description", "technologies", "technology", "tech stack", "tools", "skills",
}
ADDITIONAL_TECHNOLOGIES = (
    "Pandas", "NumPy", "Matplotlib", "Seaborn", "SciPy", "Keras",
    "OpenCV", "FastAPI", "Node.js", "Express", "AWS", "Azure",
)
EXPERIENCE_DATE_PART = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?|\d{1,2}/)\s*(?:19|20)\d{2}"
)
EXPERIENCE_DATE_RE = re.compile(
    rf"\b(?P<start>{EXPERIENCE_DATE_PART})\s*(?:-|–|—|to)\s*"
    rf"(?P<end>{EXPERIENCE_DATE_PART})\b",
    re.I,
)


def _normalize_heading(line: str) -> str:
    line = re.sub(r"^\s*(?:(?:\d+[.)])|[-*•])\s*", "", line)
    return re.sub(r"[^a-z0-9]+", " ", line.casefold()).strip()


def _extract_sections(text: str) -> dict[str, str]:
    sections = {name: [] for name in SECTION_ALIASES}
    current_section = None
    section_headers = sorted(
        SECTION_HEADERS.items(), key=lambda item: len(item[0]), reverse=True
    )
    for line in (text or "").splitlines():
        inline_line = re.sub(r"^\s*(?:(?:\d+[.)])|[-*•])\s*", "", line)
        inline_match = None
        inline_section = None
        for header, section in section_headers:
            header_pattern = re.escape(header).replace(r"\ ", r"\s+")
            inline_match = re.match(
                rf"^\s*{header_pattern}\s*:\s*(.*)$", inline_line, re.I
            )
            if inline_match:
                inline_section = section
                break
        if inline_match and inline_section:
            current_section = inline_section
            if inline_match.group(1).strip():
                sections[current_section].append(inline_match.group(1).strip())
            continue
        normalized = _normalize_heading(line)
        if normalized in SECTION_HEADERS:
            current_section = SECTION_HEADERS[normalized]
            continue
        if normalized in OTHER_SECTION_HEADERS:
            current_section = None
            continue
        if current_section:
            sections[current_section].append(line.strip())
    return {name: "\n".join(lines) for name, lines in sections.items()}


def _sentences(text: str) -> list[str]:
    sentences = []
    seen = set()
    for line in (text or "").splitlines():
        line = re.sub(r"^\s*(?:(?:\d+[.)])|[-*•])\s*", "", line).strip()
        for sentence in re.split(r"(?<=[.!?])\s+", line):
            sentence = re.sub(r"\s+", " ", sentence).strip()
            if sentence and sentence.casefold() not in seen:
                seen.add(sentence.casefold())
                sentences.append(sentence)
    return sentences


def _skill_pattern(skill: str) -> re.Pattern[str] | None:
    normalized_skill = skill.strip().casefold()
    parts = re.split(r"[\s-]+", normalized_skill)
    if not parts or not any(parts):
        return None
    pattern = (
        r"(?<![\w+#])"
        + r"[\s-]+".join(re.escape(part) for part in parts)
    )
    if not normalized_skill.endswith(("s", "+", "#")):
        pattern += r"s?"
    pattern += r"(?![\w+#])"
    return re.compile(pattern, re.I)


def _matching_sentences(sentences: list[str], skill: str) -> list[str]:
    pattern = _skill_pattern(skill)
    if pattern is None:
        return []
    return [sentence for sentence in sentences if pattern.search(sentence)]


def _extract_technologies(text: str) -> list[str]:
    sentences = _sentences(text)
    technologies = extract_skills(text)
    for technology in ADDITIONAL_TECHNOLOGIES:
        if _matching_sentences(sentences, technology) and technology.casefold() not in {
            item.casefold() for item in technologies
        }:
            technologies.append(technology)
    return technologies


def _vacancy_skills(vacancy: Any) -> list[dict[str, str]]:
    skills_by_name = {}
    for requirement, value in (
        ("Required", vacancy.required_skills),
        ("Preferred", vacancy.preferred_skills),
    ):
        for item in (value or "").split(","):
            skill = item.strip()
            if not skill:
                continue
            key = skill.casefold()
            existing = skills_by_name.get(key)
            if existing is None or requirement == "Required":
                skills_by_name[key] = {"skill": skill, "requirement": requirement}
    return list(skills_by_name.values())


def _skill_evidence(
    skills: list[dict[str, str]],
    resume_sentences: list[str],
    project_evidence: list[dict[str, str]],
    professional_experience: list[dict[str, str]],
    internship_experience: list[dict[str, str]],
) -> list[dict[str, Any]]:
    evidence = []
    for item in skills:
        skill = item["skill"]
        resume_matches = _matching_sentences(resume_sentences, skill)
        project_matches = [
            {"source": entry["source"], "sentence": entry["sentence"]}
            for entry in project_evidence
            if _matching_sentences([entry["sentence"]], skill)
        ]
        professional_matches = [
            {"source": entry["source"], "sentence": entry["sentence"]}
            for entry in professional_experience
            if _matching_sentences([entry["sentence"]], skill)
        ]
        internship_matches = [
            {"source": entry["source"], "sentence": entry["sentence"]}
            for entry in internship_experience
            if _matching_sentences([entry["sentence"]], skill)
        ]
        if project_matches or professional_matches or internship_matches:
            status = "Evidence found"
        elif resume_matches:
            status = "Mentioned only"
        else:
            status = "Evidence not found"
        evidence.append({
            **item,
            "resume_mention": bool(resume_matches),
            "resume_sentences": resume_matches[:2],
            "project_evidence": project_matches[:3],
            "professional_experience_evidence": professional_matches[:3],
            "internship_experience_evidence": internship_matches[:3],
            "experience_evidence": (professional_matches + internship_matches)[:3],
            "status": status,
        })
    return evidence


def _similarity_percentage(project_text: str, vacancy_text: str) -> float | None:
    if not normalize_text(project_text) or not normalize_text(vacancy_text):
        return None
    return round(text_similarity(project_text, vacancy_text), 2)


def _project_entries(project_text: str) -> list[str]:
    groups: list[str] = []
    current = []
    lines = (project_text or "").splitlines()

    def flush() -> None:
        if current:
            groups.append("\n".join(current))
            current.clear()

    def looks_like_title(line: str) -> bool:
        value = line.strip(" -*•\t")
        words = value.split()
        if not 1 <= len(words) <= 9 or re.search(r"[.!?;]", value):
            return False
        if ":" in value or re.search(r"\b(?:19|20)\d{2}\b", value):
            return False
        if value.casefold().rstrip(":") in PROJECT_METADATA_LABELS:
            return False
        return not re.match(
            r"^(?:built|created|developed|implemented|designed|worked|used|"
            r"managed|analyzed|analysed|led|responsible|technologies|tools)\b",
            value,
            re.I,
        )

    def is_action_sentence(line: str) -> bool:
        return bool(re.match(
            r"^(?:built|created|developed|implemented|designed|worked|used|"
            r"managed|analyzed|analysed|led|maintained|deployed|integrated|"
            r"automated|tested|engineered|delivered|supported)\b",
            line.strip(" -*•\t"),
            re.I,
        ))

    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            flush()
            continue
        project_marker = re.match(
            r"^(?:project\s*\d+\s*[:#-]\s*|project\s*:\s*)(.*)$",
            line,
            re.I,
        )
        numbered_entry = re.match(r"^\d+[.)]\s+(.*)$", line)
        if project_marker or (numbered_entry and not is_action_sentence(numbered_entry.group(1))):
            flush()
            entry = project_marker or numbered_entry
            if entry.group(1).strip():
                current.append(entry.group(1).strip())
            continue
        bullet_project = re.match(r"^[-*•]\s+(.+)$", line)
        if (
            bullet_project
            and ":" in bullet_project.group(1)
            and current
            and not is_action_sentence(bullet_project.group(1))
            and len(bullet_project.group(1).split(":", 1)[0].split()) <= 9
        ):
            flush()
            current.append(bullet_project.group(1).strip())
            continue
        next_line = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if (
            current
            and len(current) >= 2
            and looks_like_title(line)
            and (not next_line or looks_like_title(next_line) is False)
        ):
            flush()
        current.append(re.sub(r"^[-*•]\s+", "", line))
    flush()
    return groups


def _project_title(project_text: str) -> str:
    lines = [line.strip() for line in project_text.splitlines() if line.strip()]
    if not lines:
        return "Not available"
    first_line = re.sub(r"^project\s*\d*\s*[:#-]\s*", "", lines[0], flags=re.I)
    if first_line.casefold().startswith("description:"):
        first_line = lines[1] if len(lines) > 1 else ""
    title_part = re.split(r"\s*(?::|\||\s[-–—]\s)\s*", first_line, maxsplit=1)[0].strip()
    if title_part.casefold().rstrip(":") in PROJECT_METADATA_LABELS:
        title_part = ""
    if (
        1 <= len(title_part.split()) <= 10
        and not re.match(r"^(built|created|developed|implemented|designed|worked)\b", title_part, re.I)
    ):
        return title_part.rstrip(".")
    return "Not available"


def _project_description(project_text: str) -> str:
    description_lines = []
    for index, raw_line in enumerate(project_text.splitlines()):
        line = raw_line.strip()
        if not line:
            continue
        label_match = re.match(r"^([A-Za-z ]+)\s*:\s*(.*)$", line)
        label = label_match.group(1).strip().casefold() if label_match else ""
        value = label_match.group(2).strip() if label_match else line
        if label in {"technologies", "technology", "tech stack", "tools", "skills"}:
            continue
        if label == "description":
            if value:
                description_lines.append(value)
            continue
        if index == 0:
            if label_match:
                title_prefix = label_match.group(1).strip()
                if (
                    title_prefix.casefold() not in PROJECT_METADATA_LABELS
                    and not re.match(r"^project\s*\d*$", title_prefix, re.I)
                    and value
                ):
                    description_lines.append(value)
            elif re.match(
                r"^(?:built|created|developed|implemented|designed|worked|"
                r"used|managed|analyzed|analysed|led)\b",
                line,
                re.I,
            ):
                description_lines.append(line)
            continue
        description_lines.append(value)
    return "\n".join(description_lines)


def _project_supporting_sentences(project_text: str) -> list[str]:
    supporting_lines = []
    for index, raw_line in enumerate(project_text.splitlines()):
        line = raw_line.strip()
        if not line:
            continue
        label_match = re.match(r"^([A-Za-z ]+)\s*:\s*(.*)$", line)
        label = label_match.group(1).strip().casefold() if label_match else ""
        if label in {"technologies", "technology", "tech stack", "tools", "skills"}:
            continue
        if label == "description":
            supporting_lines.append(line)
        elif index == 0:
            if label_match and label not in PROJECT_METADATA_LABELS and label_match.group(2).strip():
                supporting_lines.append(line)
            elif not label_match and re.match(
                r"^(?:built|created|developed|implemented|designed|worked|"
                r"used|managed|analyzed|analysed|led)\b",
                line,
                re.I,
            ):
                supporting_lines.append(line)
        else:
            supporting_lines.append(line)
    return _sentences("\n".join(supporting_lines))


def _project_evidence_sentences(projects: list[dict[str, Any]]) -> list[dict[str, str]]:
    evidence = []
    for project in projects:
        for sentence in project["evidence_sentences"]:
            evidence.append({
                "source": project["title"],
                "sentence": sentence,
            })
    return evidence


def _project_analysis(
    project_text: str, skills: list[dict[str, str]], vacancy: Any
) -> list[dict[str, Any]]:
    vacancy_skills = [item["skill"] for item in skills]
    vacancy_text = " ".join(
        part for part in (
            vacancy.title or "",
            vacancy.description or "",
            vacancy.responsibilities or "",
            ", ".join(vacancy_skills),
        ) if part
    )
    reports = []
    for content in _project_entries(project_text):
        project_description = _project_description(content)
        project_sentences = _sentences(project_description)
        evidence_sentences = _project_supporting_sentences(content)
        technologies = list(dict.fromkeys(_extract_technologies(content)))
        relevant_skills = [
            skill for skill in vacancy_skills if _matching_sentences(project_sentences, skill)
        ]
        for skill in relevant_skills:
            if skill.casefold() not in {technology.casefold() for technology in technologies}:
                technologies.append(skill)
        relevance = _similarity_percentage(content, vacancy_text)
        if relevance is None:
            explanation = "Not available: project or vacancy text is insufficient for comparison."
        else:
            explanation = (
                f"TF-IDF text similarity is {relevance:.2f}%; it reflects textual overlap, "
                "not candidate competence."
            )
        reports.append({
            "title": _project_title(content),
            "description": content,
            "summary": project_description,
            "technologies": technologies,
            "relevance_percentage": relevance,
            "relevant_requirements": relevant_skills,
            "explanation": explanation,
            "evidence_sentences": evidence_sentences,
        })
    return reports


def _experience_date_range(text: str) -> tuple[str, str]:
    match = EXPERIENCE_DATE_RE.search(text)
    if not match:
        return "Not available", "Not available"
    start, end = match.group("start").strip(), match.group("end").strip()

    def month_index(value: str) -> int | None:
        value = re.sub(r"\s+", " ", value.strip())
        for pattern in ("%b %Y", "%B %Y", "%m/%Y"):
            try:
                date = datetime.strptime(value, pattern)
                return date.year * 12 + date.month
            except ValueError:
                continue
        return None

    start_month, end_month = month_index(start), month_index(end)
    if start_month is None or end_month is None or end_month < start_month:
        return f"{start} – {end}", "Not available"
    months = end_month - start_month + 1
    years, remainder = divmod(months, 12)
    duration_parts = []
    if years:
        duration_parts.append(f"{years} year{'s' if years != 1 else ''}")
    if remainder:
        duration_parts.append(f"{remainder} month{'s' if remainder != 1 else ''}")
    return f"{start} – {end}", " ".join(duration_parts) or "Less than one month"


def _experience_blocks(experience_text: str) -> list[str]:
    blocks = []
    current = []
    for line in (experience_text or "").splitlines():
        if not line.strip():
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        starts_role = re.match(
            r"^\s*(?:worked|working|served|employed)\s+as\b|"
            r"^\s*(?:internship|intern|trainee|apprentice)\b",
            line,
            re.I,
        )
        has_separate_role_heading = (
            current
            and re.match(r"^[^.!?]{2,60}\s+\|\s+[^.!?]{2,60}$", line.strip())
        )
        repeated_date_range = (
            current
            and EXPERIENCE_DATE_RE.search(line)
            and EXPERIENCE_DATE_RE.search("\n".join(current))
        )
        if current and (starts_role or has_separate_role_heading or repeated_date_range):
            blocks.append("\n".join(current))
            current = []
        current.append(line.strip())
    if current:
        blocks.append("\n".join(current))
    return blocks


def _experience_details(
    experience_text: str,
    skills: list[dict[str, str]],
    default_category: str,
) -> list[dict[str, Any]]:
    reports = []
    for block in _experience_blocks(experience_text):
        sentences = _sentences(block)
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        joined = "\n".join(lines)
        title = "Not available"
        for pattern in (
            r"\b(?:worked|working|served|employed)\s+as\s+(.+?)(?=\s+(?:at|for)\b|[,.;|\n]|$)",
            r"\bposition(?:ed)?\s+as\s+(.+?)(?=\s+(?:at|for)\b|[,.;|\n]|$)",
            r"\b([A-Z][A-Za-z/& -]{1,50}?\b(?:intern|internship|trainee|apprentice))"
            r"(?=\s+(?:at|with)\b|[,.;|\n]|$)",
        ):
            match = re.search(pattern, joined, re.I)
            if match:
                title = re.sub(r"^(?:a|an|the)\s+", "", match.group(1).strip(), flags=re.I)
                break
        company = "Not available"
        company_match = re.search(
            r"\bat\s+([A-Z][A-Za-z0-9&.,' -]*?)(?=\s+(?:for|from|since|during)\b|[,;|.]|$)",
            joined,
            re.I,
        )
        if company_match:
            company = company_match.group(1).strip()
        first_parts = re.split(r"\s*[|–—]\s*", lines[0])
        if len(first_parts) > 1:
            if title == "Not available" and len(first_parts[0].split()) <= 10:
                title = first_parts[0].strip()
            if company == "Not available" and not re.search(r"\b(19|20)\d{2}\b", first_parts[1]):
                company = first_parts[1].strip()

        is_internship = (
            default_category == "internship"
            or re.search(r"\b(?:intern(?:ship)?|trainee|apprentice)\b", title, re.I)
            or re.match(r"^\s*(?:internship|intern|trainee|apprentice)\b", lines[0], re.I)
        )
        category = "internship" if is_internship else "professional"
        date_range, duration = _experience_date_range(joined)
        responsibilities = [
            sentence for sentence in sentences
            if not EXPERIENCE_DATE_RE.search(sentence)
            and not (
                "|" in sentence
                and not re.search(
                    r"\b(?:built|created|developed|implemented|designed|worked|"
                    r"managed|analyzed|analysed|led|supported|maintained)\b",
                    sentence,
                    re.I,
                )
            )
            and not re.match(r"^(?:technologies|technology|tech stack|tools|skills)\s*:", sentence, re.I)
        ]
        relevant_skills = [
            item["skill"] for item in skills
            if _matching_sentences(responsibilities, item["skill"])
        ]
        technologies = list(dict.fromkeys(_extract_technologies(joined)))
        for skill in relevant_skills:
            if skill.casefold() not in {technology.casefold() for technology in technologies}:
                technologies.append(skill)
        reports.append({
            "category": category,
            "job_title": title,
            "company": company,
            "date_range": date_range,
            "duration": duration,
            "technologies": technologies,
            "relevant_skills": relevant_skills,
            "responsibilities": responsibilities,
            "evidence_status": "Evidence found" if responsibilities else "Evidence not found",
        })
    return reports


def _keyword_occurrences(text: str, skill: str) -> int:
    pattern = _skill_pattern(skill)
    return len(pattern.findall(text)) if pattern else 0


def _experience_evidence_sentences(experiences: list[dict[str, Any]]) -> list[dict[str, str]]:
    evidence = []
    for experience in experiences:
        category = (
            "Internship experience"
            if experience["category"] == "internship"
            else "Professional experience"
        )
        details = [
            value for value in (experience["job_title"], experience["company"])
            if value != "Not available"
        ]
        source = f"{category}: {' at '.join(details)}" if details else category
        evidence.extend(
            {"source": source, "sentence": sentence}
            for sentence in experience["responsibilities"]
        )
    return evidence


def _resume_quality(
    resume_text: str,
    sections: dict[str, str],
    candidate: Any,
    project_text: str,
    experience_text: str,
    skill_evidence: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    vacancy_skills: list[dict[str, str]],
) -> dict[str, Any]:
    missing_sections = []
    if not (candidate.education or sections["education"]):
        missing_sections.append("Education information")
    if not sections["skills"]:
        missing_sections.append("Skills section")
    if not project_text.strip():
        missing_sections.append("Project descriptions")
    if not experience_text.strip():
        missing_sections.append("Work experience information")

    keywords = list(dict.fromkeys(
        [item for item in extract_skills(resume_text)]
        + [item["skill"] for item in vacancy_skills]
    ))
    repeated_keywords = [
        {"keyword": keyword, "count": count}
        for keyword in keywords
        if (count := _keyword_occurrences(resume_text, keyword)) >= 3
    ]
    unsupported_skills = [
        item["skill"] for item in skill_evidence if item["status"] == "Mentioned only"
    ]
    incomplete_projects = []
    for project in projects:
        word_count = len(re.findall(r"\b[\w+#.-]+\b", project["summary"]))
        if word_count < 8:
            incomplete_projects.append({
                "title": project["title"],
                "observation": "The project description is brief; consider reviewing it manually.",
            })
    observations = []
    if unsupported_skills:
        observations.append(
            f"Skills mentioned without project or experience evidence: "
            f"{', '.join(unsupported_skills[:4])}."
        )
    if incomplete_projects:
        titles = [item["title"] for item in incomplete_projects[:2]]
        observations.append(f"Brief project description: {', '.join(titles)}.")
    if missing_sections:
        observations.append(f"Missing resume information: {', '.join(missing_sections[:3])}.")
    if repeated_keywords:
        repeated = [item["keyword"] for item in repeated_keywords[:3]]
        observations.append(f"Repeated keywords may need review: {', '.join(repeated)}.")
    if not observations:
        observations.append("No major resume completeness issues were identified.")
    return {
        "missing_sections": missing_sections,
        "repeated_keywords": repeated_keywords,
        "unsupported_skills": unsupported_skills,
        "incomplete_projects": incomplete_projects,
        "observations": observations[:4],
        "disclaimer": (
            "Missing resume evidence is not proof of missing ability and should not be used "
            "as automatic rejection criteria."
        ),
    }


def _hr_summary(required_evidence: list[dict[str, Any]]) -> str:
    def short_list(items: list[str]) -> str:
        if len(items) <= 4:
            return ", ".join(items)
        return f"{', '.join(items[:4])}, and {len(items) - 4} more"

    if not required_evidence:
        return "No required skills are listed for this vacancy."
    evidence_found = [item for item in required_evidence if item["status"] == "Evidence found"]
    mentioned_only = [item for item in required_evidence if item["status"] == "Mentioned only"]
    not_found = [item for item in required_evidence if item["status"] == "Evidence not found"]
    sentences = []
    project_skills = [item["skill"] for item in evidence_found if item["project_evidence"]]
    experience_skills = [
        item["skill"] for item in evidence_found
        if item["professional_experience_evidence"] or item["internship_experience_evidence"]
    ]
    if project_skills:
        sentences.append(f"Project descriptions support {short_list(project_skills)}.")
    if experience_skills:
        sentences.append(f"Experience descriptions support {short_list(experience_skills)}.")
    if not project_skills and not experience_skills:
        sentences.append("No project or experience evidence was identified for required skills.")
    review_notes = []
    if mentioned_only:
        review_notes.append(
            f"Resume-only mentions need review: "
            f"{short_list([item['skill'] for item in mentioned_only])}"
        )
    if not_found:
        review_notes.append(
            f"No supporting mention was identified for "
            f"{short_list([item['skill'] for item in not_found])}"
        )
    sentences.append(
        "; ".join(review_notes) + "."
        if review_notes
        else "All required skills have project or experience evidence."
    )
    sentences.append("Missing resume evidence is not proof of missing ability.")
    return " ".join(sentences[:4])


def build_validation_report(resume_text: str, candidate: Any, vacancy: Any) -> dict[str, Any]:
    resume_text = resume_text or ""
    sections = _extract_sections(resume_text)
    project_text = sections["projects"] or candidate.projects or ""
    professional_text = "\n\n".join(
        text for text in (
            sections["professional_experience"],
            sections["experience"],
        ) if text.strip()
    )
    internship_text = sections["internship_experience"]
    experience_text = "\n\n".join(
        text for text in (professional_text, internship_text) if text.strip()
    )
    resume_sentences = _sentences(resume_text)
    skills = _vacancy_skills(vacancy)
    projects = _project_analysis(project_text, skills, vacancy)
    project_evidence = _project_evidence_sentences(projects)
    general_experiences = _experience_details(professional_text, skills, "professional")
    explicit_internships = _experience_details(internship_text, skills, "internship")
    professional_experiences = [
        item for item in general_experiences if item["category"] == "professional"
    ]
    internship_experiences = [
        item for item in general_experiences if item["category"] == "internship"
    ] + explicit_internships
    professional_evidence = _experience_evidence_sentences(professional_experiences)
    internship_evidence = _experience_evidence_sentences(internship_experiences)
    skill_evidence = _skill_evidence(
        skills,
        resume_sentences,
        project_evidence,
        professional_evidence,
        internship_evidence,
    )
    required_evidence = [item for item in skill_evidence if item["requirement"] == "Required"]
    experiences = professional_experiences + internship_experiences
    unique_required = {item["skill"].casefold(): item for item in required_evidence}
    overview = {
        "total_required_skills": len(unique_required),
        "skills_identified": sum(
            item["status"] != "Evidence not found" for item in unique_required.values()
        ),
        "skills_with_evidence": sum(
            item["status"] == "Evidence found" for item in unique_required.values()
        ),
        "skills_requiring_review": sum(
            item["status"] != "Evidence found" for item in unique_required.values()
        ),
        "skills_with_project_evidence": sum(
            bool(item["project_evidence"]) for item in unique_required.values()
        ),
        "skills_with_experience_evidence": sum(
            bool(
                item["professional_experience_evidence"]
                or item["internship_experience_evidence"]
            )
            for item in unique_required.values()
        ),
        "skills_mentioned_only": sum(
            item["status"] == "Mentioned only" for item in unique_required.values()
        ),
        "skills_not_found": sum(
            item["status"] == "Evidence not found" for item in unique_required.values()
        ),
    }
    return {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "vacancy_title": vacancy.title,
        "overview": overview,
        "skills": skill_evidence,
        "projects": projects,
        "professional_experience": professional_experiences,
        "internship_experience": internship_experiences,
        "experience": experiences,
        "quality": _resume_quality(
            resume_text, sections, candidate, project_text, experience_text,
            skill_evidence, projects, skills,
        ),
        "hr_summary": _hr_summary(required_evidence),
    }
