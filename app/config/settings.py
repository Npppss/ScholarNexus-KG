from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # ArXiv
    arxiv_rate_limit_rps:    float = 3.0        # requests per second
    arxiv_cache_ttl_days:    int   = 7
    arxiv_search_max_results: int  = 10
    arxiv_similarity_threshold: float = 0.55

    # Neo4j
    neo4j_uri:      str = "bolt://localhost:7687"
    neo4j_user:     str = "neo4j"
    neo4j_password: str = "password"

    # Gemini
    gemini_api_key: str = ""
    gemini_model:   str = "gemini-1.5-flash"
    embedding_model: str = "models/text-embedding-004"

    class Config:
        env_file = ".env"

settings = Settings()