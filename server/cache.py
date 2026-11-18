"""
NetSim-RT Simulation Result Cache Engine (DuckDB)
CSL559 Computer Systems Design - IIT Bhilai
"""

import json
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any
import duckdb


class ResultCache:
    """Stores and retrieves simulation run results indexed by configuration hash."""
    def __init__(self, db_path: str = "results/cache.duckdb"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = duckdb.connect(str(self.db_path))
        self._init_schema()

    def _init_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sim_cache (
                config_hash VARCHAR PRIMARY KEY,
                trace_name VARCHAR,
                policy VARCHAR,
                num_servers INTEGER,
                load_multiplier DOUBLE,
                result_json VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def _compute_hash(self, config_dict: Dict[str, Any]) -> str:
        # Normalize dict to deterministic json string
        serialized = json.dumps(config_dict, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get(self, config_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        h = self._compute_hash(config_dict)
        cursor = self.conn.execute("SELECT result_json FROM sim_cache WHERE config_hash = ?", [h])
        row = cursor.fetchone()
        if row:
            return json.loads(row[0])
        return None

    def put(self, config_dict: Dict[str, Any], result_dict: Dict[str, Any]):
        h = self._compute_hash(config_dict)
        trace_name = str(config_dict.get("trace_path", ""))
        policy = str(config_dict.get("policy", ""))
        servers = int(config_dict.get("num_servers", 1))
        load = float(config_dict.get("load_multiplier", 1.0))
        res_str = json.dumps(result_dict)

        self.conn.execute("""
            INSERT OR REPLACE INTO sim_cache 
            (config_hash, trace_name, policy, num_servers, load_multiplier, result_json)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [h, trace_name, policy, servers, load, res_str])


# Singleton cache instance
_GLOBAL_CACHE: Optional[ResultCache] = None

def get_cache() -> ResultCache:
    global _GLOBAL_CACHE
    if _GLOBAL_CACHE is None:
        _GLOBAL_CACHE = ResultCache()
    return _GLOBAL_CACHE
