import json
import random

# 📂 1. JSON faylni o'qish
def load_questions():
    with open("questions.json", "r", encoding="utf-8") as file:
        return json.load(file)

# 🔍 2. Foydalanuvchi matnidan kalit so'zni izlash
def find_keyword_in_text(text, keywords):
    text = text.lower()
    for keyword in keywords:
        if keyword.lower() in text:
            return keyword
    return None

# 🗨️ 3. Chat sikli
def chat():
    questions = load_questions()

    print("🤖 TorexTalk bot: Xush kelibsiz! ('exit' deb yozing chiqish uchun)")

    while True:
        user_input = input("Siz: ")
        if user_input.lower() in ["exit", "chiqish", "quit"]:
            print("Bot: Keling, keyingi safar chatlaymiz 😊")
            break

        # Barcha savollarni kalit so'z sifatida saqlash
        all_questions = [item["question"] for item in questions]

        # Matnda kalit so'z borligini tekshirish
        matched_question = find_keyword_in_text(user_input, all_questions)

        if matched_question:
            # Mos savol topilsa, uning javoblaridan birini tanlash
            matched_item = next(item for item in questions if item["question"] == matched_question)
            response = random.choice(matched_item["responses"])
            print(f"Bot: {response}")
        else:
            print("Bot: Bu savol haqida nimanidir kiriting.")