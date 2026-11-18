"""Search and test coverage analytics over the corpus store."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from qa_auto.index.store import init_db


def search_testcases(
    query: str,
    db_path: Path | str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search test cases using FTS5 BM25 match."""
    con = init_db(db_path)
    sanitized = query.replace('"', '""').strip()
    match_query = f'"{sanitized}"' if " " in sanitized else sanitized

    cur = con.cursor()
    cur.execute(
        """
        SELECT
            t.id,
            t.name,
            t.start_url,
            t.file_path,
            snippet(steps_fts, 4, '[b]', '[/b]', '...', 10) as match_snippet,
            bm25(steps_fts) as rank
        FROM steps_fts
        JOIN testcases t ON t.id = steps_fts.testcase_id
        WHERE steps_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (match_query, limit),
    )

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in cur.fetchall():
        tc_id = row[0]
        if tc_id in seen:
            continue
        seen.add(tc_id)
        results.append(
            {
                "id": tc_id,
                "name": row[1],
                "start_url": row[2],
                "file_path": row[3],
                "snippet": row[4],
                "score": round(abs(row[5]), 3),
            }
        )
    con.close()
    return results


def get_coverage_report(db_path: Path | str | None = None) -> dict[str, Any]:
    """Analyze corpus coverage across domains, start URLs, and network endpoints."""
    con = init_db(db_path)
    cur = con.cursor()

    cur.execute("SELECT id, name, start_url, file_path FROM testcases")
    testcases = cur.fetchall()

    start_urls: dict[str, int] = {}
    domains: dict[str, int] = {}
    for _, _, start_url, _ in testcases:
        start_urls[start_url] = start_urls.get(start_url, 0) + 1
        domain = urlparse(start_url).netloc
        if domain:
            domains[domain] = domains.get(domain, 0) + 1

    cur.execute("SELECT network_urls FROM steps_fts WHERE network_urls != ''")
    endpoints: dict[str, int] = {}
    for (net_urls,) in cur.fetchall():
        for url in net_urls.split():
            clean_url = url.split("?")[0]
            endpoints[clean_url] = endpoints.get(clean_url, 0) + 1

    potential_duplicates = [
        {"url": url, "count": count} for url, count in start_urls.items() if count > 1
    ]

    con.close()
    return {
        "total_testcases": len(testcases),
        "unique_domains": len(domains),
        "domains": domains,
        "start_urls": start_urls,
        "network_endpoints": endpoints,
        "potential_duplicates": potential_duplicates,
    }
