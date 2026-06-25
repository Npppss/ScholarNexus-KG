# 🧠 ScholarNexus-KG: Research Lineage & Paper Personality Discovery

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=FastAPI&logoColor=white)](https://fastapi.tiangolo.com/)
[![Neo4j](https://img.shields.io/badge/database-Neo4j-018bff.svg)](https://neo4j.com/)
[![Redis](https://img.shields.io/badge/redis-%23DD0031.svg?style=flat&logo=redis&logoColor=white)](https://redis.io/)
[![React](https://img.shields.io/badge/react-%2320232a.svg?style=flat&logo=react&logoColor=%2361DAFB)](https://reactjs.org/)
[![LLM](https://img.shields.io/badge/LLM-Gemini_2.5_Flash-orange.svg)](https://aistudio.google.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**ScholarNexus-KG** (sebelumnya dikenal sebagai *KG_personality*) adalah platform berbasis AI yang dirancang untuk memetakan ekosistem riset secara otomatis. Dengan menggabungkan **Knowledge Graphs (KG)**, **Vector Embeddings**, dan **Large Language Models (LLM)**, sistem ini mengekstraksi metadata, menganalisis "kepribadian" kontribusi paper, serta melacak silsilah penemuan ilmiah (*research lineage*).

---

## ✨ Fitur Utama

* **🎭 Paper Personality Tagging:** Klasifikasi otomatis peran paper dalam literatur:
  * 🚀 **The Pioneer:** Memperkenalkan paradigma atau arsitektur baru.
  * 🛠️ **The Optimizer:** Meningkatkan efisiensi/akurasi dari metode yang sudah ada.
  * 🌉 **The Bridge:** Menghubungkan metode dari satu domain ke domain lainnya.
* **🧠 Cognitive Search (Spreading Activation):** Pencarian *serendipitous* yang terinspirasi dari model kognitif (ACT-R) untuk menemukan paper relevan di luar batasan kemiripan teks langsung.
* **🔍 Smart GraphRAG:** *Hybrid search* yang menggabungkan *vector search* (768d embeddings), ekspansi graf 2-hop, dan re-ranking berdasarkan metrik sitasi & tahun.
* **🕸️ Automated Graph Construction:** Membangun graf hubungan entitas secara otomatis dari integrasi *multi-source* (PDF Upload, ArXiv API, dan Semantic Scholar).
* **📈 Lineage Discovery:** Visualisasi jalur evolusi ide dari paper klasik (fondasi) hingga riset turunan terbarunya.

---

## 🏗️ Arsitektur Pipeline

Sistem ini menggunakan pendekatan **Hybrid RAG (Vector + Graph)**:
1.  **Ingestion Layer:** Ekstraksi PDF menggunakan `pypdf` dan pembersihan teks.
2.  **Reasoning Layer:** Gemini 2.5 Flash melakukan ekstraksi entitas (Entity Extraction) dan klasifikasi personality.
3.  **Graph Layer:** Penyimpanan data ke dalam Neo4j menggunakan skema ontologi yang saling terhubung.
4.  **Enrichment Layer:** Integrasi ArXiv API untuk memperluas graf berdasarkan referensi yang ditemukan.

---

## 📂 Struktur Direktori

```text
ScholarNexus-KG/
├── app/                  # FastAPI routers & entry point utama (app/main.py)
├── services/             # Business logic (GraphRAG, cognitive/spreading_activation)
├── pipeline/             # Orkestrasi ekstraksi PDF dan pemrosesan LLM (Gemini)
├── frontend/             # Aplikasi React UI & visualisasi vis.js
├── db/                   # Skema Neo4j, Cypher migrations, index/constraints
├── .env.example          # Template environment variables (API Key, DB URI)
├── .gitignore            # Exclude .env, venv, cache, dll.
├── docker-compose.yml    # Orkestrasi multi-container (FastAPI, Neo4j, Redis, UI)
├── requirements.txt      # List dependencies Python
└── LICENSE               # MIT License