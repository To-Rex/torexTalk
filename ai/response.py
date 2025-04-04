import json
import random
from rapidfuzz import process, fuzz

class CustomChatBot:
    def __init__(self, data_path):
        # JSON faylini yuklash
        with open(data_path, "r", encoding="utf-8") as file:
            self.data = json.load(file)
        
        # Sukut bo'yicha javoblar
        self.default_responses = [""]
        
        # Savollar va javoblarni tezkor xotirada saqlash
        self.indexed_questions = {
            pair["question"].lower(): pair["responses"]
            for pair in self.data["data"]["pairs"]
        }
        
        # Savollar ro'yxatini oldindan tuzish
        self.questions = list(self.indexed_questions.keys())
    
    def train(self):
        # Modelni o'qitish jarayoni
        print("Model o'qitildi! Kiritilgan savollarga asoslangan javoblar tayyor.")
    
    def respond(self, user_input):
        # Foydalanuvchi kiritgan matnni kichik harfga o'tkazish
        user_input = user_input.lower()
        
        # Eng yaxshi moslikni oldindan tuzilgan savollar ro'yxatidan topish
        best_match = process.extractOne(user_input, self.questions, scorer=fuzz.ratio)
        
        if best_match and best_match[1] > 70:  # Agar o'xshashlik 70% dan yuqori bo'lsa
            matched_question = best_match[0]
            return random.choice(self.indexed_questions[matched_question])  # Tasodifiy javob qaytarish
        else:
            # Sukut bo'yicha javob
            return random.choice(self.default_responses)
    
    def question(self, user_input):
        # Foydalanuvchi kiritgan savolga javob qaytarish
        return self.respond(user_input)

# Ma'lumotlarni yuklash
#data_path = "data.json"  # JSON fayl manzili
#avto_bot = CustomChatBot(data_path)

# Modelni o'qitish
#avto_bot.train()