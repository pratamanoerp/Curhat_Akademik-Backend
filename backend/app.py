import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client
from openai import OpenAI
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
CORS(app)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# =========================
# SUPABASE
# =========================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================
# OPENAI
# =========================
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=60
)

SYSTEM_PROMPT = """
Kamu adalah Curhat Akademik AI, sebuah AI Assistant yang dirancang khusus
untuk membantu mahasiswa Indonesia dalam menghadapi berbagai permasalahan akademik.

IDENTITAS
- Nama: Curhat Akademik AI
- Fokus: Pendamping akademik mahasiswa.
- Bahasa utama: Indonesia.

TUJUAN
1. Membantu mahasiswa memahami masalah akademiknya.
2. Memberikan solusi yang realistis.
3. Memberikan dukungan emosional ringan.
4. Membantu mahasiswa membuat rencana tindakan.

RUANG LINGKUP
- Skripsi
- Tugas kuliah
- Ujian
- Burnout
- Manajemen waktu
- Presentasi
- Revisi dosen
- Organisasi
- Magang
- Kerja kelompok
- Motivasi belajar

ATURAN
- Gunakan bahasa Indonesia yang sopan.
- Tunjukkan empati.
- Jangan menghakimi pengguna.
- Jangan memberikan diagnosis medis.
- Jangan memberikan saran hukum.
- Jangan memberikan saran investasi atau keuangan.
- Jika informasi kurang lengkap, ajukan pertanyaan terlebih dahulu.
- Gunakan konteks percakapan sebelumnya.
- Jika pengguna bertanya di luar topik akademik, jawab secara sopan bahwa AI ini dirancang khusus untuk membantu permasalahan akademik mahasiswa, kemudian arahkan kembali ke topik akademik.
FORMAT JAWABAN

📌 Ringkasan Masalah
Tuliskan inti masalah pengguna.

🔍 Pemahaman AI
Jelaskan penyebab atau kondisi yang mungkin terjadi berdasarkan informasi pengguna.

✅ Solusi
Berikan langkah-langkah yang praktis.

📅 Langkah Selanjutnya
Berikan tindakan yang bisa dilakukan hari ini.

🌱 Motivasi
Tutup dengan kalimat yang memotivasi.
"""

# =========================
# HOME
# =========================
@app.route('/')
def home():
    return "Backend berjalan"

# =========================
# REGISTER
# =========================
@app.route('/register', methods=['POST'])
def register():

    data = request.json

    nama = data.get("nama")
    email = data.get("email")
    password = data.get("password")

    if not nama or not email or not password:
        return jsonify({
            "message": "Semua data harus diisi."
        }), 400

    # Cek apakah email sudah digunakan
    cek = supabase.table("users") \
        .select("*") \
        .eq("email", email) \
        .execute()

    if len(cek.data) > 0:
        return jsonify({
            "message": "Email sudah terdaftar."
        }), 400

    hashed_password = generate_password_hash(password)

    response = supabase.table("users").insert({
        "nama": nama,
        "email": email,
        "password": hashed_password
    }).execute()

    return jsonify({
        "message": "Register berhasil",
        "data": response.data
    })

# =========================
# LOGIN
# =========================
@app.route('/login', methods=['POST'])
def login():

    data = request.json

    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({
            "message": "Email dan password harus diisi."
        }), 400

    response = supabase.table("users") \
        .select("*") \
        .eq("email", email) \
        .execute()

    if len(response.data) == 0:
        return jsonify({
            "message": "Email atau password salah"
        }), 401

    user = response.data[0]

    if check_password_hash(user["password"], password):

        return jsonify({
            "message": "Login berhasil",
            "user": user
        })

    return jsonify({
        "message": "Email atau password salah"
    }), 401

# =========================
# NEW CHAT
# =========================
@app.route('/new-chat', methods=['POST'])
def new_chat():

    data = request.json

    user_id = data.get("user_id")
    title = data.get("title", "Chat Baru")

    if not user_id:
        return jsonify({
            "message": "user_id wajib diisi."
        }), 400

    response = supabase.table("chat_sessions").insert({
        "user_id": user_id,
        "title": title
    }).execute()

    return jsonify({
        "message": "Session berhasil dibuat",
        "session": response.data[0]
    })

