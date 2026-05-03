import math
from collections import defaultdict

from services.graph_service import driver


class CognitiveSearch:
    """Spreading Activation engine over Paper graph (CITES + SIMILAR_TO)."""

    def __init__(
        self,
        initial_energy: float = 1.0,
        decay_factor: float = 0.6,
        threshold: float = 0.05,
        max_depth: int = 5,
        semantic_weight: float = 0.4,
        citation_weight: float = 0.6,
        max_expansions: int = 3000,
    ):
        self.initial_energy = initial_energy
        self.decay_factor = decay_factor
        self.threshold = threshold
        self.max_depth = max_depth
        self.semantic_weight = semantic_weight
        self.citation_weight = citation_weight
        self.max_expansions = max_expansions

    def activate(self, seed_paper_id: str, max_results: int = 30) -> dict:
        resolved_seed = self._resolve_seed_paper_id(seed_paper_id)
        if not resolved_seed:
            return {"seed": seed_paper_id, "discoveries": [], "total_activated": 0}

        activation_map = defaultdict(float)
        visit_depth = {}
        activation_paths = defaultdict(list)
        queue = [(resolved_seed, self.initial_energy, 0, [resolved_seed])]

        activation_map[resolved_seed] = self.initial_energy
        visit_depth[resolved_seed] = 0

        while queue:
            if len(visit_depth) >= self.max_expansions:
                break
            current_id, energy, depth, path = queue.pop(0)
            if depth >= self.max_depth or energy < self.threshold:
                continue

            neighbors = self._get_weighted_neighbors(current_id)
            for neighbor in neighbors:
                neighbor_id = neighbor.get("paper_id")
                if not neighbor_id:
                    continue
                if neighbor_id in path:
                    continue

                edge_weight = (
                    self.citation_weight * neighbor.get("citation_strength", 0.5)
                    + self.semantic_weight * neighbor.get("semantic_similarity", 0.0)
                )
                propagated_energy = energy * self.decay_factor * edge_weight

                if propagated_energy < self.threshold:
                    continue

                activation_map[neighbor_id] += propagated_energy
                if neighbor_id not in visit_depth:
                    visit_depth[neighbor_id] = depth + 1

                new_path = path + [neighbor_id]
                activation_paths[neighbor_id].append(new_path)
                queue.append((neighbor_id, propagated_energy, depth + 1, new_path))

            queue.sort(key=lambda item: -item[1])

        discoveries = []
        for paper_id, activation in activation_map.items():
            if paper_id == resolved_seed:
                continue

            depth = visit_depth.get(paper_id, 0)
            serendipity = activation * math.log2(depth + 1)
            discoveries.append(
                {
                    "paper_id": paper_id,
                    "activation_energy": round(activation, 4),
                    "depth": depth,
                    "serendipity_score": round(serendipity, 4),
                    "activation_paths": activation_paths[paper_id][:3],
                }
            )

        discoveries.sort(key=lambda row: -row["serendipity_score"])
        discoveries = discoveries[:max_results]

        if discoveries:
            metadata_map = self._batch_fetch_metadata([d["paper_id"] for d in discoveries])
            for row in discoveries:
                meta = metadata_map.get(row["paper_id"], {})
                row["title"] = meta.get("title")
                row["year"] = meta.get("year")
                row["arxiv_id"] = meta.get("arxiv_id")
                row["personality_tag"] = meta.get("personality_tag")
                row["primary_category"] = meta.get("primary_category")
                row["authors_text"] = meta.get("authors_text", "")
        else:
            metadata_map = {}

        graph = self._build_activation_graph(
            resolved_seed=resolved_seed,
            discoveries=discoveries,
            activation_map=activation_map,
        )

        return {
            "seed": resolved_seed,
            "discoveries": discoveries,
            "total_activated": len(discoveries),
            "graph": graph,
            "params": {
                "decay": self.decay_factor,
                "threshold": self.threshold,
                "max_depth": self.max_depth,
            },
        }

    def _resolve_seed_paper_id(self, seed_input: str) -> str | None:
        query = """
            MATCH (p:Paper)
            WHERE p.paper_id = $pid
               OR p.arxiv_id = $pid
               OR p.paper_id = 'arxiv:' + $pid
            RETURN p.paper_id AS paper_id
            LIMIT 1
        """
        with driver.session() as session:
            record = session.run(query, pid=seed_input).single()
            return record["paper_id"] if record else None

    def _get_weighted_neighbors(self, paper_id: str) -> list[dict]:
        query = """
            MATCH (p:Paper {paper_id: $pid})
            OPTIONAL MATCH (p)-[c:CITES]-(cite_neighbor:Paper)
            WHERE cite_neighbor.unresolved = false
            WITH p, collect(DISTINCT {
                paper_id: cite_neighbor.paper_id,
                citation_strength: coalesce(c.match_confidence, 0.8),
                semantic_similarity: 0.0
            }) AS cite_neighbors

            OPTIONAL MATCH (p)-[s:SIMILAR_TO]-(sim_neighbor:Paper)
            WHERE sim_neighbor.unresolved = false
            WITH cite_neighbors, collect(DISTINCT {
                paper_id: sim_neighbor.paper_id,
                citation_strength: 0.0,
                semantic_similarity: coalesce(s.similarity_score, 0.5)
            }) AS sim_neighbors

            RETURN cite_neighbors + sim_neighbors AS neighbors
        """
        with driver.session() as session:
            record = session.run(query, pid=paper_id).single()
            if not record:
                return []

            merged: dict[str, dict] = {}
            for n in record["neighbors"]:
                n_id = n.get("paper_id")
                if not n_id:
                    continue

                if n_id not in merged:
                    merged[n_id] = dict(n)
                else:
                    merged[n_id]["citation_strength"] = max(
                        merged[n_id].get("citation_strength", 0.0),
                        n.get("citation_strength", 0.0),
                    )
                    merged[n_id]["semantic_similarity"] = max(
                        merged[n_id].get("semantic_similarity", 0.0),
                        n.get("semantic_similarity", 0.0),
                    )

            return list(merged.values())

    def _batch_fetch_metadata(self, paper_ids: list[str]) -> dict:
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
            rows = session.run(query, ids=paper_ids)
            return {row["paper_id"]: dict(row) for row in rows}

    def _build_activation_graph(
        self,
        resolved_seed: str,
        discoveries: list[dict],
        activation_map: dict,
    ) -> dict:
        all_ids = [resolved_seed] + [d["paper_id"] for d in discoveries]
        all_meta = self._batch_fetch_metadata(all_ids)
        seed_meta = all_meta.get(resolved_seed, {})

        max_energy = max(activation_map.values()) if activation_map else 1.0
        if max_energy <= 0:
            max_energy = 1.0

        nodes = [
            {
                "id": resolved_seed,
                "paper_id": resolved_seed,
                "label": (seed_meta.get("title", resolved_seed) or resolved_seed)[:50],
                "title": seed_meta.get("title", resolved_seed),
                "year": seed_meta.get("year"),
                "arxiv_id": seed_meta.get("arxiv_id"),
                "personality_tag": seed_meta.get("personality_tag"),
                "depth": 0,
                "activation_energy": 1.0,
                "serendipity_score": 0.0,
                "is_seed": True,
            }
        ]

        for d in discoveries:
            energy = float(d.get("activation_energy", 0.0))
            nodes.append(
                {
                    "id": d["paper_id"],
                    "paper_id": d["paper_id"],
                    "label": (d.get("title") or d["paper_id"])[:50],
                    "title": d.get("title"),
                    "year": d.get("year"),
                    "arxiv_id": d.get("arxiv_id"),
                    "personality_tag": d.get("personality_tag"),
                    "depth": d.get("depth", 0),
                    "activation_energy": max(0.0, min(1.0, energy / max_energy)),
                    "serendipity_score": d.get("serendipity_score", 0.0),
                    "is_seed": False,
                }
            )

        edges = []
        seen = set()
        for d in discoveries:
            for path in d.get("activation_paths", []):
                for i in range(len(path) - 1):
                    src = path[i]
                    tgt = path[i + 1]
                    key = f"{src}->{tgt}"
                    if key in seen:
                        continue
                    seen.add(key)
                    edges.append(
                        {
                            "from": src,
                            "to": tgt,
                            "rel_type": "activation_flow",
                            "arrows": "to",
                        }
                    )

        return {"nodes": nodes, "edges": edges, "root": resolved_seed}


cognitive_search = CognitiveSearch()
