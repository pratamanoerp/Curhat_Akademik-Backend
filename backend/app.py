import os
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client
from openai import OpenAI
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet

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

# =========================
# ENKRIPSI CHAT
# =========================
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if not ENCRYPTION_KEY:
    raise ValueError("ENCRYPTION_KEY belum diatur di file .env")

cipher = Fernet(ENCRYPTION_KEY.encode())

def encrypt_text(text):
    return cipher.encrypt(text.encode()).decode()

def decrypt_text(text):
    return cipher.decrypt(text.encode()).decode()

# =========================
# LIMIT CHAT HARIAN
# =========================
DAILY_CHAT_LIMIT = 20


def get_today_chat_count(user_id):

    jakarta = ZoneInfo("Asia/Jakarta")
    now_jakarta = datetime.now(jakarta)

    start_jakarta = now_jakarta.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    end_jakarta = now_jakarta.replace(
        hour=23,
        minute=59,
        second=59,
        microsecond=999999
    )

    start_utc = start_jakarta.astimezone(timezone.utc)
    end_utc = end_jakarta.astimezone(timezone.utc)

    response = (
        supabase.table("chats")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .gte("created_at", start_utc.isoformat())
        .lte("created_at", end_utc.isoformat())
        .execute()
    )

    return response.count or 0