# =========================
# CHAT GPT (MULTI TURN)
# =========================
@app.route('/chat', methods=['POST'])
def chat():

    try:
        
        data = request.json

        user_id = data.get("user_id")
        session_id = data.get("session_id")
        pesan = data.get("pesan", "").strip()
       
        if not user_id or not session_id or not pesan:
            return jsonify({
                "message": "user_id dan pesan wajib diisi."
            }), 400

        # =========================
        # AMBIL 20 RIWAYAT CHAT TERAKHIR
        # =========================
        history = supabase.table("chats") \
        .select("*") \
        .eq("session_id", session_id) \
        .order("created_at", desc=True) \
        .limit(20) \
        .execute()

         # Balik lagi supaya urut dari lama ke baru
        history_data = list(reversed(history.data))

        # =========================
        # SUSUN MESSAGES
        # =========================
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            }
        ]
        
        # =========================
        # MASUKKAN RIWAYAT CHAT
        # =========================
        for item in history_data:

            messages.append({
                "role": "user",
                "content": item["pesan_user"]
            })

            if item["respon_gpt"]:
                messages.append({
                    "role": "assistant",
                    "content": item["respon_gpt"]
                })

        # =========================
        # PESAN TERBARU USER
        # =========================
        messages.append({
        "role": "system",
         "content": """
        Sebelum menjawab:

        1. Pahami konteks pengguna.
        2. Tentukan apakah pengguna mengalami:
        - Burnout akademik
        - Stres akademik
        - Kesulitan manajemen waktu
        - Kesulitan skripsi
        - Kecemasan ujian
        - Kehilangan motivasi
        3. Sesuaikan gaya bahasa dengan kondisi pengguna.
        4. Jangan memberikan diagnosis medis.
        5. Jika informasi dari pengguna belum cukup, ajukan satu pertanyaan klarifikasi sebelum memberikan solusi.
        """
        })

        messages.append({
            "role": "user",
            "content": pesan
        })

        # =========================
        # REQUEST KE OPENAI
        # =========================
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.6,
            max_tokens=700,
            presence_penalty=0.3,
            frequency_penalty=0.2,
        )

        hasil = response.choices[0].message.content
        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        total_tokens = usage.total_tokens if usage else 0

        return jsonify({
            "respon_gpt": hasil,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens
            }
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

# =========================
# SIMPAN CHAT
# =========================
@app.route('/save-chat', methods=['POST'])
def save_chat():

    data = request.json

    user_id = data.get("user_id")
    session_id = data.get("session_id")
    pesan_user = data.get("pesan_user")
    respon_gpt = data.get("respon_gpt", "")

    if not user_id or not session_id or not pesan_user:
        return jsonify({
            "message": "user_id dan pesan_user wajib diisi."
        }), 400

    response = supabase.table("chats").insert({
        "user_id": user_id,
        "session_id": session_id,
        "pesan_user": pesan_user,
        "respon_gpt": respon_gpt
    }).execute()

    # =========================
    # UPDATE JUDUL CHAT
    # =========================
    session = supabase.table("chat_sessions") \
            .select("title") \
            .eq("id", session_id) \
            .single() \
            .execute()

    if session.data and session.data["title"] == "Chat Baru":

        judul = pesan_user[:40]

        if len(pesan_user) > 40:
            judul += "..."

        session = (
            supabase.table("chat_sessions")
            .select("title")
            .eq("id", session_id)
            .single()
            .execute()
        )

    # =========================
    # RESPONSE
    # =========================
    return jsonify({
         "message": "Chat berhasil disimpan",
        "data": response.data
    })

# =========================
# GET CHAT SESSIONS
# =========================
@app.route('/chat-sessions/<user_id>', methods=['GET'])
def get_chat_sessions(user_id):

    response = supabase.table("chat_sessions") \
        .select("*") \
        .eq("user_id", user_id) \
        .order("created_at", desc=True) \
        .execute()

    return jsonify(response.data)

# =========================
# AMBIL RIWAYAT CHAT
# =========================
@app.route('/get-chat/<session_id>', methods=['GET'])
def get_chat(session_id):

    response = supabase.table("chats") \
        .select("*") \
        .eq("session_id", session_id) \
        .order("created_at") \
        .execute()

    return jsonify(response.data)

# =========================
# RUN APP
# =========================
if __name__ == "__main__":
    app.run(debug=True)