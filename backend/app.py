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
    api_key=os.getenv("OPENAI_API_KEY")
)

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
# CHAT GPT (MULTI TURN)
# =========================
@app.route('/chat', methods=['POST'])
def chat():

    try:
        
        data = request.json

        user_id = data.get("user_id")
        pesan = data.get("pesan")

        if not user_id or not pesan:
            return jsonify({
                "message": "user_id dan pesan wajib diisi."
            }), 400

        # =========================
        # AMBIL 20 RIWAYAT CHAT TERAKHIR
        # =========================
        history = supabase.table("chats") \
        .select("*") \
        .eq("user_id", user_id) \
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
                "content": """
            Kamu adalah AI Curhat Akademik yang membantu mahasiswa Indonesia.

            TUJUAN:
            - Membantu mahasiswa menghadapi stres akademik.
            - Memberikan dukungan emosional ringan.
            - Membantu manajemen waktu.
            - Membantu tugas kuliah dan skripsi.

            ATURAN:
            - Selalu gunakan Bahasa Indonesia.
            - Bersikap empatik.
            - Jangan menghakimi pengguna.
            - Berikan solusi yang praktis.
            - Ingat konteks percakapan sebelumnya.
            - Jangan memberikan diagnosis medis.
            - Jangan memberikan saran hukum.
            - Jangan memberikan saran keuangan.
            """
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
            "role": "user",
            "content": pesan
        })

        # =========================
        # REQUEST KE OPENAI
        # =========================
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.7,
            max_tokens=500,
            messages=messages
        )

        hasil = response.choices[0].message.content

        return jsonify({
            "respon_gpt": hasil
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
    pesan_user = data.get("pesan_user")
    respon_gpt = data.get("respon_gpt", "")

    if not user_id or not pesan_user:
        return jsonify({
            "message": "user_id dan pesan_user wajib diisi."
        }), 400

    response = supabase.table("chats").insert({
        "user_id": user_id,
        "pesan_user": pesan_user,
        "respon_gpt": respon_gpt
    }).execute()

    return jsonify({
        "message": "Chat berhasil disimpan",
        "data": response.data
    })

# =========================
# AMBIL RIWAYAT CHAT
# =========================
@app.route('/get-chat/<user_id>', methods=['GET'])
def get_chat(user_id):

    response = supabase.table("chats") \
        .select("*") \
        .eq("user_id", user_id) \
        .order("created_at") \
        .execute()

    return jsonify(response.data)

# =========================
# RUN APP
# =========================
if __name__ == "__main__":
    app.run()
