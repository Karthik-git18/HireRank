import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from ml_engine import (
    clean_resume_text,
    extract_resume_information,
    extract_skills,
    load_skill_dictionary,
    calculate_match,
    load_scoring_weights,
)


class ResumeExtractionTests(unittest.TestCase):
    def test_clean_resume_text_normalizes_spacing_and_control_characters(self):
        self.assertEqual(
            clean_resume_text("Name\r\n\r\nPython\tDeveloper\x00"),
            "Name\nPython Developer",
        )

    def test_extract_resume_information_uses_resume_sections(self):
        resume_text = """Alex Morgan
alex.morgan@example.org
+1 415 555 0132
Skills
Python, C++, SQL, Machine Learning
Professional Experience
Software Engineer at Example Corp
Built data services using Python and SQL.
Education
B.Tech in Computer Science, Example University
Projects
Forecasting Platform
Developed a time-series model using Python.
Certifications
AWS Certified Developer
"""

        result = extract_resume_information(resume_text)

        self.assertEqual(result["name"], "Alex Morgan")
        self.assertEqual(result["email"], "alex.morgan@example.org")
        self.assertIn("415 555 0132", result["phone"])
        self.assertEqual(
            result["skills"], ["Python", "C++", "SQL", "Machine Learning", "AWS"]
        )
        self.assertIn("B.Tech in Computer Science", result["education"])
        self.assertIn("Software Engineer at Example Corp", result["experience_summary"])
        self.assertIn("Forecasting Platform", result["projects"])
        self.assertIn("AWS Certified Developer", result["certifications"])
        self.assertIsNone(result["experience_years"])

    def test_missing_fields_remain_empty_without_invented_values(self):
        result = extract_resume_information("A resume without contact or qualification details.")

        self.assertEqual(result["name"], "Unidentified candidate")
        self.assertEqual(result["email"], "")
        self.assertEqual(result["phone"], "")
        self.assertEqual(result["skills"], [])
        self.assertEqual(result["education"], "")
        self.assertEqual(result["experience_summary"], "")
        self.assertEqual(result["projects"], "")
        self.assertEqual(result["certifications"], "")

    def test_inline_section_labels_preserve_their_first_values(self):
        result = extract_resume_information(
            "Jordan Lee\n"
            "Skills: Python, SQL\n"
            "Education: B.Tech in Computer Science\n"
            "Experience: Python Developer at Example Corp\n"
            "Projects: Weather API - Built a service with Python.\n"
            "Certifications: AWS Certified Developer"
        )

        self.assertIn("B.Tech in Computer Science", result["education"])
        self.assertEqual(result["experience_summary"], "Python Developer at Example Corp")
        self.assertIn("Weather API", result["projects"])
        self.assertEqual(result["certifications"], "AWS Certified Developer")
        self.assertIn("Python", result["skills"])
        self.assertIn("SQL", result["skills"])

    def test_skill_dictionary_can_be_configured_and_avoids_c_prefix_false_match(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "skills.json"
            path.write_text(json.dumps({"Custom": ["Rust", "C", "C++"]}), encoding="utf-8")
            configured = load_skill_dictionary(path)

        self.assertEqual(extract_skills("Rust and C++", configured), ["Rust", "C++"])

    def test_scoring_weights_are_configurable_and_sum_to_one(self):
        weights = {
            "description_similarity": 1.0,
            "required_skills": 0.0,
            "experience_match": 0.0,
            "education_match": 0.0,
            "preferred_skills": 0.0,
        }
        candidate = SimpleNamespace(
            skills=[SimpleNamespace(name="Python")],
            education="B.Tech",
            experience_years=2,
        )
        vacancy = SimpleNamespace(
            title="Python Engineer",
            description="Python Engineer",
            responsibilities="",
            required_skills="Python",
            preferred_skills="",
            education="B.Tech",
            min_experience=1,
            max_experience=3,
        )

        result = calculate_match("Python Engineer", candidate, vacancy, weights)

        self.assertEqual(result["weights"], weights)
        self.assertEqual(result["final_score"], result["description_similarity"])
        self.assertEqual(sum(load_scoring_weights(weights).values()), 1)

    def test_skill_gap_deduplicates_requirements_and_explains_real_counts(self):
        candidate = SimpleNamespace(
            skills=[
                SimpleNamespace(name="Python"),
                SimpleNamespace(name="python"),
                SimpleNamespace(name="SQL"),
            ],
            education="B.Tech",
            experience_years=3,
        )
        vacancy = SimpleNamespace(
            title="Data Engineer",
            description="",
            responsibilities="",
            required_skills="Python, python, SQL, SQL, Deep Learning",
            preferred_skills="AWS, aws",
            education="B.Tech",
            min_experience=2,
            max_experience=5,
        )

        result = calculate_match("Python SQL", candidate, vacancy)
        explanation = result["explanation"]

        self.assertEqual(result["required_skills"], 66.67)
        self.assertEqual(result["preferred_skills"], 0)
        self.assertEqual(explanation["matched_required_skills"], ["Python", "SQL"])
        self.assertEqual(explanation["missing_required_skills"], ["Deep Learning"])
        self.assertEqual(explanation["required_skills_matched_count"], 2)
        self.assertEqual(explanation["required_skills_total"], 3)
        self.assertEqual(explanation["experience_status"], "Requirement satisfied")
        self.assertEqual(explanation["education_status"], "Requirement satisfied")
        self.assertIn("2 of 3 unique required skills matched", explanation["summary"])

    def test_invalid_scoring_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            load_scoring_weights('{"required_skills": 0.5}')


if __name__ == "__main__":
    unittest.main()
