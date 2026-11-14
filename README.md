# ScholarNexus-KG: Scientific Knowledge Graph & Literature Review Platform

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=FastAPI&logoColor=white)](https://fastapi.tiangolo.com/)
[![Neo4j](https://img.shields.io/badge/database-Neo4j-018bff.svg)](https://neo4j.com/)
[![Redis](https://img.shields.io/badge/redis-%23DD0031.svg?style=flat&logo=redis&logoColor=white)](https://redis.io/)
[![React](https://img.shields.io/badge/react-%2320232a.svg?style=flat&logo=react&logoColor=%2361DAFB)](https://reactjs.org/)
[![LLM](https://img.shields.io/badge/LLM-G   emini_2.5_Flash-orange.svg)](https://aistudio.google.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**ScholarNexus-KG** adalah platform penelusuran silsilah riset dan tinjauan pustaka ilmiah berbasis AI yang mengintegrasikan **Knowledge Graph (Neo4j)**, **Vector Embeddings**, dan **Large Language Models (LLM)**. Platform ini dirancang untuk memetakan evolusi ide, menganalisis kontribusi ilmiah, serta menghubungkan keterkaitan metodologi antar-naskah penelitian secara otomatis.

---

## Target Pengguna

Platform ini dirancang khusus untuk memenuhi kebutuhan komunitas akademik di berbagai jenjang:
* **Siswa SMA / SMK / MA:** Membantu penyusunan karya tulis ilmiah, proposal penelitian, dan riset kompetisi (Olimpiade/KIR).
* **Mahasiswa Sarjana (S1):** Mempercepat penyusunan bab tinjauan pustaka (Literature Review) pada tugas akhir dan skripsi.
* **Mahasiswa Magister (S2):** Memetakan State-of-the-Art (SOTA) dan mengidentifikasi celah riset (research gap) untuk tesis.
* **Kandidat Doktoral (S3):** Menelusuri lintasan historis evolusi paradigma dari artikel fondasi hingga perkembangan mutakhir untuk disertasi.

---

## Fitur Utama

### 1. Klasifikasi Peran Ilmiah (Paper Personality Tagging)
Setiap naskah dievaluasi perannya dalam ekosistem riset menggunakan model penalaran ilmiah (Gemini 2.5 Flash / DeepSeek R1):
* **PIONEER:** Memperkenalkan paradigma, arsitektur, atau metodologi baru yang fundamental.
* **OPTIMIZER:** Meningkatkan efisiensi, akurasi, kecepatan, atau ketahanan dari metode yang sudah ada.
* **BRIDGE:** Menghubungkan dua domain riset atau disiplin ilmu yang sebelumnya terpisah.

Setiap klasifikasi dilengkapi dengan tingkat keyakinan (*confidence score*), justifikasi penalaran AI, dan kutipan bukti langsung (*evidence quotes*) dari naskah.

### 2. Pencarian Universal & Visualisasi Silsilah 1-Langkah
* **Auto-Detection ArXiv ID:** Kolom pencarian tunggal yang secara otomatis mendeteksi format ArXiv ID (contoh: `1706.03762`) atau kata kunci topik penelitian.
* **Ingest & Visualize Seketika:** Memilih artikel pada hasil pencarian akan langsung memasukkan data ke graf pengetahuan (termasuk referensi sitasi di latar belakang) dan merender silsilah graf secara bersamaan tanpa proses manual bertahap.

### 3. Generator Sitasi Akademik Instan
Menyediakan format kutipan baku yang dapat disalin ke papan klip dalam satu klik:
* **APA (American Psychological Association) 7th Edition:** Standar naskah ilmiah umum dan sains sosial.
* **IEEE:** Format numerik standar teknik elektro, ilmu komputer, dan informatika.
* **BibTeX:** Format sumber referensi siap pakai untuk pengguna LaTeX dan Overleaf.

### 4. Ringkasan Eksekutif (TL;DR) & Panel Metadata
* **Core Problem:** Masalah utama yang berusaha diselesaikan oleh naskah.
* **Key Contribution:** Kontribusi orisinal yang diajukan oleh penulis.
* **Collapsible Abstract:** Tinjauan abstrak ringkas dengan fitur perluasan teks.
* **Metrik Silsilah Graf:** Menghitung jumlah sitasi internal di graf, referensi yang berhasil dipetakan, serta status peran silsilah (*Foundational Root*, *Derivative Work*, atau *Isolated Node*).

### 5. Smart Discovery (GraphRAG) & Cognitive Search
* **AI Smart Discovery:** Pencarian hibrida yang menggabungkan kemiripan vektor semantik (768 dimensi) dengan pembobotan jalur graf 2-hop dan jumlah sitasi.
* **Eksplorasi Asosiatif (Spreading Activation):** Simulasi keterkaitan ide berbasis model memori asosiatif kognitif untuk menemukan artikel terkait secara tak terduga (*serendipitous findings*) di luar kemiripan kata kunci langsung.

### 6. Visualisasi Graf Interaktif & Zoom Adaptif
* **Dynamic Zoom-Out Clamping:** Batas perkecilan tampilan (*minimum zoom-out scale*) disesuaikan secara dinamis mengikuti jumlah node pada layar. Hal ini mencegah graf menyusut menjadi titik kecil di kanvas kosong.
* **Floating Navigation Controls:** Tombol navigasi melayang (*Zoom In*, *Zoom Out*, dan *Fit / Pusatkan Graf*) untuk memudahkan navigasi kanvas.
* **Linimasa Tahun:** Filter interaktif untuk meninjau perkembangan silsilah riset dari tahun ke tahun.

### 7. Ekspor dan Berbagi
* **Ekspor Gambar PNG:** Menyimpan kanvas visualisasi graf resolusi tinggi.
* **Ekspor BibTeX:** Mengunduh seluruh daftar pustaka pada silsilah dalam satu file `.bib`.
* **Laporan Cetak PDF:** Menghasilkan ringkasan laporan riset siap cetak.
* **Tautan Berbagi:** Menghasilkan URL langsung untuk membuka kembali silsilah graf tertentu.

---

## Arsitektur Sistem

```text
                                  +-----------------------+
                                  |   React SPA Client    |
                                  | (Vis-Network / Vite)  |
                                  +-----------+-----------+
                                              | HTTP / REST
                                              v
+-----------------------------------------------------------------------------------+
|                            FastAPI Application Gateway                            |
|                                                                                   |
|  +--------------------+  +--------------------+  +-----------------------------+  |
|  | ArXiv / Search API |  |  Graph Lineage API |  | Cognitive & GraphRAG Router |  |
|  +---------+----------+  +---------+----------+  +--------------+--------------+  |
+------------|-----------------------|----------------------------|-----------------+
             |                       |                            |
             v                       v                            v
+--------------------+   +---------------------+   +-----------------------------+
| External Services  |   | Graph Engine (Neo4j)|   |  In-Memory Layer (Redis)    |
| - ArXiv REST API   |   | - Nodes: Paper,     |   | - Cache Query Hasil Search  |
| - Gemini 2.5 Flash |   |   Author, Topic     |   | - Cache Lineage Tree        |
| - Text Embeddings  |   | - Rel: CITES,       |   | - Rate Limit Tracking       |
|                    |   |   AUTHORED_BY, etc. |   |                             |
+--------------------+   +---------------------+   +-----------------------------+
```

---

## Struktur Direktori

```text
ScholarNexus-KG/
├── app/
│   ├── config/
│   │   └── settings.py          # Konfigurasi aplikasi berbasis Pydantic
│   ├── main.py                  # Inisialisasi FastAPI dan CORS middleware
│   └── routers/
│       ├── arxiv.py             # Router pencarian dan pengunduhan metadata ArXiv
│       ├── cognitive.py         # Router eksplorasi asosiatif (Spreading Activation)
│       ├── graph.py             # Router silsilah graf, analitik, dan detail node
│       ├── health.py            # Endpoint health check sistem
│       ├── papers.py            # Router unggah dan ekstraksi naskah PDF lokal
│       └── search.py            # Router hybrid search (GraphRAG)
├── db/
│   ├── connection.py            # Pool koneksi Neo4j dan Redis client
│   └── init_db.cypher           # Skema constraints dan index Neo4j
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── DetailPanel.jsx  # Panel metadata, TL;DR, dan generator sitasi
│   │   │   ├── GraphView.jsx    # Kanvas graf vis-network dengan zoom clamping
│   │   │   ├── Sidebar.jsx      # Panel pencarian universal dan unggah naskah
│   │   │   ├── TimelineSlider.jsx # Kontrol filter linimasa tahun
│   │   │   └── TopBar.jsx       # Header status sistem dan ringkasan metrik
│   │   ├── App.jsx              # Komponen utama dan orkestrasi state
│   │   └── styles/              # Tata letak dan tema visual aplikasi
│   ├── Dockerfile               # Konfigurasi container Frontend (Nginx)
│   └── package.json             # Dependensi React
├── pipeline/
│   ├── pdf_extractor.py         # Ekstraksi teks dan struktur naskah PDF
│   └── personality_tagger.py    # Integrasi penalaran LLM (Gemini 2.5 / DeepSeek)
├── services/
│   ├── arxiv_service.py         # Layanan client ArXiv API dan pemetaan referensi
│   ├── cognitive_service.py     # Algoritma spreading activation ACT-R
│   ├── graph_service.py         # Operasi kueri Cypher Neo4j
│   └── smart_search_service.py  # Layanan kalkulasi skor GraphRAG
├── docker-compose.yml           # Orkestrasi container Docker
├── .env.example                 # Template variabel lingkungan
├── requirements.txt             # Dependensi Python backend
└── README.md                    # Dokumentasi teknis platform
```

---

## Persyaratan Sistem & Instalasi

### Prasyarat
* **Docker Desktop** (versi 20.10 ke atas) atau Docker Engine dengan plugin Docker Compose.
* **RAM Minimum:** 4 GB (disarankan 8 GB untuk performa visualisasi graf yang optimal).
* **Koneksi Internet:** Diperlukan untuk mengakses ArXiv API dan Google AI Studio API.

### Langkah Instalasi

1. **Kloning Repositori:**
   ```bash
   git clone https://github.com/Npppss/ScholarNexus-KG.git
   cd ScholarNexus-KG
   ```

2. **Konfigurasi Variabel Lingkungan:**
   Salin file template `.env.example` menjadi `.env`:
   ```bash
   cp .env.example .env
   ```
   Buka file `.env` dan masukkan API Key Google Gemini Anda:
   ```env
   LLM_PROVIDER=gemini
   GEMINI_API_KEY=AIzaSy...your_gemini_api_key_here
   GEMINI_MODEL=gemini-2.5-flash
   ```

3. **Menjalankan Layanan:**
   Jalankan seluruh layanan menggunakan Docker Compose:
   ```bash
   docker compose up -d --build
   ```

4. **Verifikasi Status Kontainer:**
   Pastikan keempat kontainer berjalan dengan status sehat (*healthy*):
   * `kg_frontend` (Port 3000)
   * `kg_fastapi` (Port 8000)
   * `kg_neo4j` (Port 7474, 7687)
   * `kg_redis` (Port 6379)

---

## Akses Layanan

| Komponen | URL Akses | Keterangan |
| :--- | :--- | :--- |
| **Aplikasi Web** | [http://localhost:3000](http://localhost:3000) | Antarmuka visualisasi silsilah riset |
| **Dokumentasi API** | [http://localhost:8000/docs](http://localhost:8000/docs) | Swagger UI dokumentasi interaktif FastAPI |
| **Neo4j Browser** | [http://localhost:7474](http://localhost:7474) | Browser query graf (User: `neo4j`, Sandi di `.env`) |

---

## Dokumentasi Endpoint REST API

| Metode | Endpoint | Parameter Utama | Deskripsi |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/health` | - | Memeriksa status kesehatan koneksi Neo4j dan Redis |
| `POST` | `/api/arxiv/search` | `query`, `max_results` | Melakukan pencarian naskah di katalog global ArXiv |
| `POST` | `/api/arxiv/fetch` | `arxiv_ids`, `auto_fetch_references` | Mengunduh metadata paper dan memetakan referensi ke Neo4j |
| `POST` | `/api/search/smart` | `query`, `top_k`, `limit` | Pencarian rekomendasi semantik AI GraphRAG |
| `POST` | `/api/cognitive-search/{paper_id}` | `profile` (*fast/balanced/deep*) | Menjalankan algoritma spreading activation dari node tertentu |
| `GET` | `/api/graph/lineage/{paper_id}` | `direction`, `depth` | Mengambil data node dan edge silsilah graf untuk dirender |
| `GET` | `/api/graph/paper/{paper_id}/details` | - | Mengambil metadata komprehensif, abstrak, metrik, dan kutipan |
| `POST` | `/api/graph/paper/{paper_id}/analyze` | - | Memicu analisis Gemini Reasoning untuk klasifikasi peran paper |
| `GET` | `/api/graph/bibtex/{paper_id}` | - | Mengekspor kumpulan sitasi naskah dalam format file BibTeX |
| `POST` | `/api/papers/upload` | `file` (multipart/form-data) | Mengunggah file PDF lokal, mengekstrak teks, dan memetakan ke graf |

---

## Lisensi

Platform ini didistribusikan di bawah lisensi **MIT License**. Silakan merujuk ke file [LICENSE](LICENSE) untuk informasi hak cipta dan ketentuan penggunaan lebih lanjut.
