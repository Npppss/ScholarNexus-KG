# 🧠 ScholarNexus-KG: Research Lineage & Paper Personality Discovery

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Neo4j](https://img.shields.io/badge/database-Neo4j-018bff.svg)](https://neo4j.com/)
[![LLM](https://img.shields.io/badge/LLM-Gemini_1.5_Flash-orange.svg)](https://aistudio.google.com/)
[![License](https://img.shields.io/badge/license-Apache_2.0-green.svg)](LICENSE)

**ScholarNexus-KG** (sebelumnya dikenal sebagai *KG_personality*) adalah platform berbasis AI yang dirancang untuk memetakan ekosistem riset secara otomatis. Dengan menggabungkan **Knowledge Graphs (KG)** dan **Large Language Models (LLM)**, sistem ini tidak hanya mengekstraksi metadata, tetapi juga menganalisis "kepribadian" (karakteristik kontribusi) sebuah paper serta melacak silsilah penemuan ilmiah (*research lineage*).

---

## ✨ Fitur Utama

* **🎭 Paper Personality Tagging:** Klasifikasi otomatis peran paper dalam literatur:
    * 🚀 **The Pioneer:** Memperkenalkan paradigma atau arsitektur baru.
    * 🛠️ **The Optimizer:** Meningkatkan efisiensi/akurasi dari metode yang sudah ada.
    * 🌉 **The Bridge:** Menghubungkan metode dari satu domain ke domain lainnya.
* **🕸️ Automated Graph Construction:** Membangun graf hubungan antara Paper, Author, Method, dan Dataset secara *real-time* dari PDF user dan ArXiv API.
* **🔍 GraphRAG Search:** Melakukan pencarian semantik tingkat lanjut yang mempertimbangkan konteks hubungan antar-paper (bukan sekadar kemiripan teks).
* **📈 Lineage Discovery:** Menemukan jalur evolusi ide dari paper klasik hingga riset *state-of-the-art* terbaru.

---

## 🏗️ Arsitektur Sistem

Sistem ini menggunakan pendekatan **Hybrid RAG (Vector + Graph)**:
1.  **Ingestion Layer:** Ekstraksi PDF menggunakan `pypdf` dan pembersihan teks.
2.  **Reasoning Layer:** Gemini 1.5 Flash melakukan ekstraksi entitas (Entity Extraction) dan klasifikasi personality.
3.  **Graph Layer:** Penyimpanan data ke dalam Neo4j menggunakan skema ontologi yang saling terhubung.
4.  **Enrichment Layer:** Integrasi ArXiv API untuk memperluas graf berdasarkan referensi yang ditemukan.

---

## 📂 Struktur Folder

```text
ScholarNexus-KG/
├── data/               # Penyimpanan file PDF mentah & cache
├── src/
│   ├── extractor/      # Logika PDF Parsing & LLM Prompting
│   ├── database/       # Konektor Neo4j & Query Cypher
│   ├── api/            # Integrasi ArXiv API
│   └── utils/          # Fungsi pembantu (logging, config)
├── notebooks/          # Eksperimen ekstraksi & analisis graf
├── .env.example        # Template konfigurasi API Key
├── main.py             # Entry point aplikasi
└── requirements.txt    # Dependensi Python
