from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # ArXiv
    arxiv_rate_limit_rps:    float = 3.0        # requests per second
    arxiv_cache_ttl_days:    int   = 7
    arxiv_search_max_results: int  = 10
    arxiv_similarity_threshold: float = 0.55

    # Neo4j
    neo4j_uri:      str = "neo4j+s://d99ffd6c.databases.neo4j.io"
    neo4j_user:     str = "d99ffd6c"
    neo4j_password: str = "99fZz-u3p2mZYlTGX4V2FumstQj9fDgwAAAQ-QeVGwc"

    # Gemini
    gemini_api_key: str = ""
    gemini_model:   str = "gemini-1.5-flash"
    embedding_model: str = "models/text-embedding-004"
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