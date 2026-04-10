from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # ArXiv
    arxiv_rate_limit_rps:    float = 3.0        # requests per second
    arxiv_cache_ttl_days:    int   = 7
    arxiv_search_max_results: int  = 10
    arxiv_similarity_threshold: float = 0.55

    # Neo4j
    neo4j_uri:      str = "bolt://neo4j:7687"
    neo4j_user:     str = "neo4j"
    neo4j_password: str = "scholarNexus2024"

    # Gemini
    gemini_api_key: str = ""
    gemini_model:   str = "gemini-2.5-flash"
    embedding_model: str = "models/gemini-embedding-001"
    openai_api_key: str = "" 

    # Redis & App Config
    redis_url: str = "redis://redis:6379/0"
    redis_cache_ttl_days: int = 7   
    log_level: str = "INFO"          
    upload_max_size_mb: int = 50     

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()