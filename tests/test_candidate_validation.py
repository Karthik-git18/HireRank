import unittest
from types import SimpleNamespace

from candidate_validation import build_validation_report
from ml_engine import calculate_match


class CandidateValidationTests(unittest.TestCase):
    def setUp(self):
        self.candidate = SimpleNamespace(
            name="Example Candidate",
            skills=[],
            projects="",
            experience_summary="",
            experience_years=None,
            education="B.Tech in Computer Science",
        )
        self.vacancy = SimpleNamespace(
            title="Machine Learning Engineer",
            required_skills="Python, Machine Learning, TensorFlow, SQL, Scikit-learn",
            preferred_skills="PyTorch",
            description="Build machine learning models using Python and TensorFlow.",
            responsibilities="Develop and maintain machine learning applications.",
            education="B.Tech",
            min_experience=0,
            max_experience=0,
        )
        self.resume_text = """Skills
Python, Machine Learning, TensorFlow, SQL, Scikit-learn
Projects
1. House Price Prediction: Built using Python and Scikit-learn.
2. Image Classification: Developed with TensorFlow and Machine Learning.
Experience
Worked as a Python Developer Intern at Acme for six months. Built Flask APIs and worked with SQL databases.
Education
B.Tech in Computer Science.
"""

    def test_skill_evidence_keeps_mentions_separate_from_demonstration(self):
        report = build_validation_report(self.resume_text, self.candidate, self.vacancy)
        by_skill = {item["skill"]: item for item in report["skills"]}

        self.assertEqual(by_skill["Python"]["status"], "Evidence found")
        self.assertEqual(by_skill["SQL"]["status"], "Evidence found")
        self.assertEqual(by_skill["PyTorch"]["status"], "Evidence not found")
        self.assertIn(
            "House Price Prediction: Built using Python and Scikit-learn.",
            [entry["sentence"] for entry in by_skill["Python"]["project_evidence"]],
        )
        self.assertIn(
            "House Price Prediction",
            [entry["source"] for entry in by_skill["Python"]["project_evidence"]],
        )
        self.assertIn(
            "Worked as a Python Developer Intern at Acme for six months.",
            [entry["sentence"] for entry in by_skill["Python"]["internship_experience_evidence"]],
        )
        self.assertEqual(report["overview"]["total_required_skills"], 5)
        self.assertEqual(report["overview"]["skills_not_found"], 0)
        self.assertEqual(report["overview"]["skills_with_evidence"], 5)
        self.assertEqual(report["overview"]["skills_requiring_review"], 0)

    def test_project_analysis_uses_resume_text_and_vacancy_similarity(self):
        report = build_validation_report(self.resume_text, self.candidate, self.vacancy)

        projects = report["projects"]
        self.assertEqual([project["title"] for project in projects], [
            "House Price Prediction",
            "Image Classification",
        ])
        self.assertIn("Python", projects[0]["technologies"])
        self.assertIn("Scikit-learn", projects[0]["relevant_requirements"])
        self.assertIsNotNone(projects[0]["relevance_percentage"])
        self.assertTrue(projects[0]["explanation"].startswith("TF-IDF text similarity"))
        self.assertIn("not candidate competence", projects[0]["explanation"])

    def test_experience_details_are_extracted_only_when_present(self):
        report = build_validation_report(self.resume_text, self.candidate, self.vacancy)
        experience = report["experience"][0]

        self.assertEqual(experience["job_title"], "Python Developer Intern")
        self.assertEqual(experience["company"], "Acme")
        self.assertEqual(experience["duration"], "Not available")
        self.assertEqual(experience["category"], "internship")
        self.assertIn("SQL", experience["relevant_skills"])

    def test_multiple_experience_blocks_are_kept_separate(self):
        candidate = SimpleNamespace(
            skills=[],
            projects="",
            experience_summary="",
            experience_years=None,
            education="",
        )
        vacancy = SimpleNamespace(
            title="Engineer",
            required_skills="Python, SQL",
            preferred_skills="",
            description="",
            responsibilities="",
            education="",
        )
        resume_text = (
            "Experience\n"
            "Worked as a Python Developer at Acme for one year. Built Python APIs.\n\n"
            "Worked as a SQL Analyst at Beta for two years. Queried SQL databases."
        )

        report = build_validation_report(resume_text, candidate, vacancy)

        self.assertEqual(
            [(item["job_title"], item["company"], item["duration"]) for item in report["experience"]],
            [
                ("Python Developer", "Acme", "Not available"),
                ("SQL Analyst", "Beta", "Not available"),
            ],
        )

    def test_inline_section_headings_are_recognized(self):
        candidate = SimpleNamespace(
            skills=[],
            projects="",
            experience_summary="",
            experience_years=None,
            education="",
        )
        vacancy = SimpleNamespace(
            title="Engineer",
            required_skills="FastAPI",
            preferred_skills="",
            description="Build APIs",
            responsibilities="",
            education="",
        )
        report = build_validation_report(
            "Skills: FastAPI\nProjects: FastAPI service: Built a FastAPI endpoint for clients.",
            candidate,
            vacancy,
        )

        self.assertEqual(report["skills"][0]["status"], "Evidence found")
        self.assertNotIn("Skills section", report["quality"]["missing_sections"])
        self.assertNotIn("Project descriptions", report["quality"]["missing_sections"])

    def test_academic_projects_internships_and_professional_roles_are_separate(self):
        candidate = SimpleNamespace(
            skills=[],
            projects="",
            experience_summary="",
            experience_years=None,
            education="",
        )
        vacancy = SimpleNamespace(
            title="Python Developer",
            required_skills="Python, Flask, SQL, REST API, HTML, JavaScript, TensorFlow, Python",
            preferred_skills="SQL",
            description="Build Python services and REST APIs.",
            responsibilities="Develop applications with Flask and SQL.",
            education="",
        )
        resume_text = """Skills
Python, Flask, SQL, HTML
Academic Projects
Customer Churn Prediction
Developed a model using Python and Scikit-learn to predict customer churn.
Technologies: Python, Scikit-learn, Pandas
Student Record API
Built REST APIs using Flask and SQL to manage student records.
Technologies: Python, Flask, SQL, REST API
Tool List
Technologies: TensorFlow
Professional Experience
Software Engineer | Acme
Jan 2020 - Dec 2021
Developed Python services.
Internship Experience
Python Developer Intern at Beta
Built Flask APIs.
"""

        report = build_validation_report(resume_text, candidate, vacancy)
        by_skill = {item["skill"]: item for item in report["skills"]}

        self.assertEqual(len(report["projects"]), 3)
        self.assertEqual(
            [project["title"] for project in report["projects"]],
            ["Customer Churn Prediction", "Student Record API", "Tool List"],
        )
        self.assertIn("Pandas", report["projects"][0]["technologies"])
        self.assertEqual(len(report["professional_experience"]), 1)
        self.assertEqual(len(report["internship_experience"]), 1)
        self.assertEqual(report["professional_experience"][0]["duration"], "2 years")
        self.assertEqual(report["internship_experience"][0]["duration"], "Not available")
        self.assertEqual(report["internship_experience"][0]["job_title"], "Python Developer Intern")
        self.assertEqual(by_skill["REST API"]["status"], "Evidence found")
        self.assertEqual(by_skill["TensorFlow"]["status"], "Mentioned only")
        self.assertEqual(by_skill["TensorFlow"]["project_evidence"], [])
        self.assertEqual(by_skill["HTML"]["status"], "Mentioned only")
        self.assertEqual(by_skill["JavaScript"]["status"], "Evidence not found")
        self.assertEqual(report["overview"]["total_required_skills"], 7)
        self.assertEqual(report["overview"]["skills_identified"], 6)
        self.assertEqual(report["overview"]["skills_with_evidence"], 4)
        self.assertEqual(report["overview"]["skills_requiring_review"], 3)
        self.assertLessEqual(len(report["quality"]["observations"]), 4)

    def test_missing_resume_data_is_reported_without_invention(self):
        candidate = SimpleNamespace(
            skills=[],
            projects="",
            experience_summary="",
            experience_years=None,
            education="",
        )
        report = build_validation_report("", candidate, self.vacancy)

        self.assertEqual(report["experience"], [])
        self.assertEqual(report["projects"], [])
        self.assertEqual(
            report["quality"]["missing_sections"],
            [
                "Education information",
                "Skills section",
                "Project descriptions",
                "Work experience information",
            ],
        )
        self.assertTrue(all(item["status"] == "Evidence not found" for item in report["skills"]))

    def test_quality_report_flags_repetition_and_brief_projects(self):
        candidate = SimpleNamespace(
            skills=[],
            projects="",
            experience_summary="",
            experience_years=None,
            education="",
        )
        vacancy = SimpleNamespace(
            title="Python Engineer",
            required_skills="Python",
            preferred_skills="",
            description="",
            responsibilities="",
            education="",
        )
        resume_text = "Skills\nPython, Python, Python\nProjects\nToy project\nExperience\nWorked at Acme."

        report = build_validation_report(resume_text, candidate, vacancy)

        self.assertEqual(report["quality"]["repeated_keywords"], [{"keyword": "Python", "count": 3}])
        self.assertEqual(report["quality"]["unsupported_skills"], ["Python"])
        self.assertEqual(
            report["quality"]["incomplete_projects"][0]["title"],
            "Toy project",
        )
        self.assertIn("not be used", report["quality"]["disclaimer"])
        self.assertEqual(report["quality"]["observations"][0], "Skills mentioned without project or experience evidence: Python.")

    def test_validation_does_not_change_existing_skill_score(self):
        candidate = SimpleNamespace(
            skills=[],
            education="",
            experience_years=None,
            projects="",
        )
        vacancy = SimpleNamespace(
            title="API Engineer",
            required_skills="FastAPI",
            preferred_skills="",
            description="",
            responsibilities="",
            education="",
            min_experience=0,
            max_experience=0,
        )
        resume_text = "Skills\nFastAPI"

        report = build_validation_report(resume_text, candidate, vacancy)
        score = calculate_match(resume_text, candidate, vacancy)

        self.assertEqual(report["skills"][0]["status"], "Mentioned only")
        self.assertEqual(score["required_skills"], 0.0)
        self.assertEqual(score["final_score"], 10.0)

    def test_existing_weighted_score_formula_remains_unchanged(self):
        candidate = SimpleNamespace(
            skills=[SimpleNamespace(name="Python"), SimpleNamespace(name="Flask")],
            education="B.Tech",
            experience_years=1,
        )
        vacancy = SimpleNamespace(
            title="Python role",
            description="Python role",
            responsibilities="",
            required_skills="Python, SQL",
            preferred_skills="Flask",
            education="B.Tech",
            min_experience=1,
            max_experience=3,
        )

        result = calculate_match("Python role", candidate, vacancy)
        expected = (
            result["description_similarity"] * 0.35
            + 50 * 0.30
            + 100 * 0.20
            + 100 * 0.10
            + 100 * 0.05
        )

        self.assertEqual(result["required_skills"], 50.0)
        self.assertEqual(result["preferred_skills"], 100.0)
        self.assertEqual(result["experience_match"], 100.0)
        self.assertEqual(result["education_match"], 100.0)
        self.assertEqual(result["final_score"], round(expected, 2))


if __name__ == "__main__":
    unittest.main()
