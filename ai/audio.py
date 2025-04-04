import speech_recognition as sr
from pydub import AudioSegment
import io
import os

def ogg_to_text(file_path, language="uz-UZ"):
    try:
        # OGG formatdagi faylni to'g'ridan-to'g'ri audio data sifatida yuklash
        audio = AudioSegment.from_file(file_path, format="ogg")
        
        # Audio segmentni in-memory formatida saqlash
        audio_bytes = io.BytesIO()
        audio.export(audio_bytes, format="wav")
        audio_bytes.seek(0)  # Pointerni boshiga olib borish
        
        # SpeechRecognition yordamida audio matnga aylantirish
        recognizer = sr.Recognizer()
        with sr.AudioFile(audio_bytes) as source:
            audio_data = recognizer.record(source)
            try:
                # Google Speech-to-Text API bilan tanish
                text = recognizer.recognize_google(audio_data, language=language)
                
                # Audio faylni o'chirish
                os.remove(file_path)
                #print(text)
                return text
            except sr.UnknownValueError:
                return "Xato: Audio matnni aniqlab bo'lmadi."
            except sr.RequestError as e:
                return f"Xato: Xatolik yuz berdi: {e}"
    except Exception as e:
        return f"Xato: {e}"
