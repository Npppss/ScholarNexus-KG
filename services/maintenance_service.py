import logging
from services.graph_service import driver
from services.vector_service import generate_embedding

logger = logging.getLogger(__name__)


class MaintenanceService:
    @staticmethod
    def run_re_embedding_pipeline():
        """
        Finds resolved papers (unresolved = false) that lack embeddings,
        generates the embedding via Gemini, and updates the graph.
        """
        query_find = """
            MATCH (p:Paper)
            WHERE p.unresolved = false AND p.embedding IS NULL
            RETURN p.paper_id AS paper_id, p.title AS title, p.abstract AS abstract
            LIMIT 50
        """
        
        query_update = """
            MATCH (p:Paper {paper_id: $paper_id})
            SET p.embedding = $embedding
        """
        
        processed = 0
        with driver.session() as session:
            papers = session.run(query_find).data()
            if not papers:
                return 0

            for paper in papers:
                text_to_embed = f"{paper['title'] or ''} {paper['abstract'] or ''}".strip()
                if not text_to_embed:
                    continue

                emb = generate_embedding(text_to_embed)
                session.run(query_update, paper_id=paper["paper_id"], embedding=emb)
                processed += 1

        return processed

    @staticmethod
    def run_dead_reference_cleanup():
        """
        Deletes stub papers (unresolved = true) that have ZERO relationships.
        These are usually orphaned nodes.
        """
        query = """
            MATCH (p:Paper)
            WHERE p.unresolved = true AND NOT (p)--()
            DETACH DELETE p
        """
        with driver.session() as session:
            result = session.run(query)
            counters = result.consume().counters
            return getattr(counters, "nodes_deleted", 0)

    @staticmethod
    def run_deduplication_pipeline():
        """
        Finds duplicate papers based on:
        1) exact arxiv_id, or
        2) exact lowercase title
        Keeps one primary node, merges relationships/properties, and deletes duplicates.
        """
        query_by_arxiv = """
            MATCH (p:Paper)
            WHERE p.arxiv_id IS NOT NULL AND trim(p.arxiv_id) <> ""
            WITH p.arxiv_id AS arXiv, collect(p) AS nodes
            WHERE size(nodes) > 1
            WITH nodes[0] AS keeper, nodes[1..] AS duplicates
            UNWIND duplicates AS duplicate

            OPTIONAL MATCH (in)-[r_in:CITES]->(duplicate)
            CALL {
                WITH in, keeper, r_in
                MATCH (in) WHERE in IS NOT NULL
                MERGE (in)-[new_in:CITES]->(keeper)
                SET new_in = r_in
                RETURN count(*) AS in_rep
            }

            OPTIONAL MATCH (duplicate)-[r_out:CITES]->(out)
            CALL {
                WITH out, keeper, r_out
                MATCH (out) WHERE out IS NOT NULL
                MERGE (keeper)-[new_out:CITES]->(out)
                SET new_out = r_out
                RETURN count(*) AS out_rep
            }

            OPTIONAL MATCH (duplicate)-[s:SIMILAR_TO]-(sim)
            CALL {
                WITH sim, keeper, s
                MATCH (sim) WHERE sim IS NOT NULL
                MERGE (keeper)-[new_s:SIMILAR_TO]-(sim)
                SET new_s = s
                RETURN count(*) AS sim_rep
            }

            DETACH DELETE duplicate
            RETURN count(*) AS deleted_count
        """
        query_by_title = """
            MATCH (p:Paper)
            WHERE p.title IS NOT NULL AND trim(p.title) <> ""
            WITH toLower(trim(p.title)) AS normalized_title, collect(p) AS nodes
            WHERE size(nodes) > 1
            WITH nodes[0] AS keeper, nodes[1..] AS duplicates
            UNWIND duplicates AS duplicate

            OPTIONAL MATCH (in)-[r_in:CITES]->(duplicate)
            CALL {
                WITH in, keeper, r_in
                MATCH (in) WHERE in IS NOT NULL
                MERGE (in)-[new_in:CITES]->(keeper)
                SET new_in = r_in
                RETURN count(*) AS in_rep
            }

            OPTIONAL MATCH (duplicate)-[r_out:CITES]->(out)
            CALL {
                WITH out, keeper, r_out
                MATCH (out) WHERE out IS NOT NULL
                MERGE (keeper)-[new_out:CITES]->(out)
                SET new_out = r_out
                RETURN count(*) AS out_rep
            }

            OPTIONAL MATCH (duplicate)-[s:SIMILAR_TO]-(sim)
            CALL {
                WITH sim, keeper, s
                MATCH (sim) WHERE sim IS NOT NULL
                MERGE (keeper)-[new_s:SIMILAR_TO]-(sim)
                SET new_s = s
                RETURN count(*) AS sim_rep
            }

            DETACH DELETE duplicate
            RETURN count(*) AS deleted_count
        """
        with driver.session() as session:
            try:
                arxiv_result = session.run(query_by_arxiv)
                arxiv_deleted = sum(record["deleted_count"] for record in arxiv_result)

                # Run title-based dedup after arxiv merge pass.
                title_result = session.run(query_by_title)
                title_deleted = sum(record["deleted_count"] for record in title_result)
                return arxiv_deleted + title_deleted
            except Exception as e:
                logger.error(f"Deduplication pipeline failed: {e}")
                return 0

    @staticmethod
    def count_pending_embeddings():
        query = """
            MATCH (p:Paper)
            WHERE p.unresolved = false AND p.embedding IS NULL
            RETURN count(p) AS total
        """
        with driver.session() as session:
            record = session.run(query).single()
            return int(record["total"] or 0)

    @staticmethod
    def count_orphan_stubs():
        query = """
            MATCH (p:Paper)
            WHERE p.unresolved = true AND NOT (p)--()
            RETURN count(p) AS total
        """
        with driver.session() as session:
            record = session.run(query).single()
            return int(record["total"] or 0)

maintenance_service = MaintenanceService()