def search_academic_data(pesan):
    text = pesan.lower().strip()

    # =====================================================
    # 1. VALIDASI UNIVERSITAS
    # Sistem hanya untuk Fakultas Teknik UNIS
    # =====================================================

    university_keywords = [
    "umt",
    "universitas muhammadiyah tangerang",
    "raharja",
    "universitas raharja",
    "untirta",
    "universitas sultan ageng tirtayasa",
    "trisakti",
    "binus",
    "mercu buana",
    "mercubuana",
    "paramadina",
    "gunadarma",
    "telkom",
    "esa unggul",
    "muhammadiyah"
    ]

    unis_keywords = [
        "unis",
        "universitas islam syekh-yusuf",
        "universitas islam syekh yusuf",
        "syekh-yusuf",
        "syekh yusuf",
        "fakultas teknik unis"
    ]

    # Jika pesan menyebut UNIS, berarti konteks sesuai
    menyebut_unis = any(
        keyword in text
        for keyword in unis_keywords
    )

    # Cari apakah pesan menyebut universitas/kampus tertentu
    menyebut_kampus = any(
        keyword in text
        for keyword in university_keywords
    )

    # Jika menyebut kampus tetapi bukan UNIS,
    # jangan gunakan database UNIS
    if menyebut_kampus and not menyebut_unis:

        return {
            "type": "blocked",
            "message": (
                "Maaf, sistem ini khusus menyediakan informasi "
                "akademik Fakultas Teknik Universitas Islam "
                "Syekh-Yusuf Tangerang (UNIS)."
            )
        }

    # =====================================================
    # 2. DETEKSI UAS DAN UTS
    # =====================================================

    is_uas = any(keyword in text for keyword in [
        "uas",
        "ujian akhir semester",
        "ujian akhir"
    ])

    is_uts = any(keyword in text for keyword in [
        "uts",
        "ujian tengah semester",
        "ujian tengah"
    ])

    # =====================================================
    # 3. DETEKSI PERMINTAAN JADWAL / TANGGAL
    # =====================================================

    meminta_jadwal = any(keyword in text for keyword in [
        "kapan",
        "tanggal",
        "jadwal",
        "dilaksanakan",
        "pelaksanaan",
        "hari"
    ])

    # =====================================================
    # 4. UAS / UTS TANPA PERMINTAAN JADWAL
    # Hanya berikan penjelasan umum
    # =====================================================

    if (is_uas or is_uts) and not meminta_jadwal:

        if is_uas:
            return {
                "type": "general",
                "message": (
                    "UAS adalah Ujian Akhir Semester yang dilaksanakan "
                    "untuk mengevaluasi hasil pembelajaran mahasiswa "
                    "pada akhir semester."
                )
            }

        if is_uts:
            return {
                "type": "general",
                "message": (
                    "UTS adalah Ujian Tengah Semester yang dilaksanakan "
                    "untuk mengevaluasi hasil pembelajaran mahasiswa "
                    "pada pertengahan semester."
                )
            }

    # =====================================================
    # 5. KEYWORD AKADEMIK LOKAL
    # =====================================================

    keyword_map = {

        "uas": [
            "uas",
            "ujian akhir semester",
            "ujian akhir"
        ],

        "uts": [
            "uts",
            "ujian tengah semester",
            "ujian tengah"
        ],

        "krs": [
            "krs",
            "pengisian krs",
            "isi krs",
            "mengisi krs",
            "ambil krs"
        ],

        "kuliah": [
            "kuliah",
            "perkuliahan",
            "masuk kuliah",
            "mulai kuliah",
            "perkuliahan dimulai"
        ],

        "registrasi": [
            "registrasi",
            "her registrasi",
            "daftar ulang",
            "registrasi ulang"
        ],

        "cuti": [
            "cuti",
            "cuti akademik"
        ],

        "seminar": [
            "seminar",
            "seminar skripsi",
            "seminar proposal"
        ],

        "sidang": [
            "sidang",
            "sidang skripsi",
            "ujian skripsi",
            "yudisium"
        ],

        "skripsi": [
            "skripsi",
            "yudisium"
        ],

        "wisuda": [
            "wisuda",
            "acara wisuda"
        ],

        "nilai": [
            "entry nilai",
            "input nilai",
            "masukkan nilai",
            "nilai"
        ]
    }

    # =====================================================
    # 6. DETEKSI KATEGORI
    # =====================================================

    kategori_ditemukan = []

    for kategori, keywords in keyword_map.items():

        for keyword in keywords:

            if keyword in text:
                kategori_ditemukan.append(kategori)
                break

    # Tidak ada kategori yang cocok
    if not kategori_ditemukan:
        return None

    # =====================================================
    # 7. DETEKSI SEMESTER
    # =====================================================

    semester_filter = None

    if "ganjil" in text:
        semester_filter = "Ganjil"

    elif "genap" in text:
        semester_filter = "Genap"

    # =====================================================
    # 8. AMBIL DATA DARI DATABASE
    # =====================================================

    response = (
        supabase.table("academic_data")
        .select("*")
        .eq("tahun_akademik", "2026/2027")
        .execute()
    )

    data = response.data or []

    # =====================================================
    # 9. FILTER SEMESTER
    # =====================================================

    if semester_filter:

        data = [
            item
            for item in data
            if item["semester"] == semester_filter
        ]

    # =====================================================
    # 10. CARI DATA YANG RELEVAN
    # =====================================================

    hasil = []

    for item in data:

        kegiatan = item["kegiatan"].lower()

        cocok = False

        # -------------------------
        # UAS
        # -------------------------

        if "uas" in kategori_ditemukan:

            if "ujian akhir semester" in kegiatan:
                cocok = True

        # -------------------------
        # UTS
        # -------------------------

        if "uts" in kategori_ditemukan:

            if "ujian tengah semester" in kegiatan:
                cocok = True

        # -------------------------
        # KRS
        # -------------------------

        if "krs" in kategori_ditemukan:

            if "krs" in kegiatan:
                cocok = True

        # -------------------------
        # KULIAH
        # -------------------------

        if "kuliah" in kategori_ditemukan:

            if "perkuliahan" in kegiatan:
                cocok = True

        # -------------------------
        # REGISTRASI
        # -------------------------

        if "registrasi" in kategori_ditemukan:

            if "registrasi" in kegiatan:
                cocok = True

        # -------------------------
        # CUTI
        # -------------------------

        if "cuti" in kategori_ditemukan:

            if "cuti akademik" in kegiatan:
                cocok = True

        # -------------------------
        # SEMINAR
        # -------------------------

        if "seminar" in kategori_ditemukan:

            if "seminar" in kegiatan:
                cocok = True

        # -------------------------
        # SIDANG
        # -------------------------

        if "sidang" in kategori_ditemukan:

            if (
                "sidang" in kegiatan
                or "yudisium" in kegiatan
            ):
                cocok = True

        # -------------------------
        # SKRIPSI
        # -------------------------

        if "skripsi" in kategori_ditemukan:

            if (
                "skripsi" in kegiatan
                or "yudisium" in kegiatan
            ):
                cocok = True

        # -------------------------
        # WISUDA
        # -------------------------

        if "wisuda" in kategori_ditemukan:

            if "wisuda" in kegiatan:
                cocok = True

        # -------------------------
        # NILAI
        # -------------------------

        if "nilai" in kategori_ditemukan:

            if "nilai" in kegiatan:
                cocok = True

        # Masukkan hasil
        if cocok:
            hasil.append(item)

    # =====================================================
    # 11. JIKA TIDAK ADA DATA
    # =====================================================

    if not hasil:
        return None

    # =====================================================
    # 12. KEMBALIKAN DATA DATABASE
    # =====================================================

    return {
        "type": "database",
        "data": hasil
    }

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

