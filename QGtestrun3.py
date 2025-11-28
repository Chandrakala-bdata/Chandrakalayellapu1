"""
LLM Quiz Generator using Gemini AI + MySQL
------------------------------------------
Generates MCQs and stores structured questions into database.
"""

import os
import re
import mysql.connector
from dotenv import load_dotenv
import google.generativeai as genai

# ==============================
# 1. Load configuration
# ==============================
load_dotenv()

class Config:
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", 3306))
    DB_NAME = os.getenv("DB_NAME", "quizdb")
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash-preview")


# ==============================
# 2. Database Handling
# ==============================
class Database:
    def __init__(self):
        try:
            self.conn = mysql.connector.connect(
                host=Config.DB_HOST,
                port=Config.DB_PORT,
                database=Config.DB_NAME,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
            )
            print("✅ Connected to MySQL database.")
        except mysql.connector.Error as e:
            print(f"❌ Database connection error: {e}")
            self.conn = None

    def get_all_topics(self):
        if not self.conn:
            return []

        cursor = self.conn.cursor()
        cursor.execute("SELECT DISTINCT skills FROM skill_set;")
        topics = [row[0] for row in cursor.fetchall()]
        cursor.close()
        return topics

    def get_content_for_skill(self, skill):
        if not self.conn:
            return ""

        cursor = self.conn.cursor(dictionary=True)
        query = "SELECT Content FROM skill_set WHERE skills = %s;"
        cursor.execute(query, (skill,))
        rows = cursor.fetchall()
        cursor.close()
        return " ".join([r["Content"] for r in rows]) if rows else ""

    def save_question(self, question_no, skill, mode, q):
        """Insert parsed question data into quiz_questions table"""
        if not self.conn:
            return False

        query = """
            INSERT INTO quiz_questions
            (question_no, skill, mode, question, option_a, option_b, option_c, option_d, correct_answer)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        cursor = self.conn.cursor()
        cursor.execute(query, (
            question_no,
            skill,
            mode,
            q["question"],
            q["A"],
            q["B"],
            q["C"],
            q["D"],
            q["answer"]
        ))
        self.conn.commit()
        cursor.close()
        return True


# ==============================
# 3. Parse Quiz Output
# ==============================
def parse_quiz_output(quiz_text):
    """
    Extract:
    Q1. question
    A) option1
    B) option2
    C) option3
    D) option4
    Answer: B
    """
    pattern = r"Q(\d+)\.\s*(.*?)\s*A\)\s*(.*?)\s*B\)\s*(.*?)\s*C\)\s*(.*?)\s*D\)\s*(.*?)\s*Answer:\s*([A-D])"
    matches = re.findall(pattern, quiz_text, re.S)

    parsed = []
    for qno, q, a, b, c, d, ans in matches:
        parsed.append({
            "question_no": int(qno),
            "question": q.strip(),
            "A": a.strip(),
            "B": b.strip(),
            "C": c.strip(),
            "D": d.strip(),
            "answer": ans.strip(),
        })
    return parsed


# ==============================
# 4. Quiz Generator
# ==============================
class QuizGenerator:
    def __init__(self):
        if not Config.GEMINI_API_KEY:
            print("❌ GEMINI_API_KEY missing in .env")
            exit(1)

        genai.configure(api_key=Config.GEMINI_API_KEY)
        self.model = genai.GenerativeModel("gemini-2.5-flash")
        self.db = Database()

    def _build_prompt(self, skill, level, num_questions, content):
        return f"""
Generate {num_questions} {level}-level multiple choice questions 
based on the skill: {skill}.

Use this context:
{content}

Format Strictly:
Q1. <question>
A) <option>
B) <option>
C) <option>
D) <option>
Answer: <A/B/C/D>
"""

    def generate_quiz(self, skill, level, num_questions):
        content = self.db.get_content_for_skill(skill)
        if not content:
            return f"No content found for skill: {skill}"

        prompt = self._build_prompt(skill, level, num_questions, content)
        print("🔹 Generating quiz...")

        response = self.model.generate_content(prompt)
        return response.text.strip()


# ==============================
# 5. Main Application
# ==============================
def main():
    print("\n=== LLM QUIZ GENERATOR ===\n")
    quiz_gen = QuizGenerator()
    db = quiz_gen.db

    topics = db.get_all_topics()
    if not topics:
        print("No topics found in database.")
        return

    print("Available Skills:")
    for t in topics:
        print(f" - {t}")

    skill = input("\nEnter skill: ").strip()
    level = input("Enter level (Beginner / Intermediate / Expert): ").strip()
    num_q = int(input("Enter number of questions: ").strip())

    quiz_output = quiz_gen.generate_quiz(skill, level, num_q)

    print("\n=== GENERATED QUIZ ===\n")
    print(quiz_output)

    parsed_questions = parse_quiz_output(quiz_output)

    if not parsed_questions:
        print("❌ Parsing failed. Check Gemini output format.")
        return

    for q in parsed_questions:
        db.save_question(q["question_no"], skill, level, q)

    print(f"\n✅ {len(parsed_questions)} questions saved to database successfully!")


if __name__ == "__main__":
    main()
