# services/cognitive_service.py
"""
Cognitive Search Engine — Spreading Activation Network
Inspired by Anderson's ACT-R cognitive architecture.

Simulates how the human brain activates related concepts:
energy spreads from a seed node through citation and semantic links,
decaying at each hop, to find "serendipitous" (surprising yet relevant) papers.
"""
import math
from collections import defaultdict
from services.graph_service import driver


class CognitiveSearch:

    def __init__(
        self,
        initial_energy: float = 1.0,
        decay_factor: float = 0.6,
        threshold: float = 0.05,
        max_depth: int = 5,
        semantic_weight: float = 0.4,
        citation_weight: float = 0.6,
    ):
        self.initial_energy = initial_energy
        self.decay_factor = decay_factor
        self.threshold = threshold
        self.max_depth = max_depth
        self.semantic_weight = semantic_weight
        self.citation_weight = citation_weight

    # ── Public API ────────────────────────────────────────────────────────

    def activate(self, seed_paper_id: str, max_results: int = 30) -> dict:
        """
        Spreading Activation from a single seed node.

        Returns a dict containing discovered papers ranked by
        'serendipity_score' — high activation at surprising distance.
        """
        # Resolve seed_paper_id (in case user inputs an arxiv_id without 'arxiv:' prefix)
        with driver.session() as session:
            r = session.run("MATCH (p:Paper) WHERE p.paper_id = $pid OR p.arxiv_id = $pid OR p.arxiv_id = replace($pid, 'arxiv:', '') RETURN p.paper_id AS resolved_id", pid=seed_paper_id).single()
            if not r:
                return {"discoveries": [], "graph": None, "message": "Seed paper not found"}
            seed_paper_id = r["resolved_id"]

        activation_map = defaultdict(float)
        visit_depth = {}
        activation_paths = defaultdict(list)

        # BFS queue: (paper_id, energy, depth, path)
        queue = [(seed_paper_id, self.initial_energy, 0, [seed_paper_id])]
        activation_map[seed_paper_id] = self.initial_energy
        visit_depth[seed_paper_id] = 0

        visited_edges = set()

        while queue:
            current_id, energy, depth, path = queue.pop(0)

            if depth >= self.max_depth or energy < self.threshold:
                continue

            neighbors = self._get_weighted_neighbors(current_id)

            for neighbor in neighbors:
                n_id = neighbor["paper_id"]
                if not n_id:
                    continue

                edge_key = f"{current_id}->{n_id}"
                if edge_key in visited_edges:
                    continue
                visited_edges.add(edge_key)

                # Compute propagated energy
                edge_weight = (
                    self.citation_weight * neighbor.get("citation_strength", 0.5)
                    + self.semantic_weight * neighbor.get("semantic_similarity", 0.0)
                )
                propagated_energy = energy * self.decay_factor * edge_weight

                if propagated_energy >= self.threshold:
                    activation_map[n_id] += propagated_energy

                    if n_id not in visit_depth:
                        visit_depth[n_id] = depth + 1

                    new_path = path + [n_id]
                    activation_paths[n_id].append(new_path)
                    queue.append((n_id, propagated_energy, depth + 1, new_path))

            # Priority-queue behaviour: process highest energy first
            queue.sort(key=lambda x: -x[1])

        # ── Build results ─────────────────────────────────────────────────
        results = []
        for paper_id, activation in activation_map.items():
            if paper_id == seed_paper_id:
                continue

            depth = visit_depth.get(paper_id, 0)
            # Serendipity = high activation × far distance (log scale)
            serendipity = activation * math.log2(depth + 1)

            results.append({
                "paper_id": paper_id,
                "activation_energy": round(activation, 4),
                "depth": depth,
                "serendipity_score": round(serendipity, 4),
                "best_path": activation_paths[paper_id][0] if activation_paths[paper_id] else [],
            })

        results.sort(key=lambda x: -x["serendipity_score"])
        results = results[:max_results]

        # Enrich with metadata
        if results:
            paper_ids = [r["paper_id"] for r in results]
            metadata = self._batch_fetch_metadata(paper_ids)
            for r in results:
                meta = metadata.get(r["paper_id"], {})
                r["title"] = meta.get("title", "Unknown")
                r["year"] = meta.get("year")
                r["arxiv_id"] = meta.get("arxiv_id")
                r["personality_tag"] = meta.get("personality_tag")
                r["primary_category"] = meta.get("primary_category")
                r["authors_text"] = meta.get("authors_text", "")

        # Build vis-network compatible graph data
        graph_data = self._build_activation_graph(
            seed_paper_id, results, activation_map, visit_depth
        )

        return {
            "seed": seed_paper_id,
            "discoveries": results,
            "total_activated": len(results),
            "graph": graph_data,
            "params": {
                "decay": self.decay_factor,
                "threshold": self.threshold,
                "max_depth": self.max_depth,
            },
        }

    # ── Private helpers ───────────────────────────────────────────────────

    def _get_weighted_neighbors(self, paper_id: str) -> list[dict]:
        """Fetch neighbors with edge weights from Neo4j."""
        query = """
            MATCH (p:Paper {paper_id: $pid})

            // Citation neighbors (bidirectional)
            OPTIONAL MATCH (p)-[c:CITES]-(neighbor:Paper)
            WHERE neighbor.unresolved = false

            WITH p, neighbor, c
            WHERE neighbor IS NOT NULL

            WITH p,
                 collect(DISTINCT {
                    paper_id: neighbor.paper_id,
                    citation_strength: coalesce(c.match_confidence, 0.8),
                    semantic_similarity: 0.0
                 }) AS cite_neighbors

            // Semantic neighbors
            OPTIONAL MATCH (p)-[s:SIMILAR_TO]-(sem_neighbor:Paper)
            WHERE sem_neighbor.unresolved = false AND sem_neighbor IS NOT NULL

            WITH cite_neighbors,
                 collect(DISTINCT {
                    paper_id: sem_neighbor.paper_id,
                    citation_strength: 0.0,
                    semantic_similarity: coalesce(s.similarity_score, 0.5)
                 }) AS sem_neighbors

            RETURN cite_neighbors + sem_neighbors AS neighbors
        """
        with driver.session() as session:
            result = session.run(query, pid=paper_id).single()
            if not result:
                return []

            # Deduplicate & merge weights from both relationship types
            merged = {}
            for n in result["neighbors"]:
                nid = n.get("paper_id")
                if not nid:
                    continue
                if nid not in merged:
                    merged[nid] = dict(n)
                else:
                    merged[nid]["semantic_similarity"] = max(
                        merged[nid]["semantic_similarity"],
                        n.get("semantic_similarity", 0.0),
                    )
                    merged[nid]["citation_strength"] = max(
                        merged[nid]["citation_strength"],
                        n.get("citation_strength", 0.0),
                    )
            return list(merged.values())

    def _batch_fetch_metadata(self, paper_ids: list[str]) -> dict:
        """Batch-fetch paper metadata for enrichment."""
        query = """
            UNWIND $ids AS pid
            MATCH (p:Paper {paper_id: pid})
            RETURN p.paper_id AS paper_id,
                   p.title AS title,
                   p.year AS year,
                   p.arxiv_id AS arxiv_id,
                   p.personality_tag AS personality_tag,
                   p.primary_category AS primary_category,
                   p.authors_text AS authors_text
        """
        with driver.session() as session:
            results = session.run(query, ids=paper_ids)
            return {r["paper_id"]: dict(r) for r in results}

    def _build_activation_graph(
        self, seed_id, results, activation_map, visit_depth
    ) -> dict:
        """Build vis-network compatible node/edge data with activation colors."""
        # Fetch seed node info
        seed_meta = self._batch_fetch_metadata([seed_id]).get(seed_id, {})

        max_energy = max(activation_map.values()) if activation_map else 1.0

        nodes = [
            {
                "id": seed_id,
                "paper_id": seed_id,
                "label": (seed_meta.get("title", seed_id) or seed_id)[:50],
                "title": seed_meta.get("title", seed_id),
                "year": seed_meta.get("year"),
                "depth": 0,
                "activation_energy": 1.0,
                "personality_tag": seed_meta.get("personality_tag"),
                "is_seed": True,
            }
        ]

        for r in results:
            nodes.append({
                "id": r["paper_id"],
                "paper_id": r["paper_id"],
                "label": (r.get("title", "?") or "?")[:50],
                "title": r.get("title"),
                "year": r.get("year"),
                "depth": r["depth"],
                "activation_energy": r["activation_energy"] / max_energy,
                "serendipity_score": r["serendipity_score"],
                "personality_tag": r.get("personality_tag"),
                "is_seed": False,
            })

        # Construct Spanning Tree of 'Aha!' Moments
        edges = []
        added_edges = set()
        
        for r in results:
            path = r["best_path"]
            if not path:
                continue
            for i in range(len(path) - 1):
                src = path[i]
                tgt = path[i+1]
                edge_key = f"{src}->{tgt}"
                if edge_key not in added_edges:
                    edges.append({
                        "from": src,
                        "to": tgt,
                        "rel_type": "activation_flow",
                        "arrows": "to",
                    })
                    added_edges.add(edge_key)

        return {"nodes": nodes, "edges": edges, "root": seed_id}

    def _get_edges_for_activated(self, paper_ids: list[str]) -> list[dict]:
        """Get edges between activated papers."""
        query = """
            MATCH (src:Paper)-[r:CITES]->(tgt:Paper)
            WHERE src.paper_id IN $ids AND tgt.paper_id IN $ids
            RETURN src.paper_id AS source, tgt.paper_id AS target, 'cites' AS rel_type
            UNION
            MATCH (src:Paper)-[r:SIMILAR_TO]->(tgt:Paper)
            WHERE src.paper_id IN $ids AND tgt.paper_id IN $ids
            RETURN src.paper_id AS source, tgt.paper_id AS target, 'similar_to' AS rel_type
        """
        with driver.session() as session:
            result = session.run(query, ids=paper_ids)
            return [
                {
                    "from": r["source"],
                    "to": r["target"],
                    "rel_type": r["rel_type"],
                    "arrows": "to",
                }
                for r in result
            ]


# Singleton
cognitive_search = CognitiveSearch()