INSTRUKSI PEMROSESAN
Sebelum memberikan jawaban:
1. Pahami konteks pengguna berdasarkan pesan yang dikirim dan riwayat percakapan.
2. Identifikasi apakah pengguna mengalami:
   - Burnout akademik
   - Stres akademik
   - Kesulitan manajemen waktu
   - Kesulitan skripsi
   - Kecemasan menghadapi ujian
   - Kehilangan motivasi belajar
3. Sesuaikan gaya bahasa dengan kondisi pengguna.
4. Jangan memberikan diagnosis medis.
5. Jika informasi dari pengguna belum cukup, ajukan satu pertanyaan klarifikasi sebelum memberikan solusi.

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
# RULE-BASED VALIDATION
# =========================
ACADEMIC_KEYWORDS = [
    "akademik",
    "kuliah",
    "kampus",
    "mahasiswa",
    "dosen",
    "skripsi",
    "tugas",
    "ujian",
    "uts",
    "uas",
    "sidang",
    "seminar",
    "proposal",
    "penelitian",
    "presentasi",
    "kelas",
    "nilai",
    "ipk",
    "magang",
    "praktikum",
    "revisi",
    "bimbingan",
    "belajar",
    "semester",
    "mata kuliah",
    "organisasi",
    "kkn",
    "pkl",
    "wisuda",
    "burnout",
    "stres akademik",
    "manajemen waktu",
    "motivasi belajar"
]
def is_academic_topic(text):
    """
    Mengecek apakah pesan berkaitan dengan topik akademik
    menggunakan pencocokan kata kunci (Rule-Based Validation).
    """

    text = text.lower()

    for keyword in ACADEMIC_KEYWORDS:
        if keyword in text:
            return True

    return False

# =========================
# VALIDASI INPUT
# =========================
def validate_input(text):
    """
    Melakukan validasi input pengguna sebelum diproses oleh GPT.
    """

    text = text.strip()

    # Validasi pesan kosong
    if not text:
        return False, "Pesan tidak boleh kosong."

    # Validasi panjang minimal
    if len(text) < 5:
        return False, "Pesan terlalu pendek. Silakan jelaskan permasalahan Anda."

    # Validasi domain akademik
    if not is_academic_topic(text):
        return False, (
            "Maaf, aplikasi ini hanya melayani permasalahan akademik mahasiswa. "
            "Silakan sampaikan pertanyaan atau curahan hati yang berkaitan dengan kegiatan akademik."
        )

    return True, ""

