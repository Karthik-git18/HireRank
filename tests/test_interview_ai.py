import json
import unittest

from interview_ai import InterviewGenerationError, _validated_questions


class InterviewQuestionValidationTests(unittest.TestCase):
    def test_three_or_more_questions_cover_core_question_types(self):
        response = json.dumps({
            "questions": [
                {"category": "Technical", "question": "How would you test this API?"},
                {"category": "Practical", "question": "How would you implement pagination?"},
                {"category": "Experience-Based", "question": "Describe a relevant project."},
            ]
        })

        result = _validated_questions(response, 3)

        self.assertEqual(len(result["questions"]), 3)

    def test_missing_experience_question_is_rejected(self):
        response = json.dumps({
            "questions": [
                {"category": "Technical", "question": "Explain the design."},
                {"category": "Practical", "question": "How would you implement it?"},
                {"category": "Scenario-Based", "question": "What would you do if it failed?"},
            ]
        })

        with self.assertRaisesRegex(InterviewGenerationError, "experience-based"):
            _validated_questions(response, 3)


if __name__ == "__main__":
    unittest.main()
