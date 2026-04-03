// ── Constraints (enforce uniqueness + auto-create index) ──────────────────
CREATE CONSTRAINT paper_id_unique  IF NOT EXISTS
  FOR (p:Paper)   REQUIRE p.paper_id  IS UNIQUE;

CREATE CONSTRAINT author_id_unique IF NOT EXISTS
  FOR (a:Author)  REQUIRE a.author_id IS UNIQUE;

CREATE CONSTRAINT method_id_unique IF NOT EXISTS
  FOR (m:Method)  REQUIRE m.method_id IS UNIQUE;

CREATE CONSTRAINT dataset_id_unique IF NOT EXISTS
  FOR (d:Dataset) REQUIRE d.dataset_id IS UNIQUE;

CREATE CONSTRAINT topic_id_unique  IF NOT EXISTS
  FOR (t:Topic)   REQUIRE t.topic_id  IS UNIQUE;

// ── Standard Indexes ──────────────────────────────────────────────────────
CREATE INDEX paper_arxiv_id  IF NOT EXISTS FOR (p:Paper)  ON (p.arxiv_id);
CREATE INDEX paper_year      IF NOT EXISTS FOR (p:Paper)  ON (p.year);
CREATE INDEX paper_tag       IF NOT EXISTS FOR (p:Paper)  ON (p.personality_tag);
CREATE INDEX author_name     IF NOT EXISTS FOR (a:Author) ON (a.name);
CREATE INDEX topic_label     IF NOT EXISTS FOR (t:Topic)  ON (t.label);

// ── Vector Index (Neo4j 5.x, dimensi 768 = Gemini text-embedding-004) ─────
CREATE VECTOR INDEX paper_embedding_index IF NOT EXISTS
  FOR (p:Paper) ON (p.embedding)
  OPTIONS {
    indexConfig: {
      `vector.dimensions`:  768,
      `vector.similarity_function`: 'cosine'
    }
  };