# =========================
# VALIDASI OUTPUT
# =========================
def validate_output(text):

    # 1. Respons kosong
    if not text or not text.strip():
        return (
            "Maaf, saya tidak dapat memberikan respons saat ini. "
            "Silakan coba beberapa saat lagi."
        )

    text_lower = text.lower()

    # 2. Kata yang tidak diperbolehkan
    blocked_keywords = [
        "investasi",
        "saham",
        "crypto",
        "bitcoin",
        "judi",
        "slot",
        "casino",
        "pinjaman online",
        "pinjol",
        "diagnosis medis"
    ]

    for keyword in blocked_keywords:
        if keyword in text_lower:
            return (
                "Maaf, saya hanya dapat membantu permasalahan akademik mahasiswa."
            )

    # 3. Respons terlalu pendek
    if len(text.strip()) < 20:
        return (
            "Maaf, saya tidak dapat menghasilkan respons yang memadai. "
            "Silakan jelaskan kembali permasalahan akademik Anda."
        )

    return text

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
    
    try:
        data = request.get_json()

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

        print(response)
        print(response.data)

        if not response.data:
            return jsonify({
                "message": "Insert berhasil tetapi data kosong"
            }), 500

        return jsonify({
            "message": "Session berhasil dibuat",
            "session": response.data[0]
        })

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500
    
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
        # INPUT RULE-BASED VALIDATION
        # Hanya dilakukan pada pesan pertama
        # =========================
        if len(history_data) == 0:

            is_valid, message = validate_input(pesan)

            if not is_valid:
                return jsonify({
                    "respon_gpt": message
                }), 200
        # =========================
        # CEK DATABASE LOKAL
        # =========================
        local_data = search_academic_data(pesan)

        if local_data:

            # =========================
            # UNIVERSITAS LAIN
            # =========================
            if local_data["type"] == "blocked":

                return jsonify({
                    "respon_gpt": local_data["message"],
                    "source": "validation"
                })

            # =========================
            # UAS / UTS UMUM
            # =========================
            if local_data["type"] == "general":

                return jsonify({
                    "respon_gpt": local_data["message"],
                    "source": "local"
                })

            # =========================
            # DATA DARI DATABASE
            # =========================
            if local_data["type"] == "database":

                jawaban = "📚 **Informasi Akademik Fakultas Teknik UNIS**\n\n"

                for item in local_data["data"]:

                    jawaban += f"**{item['kegiatan']}**\n"
                    jawaban += f"📅 {item['tanggal']}\n\n"

                jawaban += (
                    "_Sumber: Kalender Akademik UNIS "
                    "Tahun Akademik 2026/2027_"
                )

                return jsonify({
                    "respon_gpt": jawaban,
                    "source": "database"
                })

        # =========================
        # CEK LIMIT CHAT HARIAN
        # =========================
        chat_count = get_today_chat_count(user_id)

        if chat_count >= DAILY_CHAT_LIMIT:
            return jsonify({
                "message": "Batas chat AI harian telah tercapai.",
                "limit": DAILY_CHAT_LIMIT,
                "used": chat_count
            }), 429

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

            try:
                pesan_lama = decrypt_text(item["pesan_user"])
            except Exception:
                # Untuk data lama yang belum terenkripsi
                pesan_lama = item["pesan_user"]

            messages.append({
                "role": "user",
                "content": pesan_lama
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
        try:

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.6,
                max_tokens=700,
                presence_penalty=0.3,
                frequency_penalty=0.2,
            )

        except Exception as e:

            print("=== OPENAI ERROR ===")
            print(str(e))
            print("====================")

            return jsonify({
                "maintenance": True,
                "message": (
                    "Sistem AI sedang mengalami gangguan sementara. "
                    "Silakan coba kembali beberapa saat lagi."
                )
            }), 503

        hasil = response.choices[0].message.content
        hasil = validate_output(hasil)
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

    pesan_user_encrypted = encrypt_text(pesan_user)

    response = supabase.table("chats").insert({
        "user_id": user_id,
        "session_id": session_id,
        "pesan_user": pesan_user_encrypted,
        "respon_gpt": respon_gpt
    }).execute()
    print("=== DEBUG SAVE CHAT ===")
    print("USER ID:", user_id)
    print("SESSION ID:", session_id)
    print("PESAN ENCRYPTED:", pesan_user_encrypted)
    print("SUPABASE DATA:", response.data)
    print("=======================")
    # =========================
    # UPDATE JUDUL CHAT
    # =========================
    session = (
        supabase.table("chat_sessions")
        .select("title")
        .eq("id", session_id)
        .single()
        .execute()
    )

    if session.data and session.data["title"] == "Chat Baru":

        judul = pesan_user[:40]

        if len(pesan_user) > 40:
            judul += "..."

        supabase.table("chat_sessions") \
            .update({
                "title": judul
            }) \
            .eq("id", session_id) \
            .execute()
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

    data = response.data

    for item in data:
        item["pesan_user"] = decrypt_text(item["pesan_user"])

    return jsonify(data)

@app.route('/test-academic', methods=['GET'])
def test_academic():

    try:
        response = (
            supabase.table("academic_data")
            .select("*")
            .eq("tahun_akademik", "2026/2027")
            .execute()
        )

        data = response.data or []

        return jsonify({
            "success": True,
            "jumlah_data": len(data),
            "data": data[:5]
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# =========================
# RUN APP
# =========================
if __name__ == "__main__":
    app.run(debug=True)