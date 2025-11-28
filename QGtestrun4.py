"""
LLM Quiz Generator using Gemini AI + MySQL
Ensures:
- Per-resume unique questions (strictly no repetition)
- Quiz results stored with score
- Questions stored in DB
"""

import os
import re
import mysql.connector
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

# ==============================
# 1. Configuration
# ==============================
class Config:
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", 3306))
    DB_NAME = os.getenv("DB_NAME", "quizdb")
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash-preview")


# ==============================
# 2. Database Handler
# ==============================
class Database:
    def __init__(self):
        self.conn = mysql.connector.connect(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            database=Config.DB_NAME,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
        )

    def get_all_topics(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT DISTINCT skills FROM skill_set;")
        topics = [r[0] for r in cursor.fetchall()]
        cursor.close()
        return topics

    def get_content_for_skill(self, skill):
        cursor = self.conn.cursor(dictionary=True)
        cursor.execute("SELECT Content FROM skill_set WHERE skills=%s;", (skill,))
        rows = cursor.fetchall()
        cursor.close()
        return " ".join([r["Content"] for r in rows])

    def question_used_before(self, resume_id, question):
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id FROM resume_history WHERE resume_id=%s AND question=%s;",
            (resume_id, question),
        )
        result = cursor.fetchone()
        cursor.close()
        return result is not None

    def store_used_question(self, resume_id, question):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO resume_history (resume_id, question) VALUES (%s,%s);",
            (resume_id, question),
        )
        self.conn.commit()
        cursor.close()

    def store_question(self, q):
        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT INTO quiz_questions
               (question_no, skill, mode, question, option_a, option_b, option_c, option_d, correct_answer)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s);""",
            (
                q["question_no"],
                q["skill"],
                q["mode"],
                q["question"],
                q["A"],
                q["B"],
                q["C"],
                q["D"],
                q["correct"],
            ),
        )
        self.conn.commit()
        cursor.close()

    def store_score(self, resume_id, skill, mode, total, correct):
        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT INTO quiz_attempts
               (resume_id, skill, mode, total_questions, correct_answers)
               VALUES (%s,%s,%s,%s,%s);""",
            (resume_id, skill, mode, total, correct),
        )
        self.conn.commit()
        cursor.close()


# ==============================
# 3. Quiz Generator
# ==============================
class QuizGenerator:
    def __init__(self):
        genai.configure(api_key=Config.GEMINI_API_KEY)
        self.db = Database()

    def _build_prompt(self, skill, level, num_questions, content):
        return f"""
Generate {num_questions} {level}-level MCQs for skill {skill}.
Use this context: {content}

Format:
Q1. <question>
A) <option>
B) <option>
C) <option>
D) <option>
Answer: <letter>
"""

    def _parse_questions(self, text):
        questions = []
        blocks = re.split(r"Q\d+\.", text)
        for block in blocks[1:]:
            lines = block.strip().split("\n")
            q_text = lines[0].strip()
            A = lines[1].split(")", 1)[1].strip()
            B = lines[2].split(")", 1)[1].strip()
            C = lines[3].split(")", 1)[1].strip()
            D = lines[4].split(")", 1)[1].strip()
            correct = lines[5].split(":")[1].strip()

            questions.append({
                "question": q_text,
                "A": A,
                "B": B,
                "C": C,
                "D": D,
                "correct": correct,
            })
        return questions

    def generate_unique_questions(self, resume_id, skill, level, num_questions):
        content = self.db.get_content_for_skill(skill)

        prompt = self._build_prompt(skill, level, num_questions * 2, content)
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        parsed = self._parse_questions(response.text)

        final_qs = []
        q_no = 1

        for q in parsed:
            if len(final_qs) == num_questions:
                break

            if not self.db.question_used_before(resume_id, q["question"]):
                q["question_no"] = q_no
                q["skill"] = skill
                q["mode"] = level
                final_qs.append(q)
                self.db.store_used_question(resume_id, q["question"])
                self.db.store_question(q)
                q_no += 1

        if len(final_qs) < num_questions:
            return "Not enough unique questions found. Try again."

        return final_qs


# ==============================
# 4. Main App
# ==============================
def main():
    print("\n=== LLM QUIZ GENERATOR ===\n")
    quiz = QuizGenerator()
    db = quiz.db

    topics = db.get_all_topics()
    print("\nSkills Available:")
    for s in topics:
        print(" -", s)

    skill = input("\nEnter skill: ").strip()
    level = input("Enter level (Beginner / Intermediate / Expert): ").strip()
    resume_id = int(input("Enter Resume ID: ").strip())
    num_q = int(input("How many questions? ").strip())

    qs = quiz.generate_unique_questions(resume_id, skill, level, num_q)

    print("\n=== QUIZ ===\n")
    correct_count = 0

    for q in qs:
        print(f"Q{q['question_no']}. {q['question']}")
        print("A)", q["A"])
        print("B)", q["B"])
        print("C)", q["C"])
        print("D)", q["D"])
        ans = input("Your answer: ").strip().upper()

        if ans == q["correct"]:
            correct_count += 1

    db.store_score(resume_id, skill, level, num_q, correct_count)


    print("\n=== RESULT ===")
    print("Score:", correct_count, "/", num_q)

    print("\n=== CORRECT ANSWERS ===")
    for q in qs:
        print(f"Q{q['question_no']}: Correct Option = {q['correct']}")


if __name__ == "__main__":
    main()
