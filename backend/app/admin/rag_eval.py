"""RAG evaluation service — aggregate metrics + LLM-as-judge."""

import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger(__name__)

_NO_ANSWER_PATTERNS = [
    re.compile(r"не\s+(удалось|смог|нашёл|нашла|могу)\s+(найти|обнаружить)", re.IGNORECASE),
    re.compile(r"нет\s+(информации|данных|сведений)", re.IGNORECASE),
    re.compile(r"в\s+(предоставленн|доступн)\w+\s+(документ|контекст|данн)", re.IGNORECASE),
    re.compile(r"i\s+(don.t|couldn.t|wasn.t able to)\s+find", re.IGNORECASE),
    re.compile(r"no\s+(information|data|relevant)\s+(found|available)", re.IGNORECASE),
    re.compile(r"not\s+found\s+in\s+the\s+(provided|available)", re.IGNORECASE),
]


def _is_no_answer(text_content: str) -> bool:
    if not text_content:
        return False
    snippet = text_content[:500]
    return any(p.search(snippet) for p in _NO_ANSWER_PATTERNS)


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(values):
        return values[f]
    return values[f] + (k - f) * (values[c] - values[f])


def collect_aggregate_metrics(session: Session) -> dict:
    """Phase 1: collect metrics from existing chat_message_analytics data."""
    result: dict = {}

    row = session.execute(text("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE chunks_found = 0) AS empty_count,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY top_similarity) AS sim_p50,
            percentile_cont(0.75) WITHIN GROUP (ORDER BY top_similarity) AS sim_p75,
            percentile_cont(0.90) WITHIN GROUP (ORDER BY top_similarity) AS sim_p90,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY search_ms) AS search_p50,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY search_ms) AS search_p95,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY total_ms) AS e2e_p50,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY total_ms) AS e2e_p95
        FROM chat_message_analytics
        WHERE created_at > NOW() - INTERVAL '30 days'
    """)).mappings().first()

    if row and row["total"] > 0:
        total = row["total"]
        result["empty_retrieval_rate"] = round(row["empty_count"] / total, 4)
        result["similarity_p50"] = round(row["sim_p50"], 4) if row["sim_p50"] else None
        result["similarity_p75"] = round(row["sim_p75"], 4) if row["sim_p75"] else None
        result["similarity_p90"] = round(row["sim_p90"], 4) if row["sim_p90"] else None
        result["search_latency_p50_ms"] = round(row["search_p50"], 1) if row["search_p50"] else None
        result["search_latency_p95_ms"] = round(row["search_p95"], 1) if row["search_p95"] else None
        result["e2e_latency_p50_ms"] = round(row["e2e_p50"], 1) if row["e2e_p50"] else None
        result["e2e_latency_p95_ms"] = round(row["e2e_p95"], 1) if row["e2e_p95"] else None

    fb_row = session.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE cm.feedback = 'up') AS up,
            COUNT(*) FILTER (WHERE cm.feedback = 'down') AS down
        FROM chat_messages cm
        WHERE cm.feedback IS NOT NULL
          AND cm.created_at > NOW() - INTERVAL '30 days'
    """)).mappings().first()

    if fb_row and (fb_row["up"] + fb_row["down"]) > 0:
        total_fb = fb_row["up"] + fb_row["down"]
        result["feedback_positive_rate"] = round(fb_row["up"] / total_fb, 4)

    answers = session.execute(text("""
        SELECT cm.content
        FROM chat_messages cm
        JOIN chat_message_analytics cma ON cma.message_id = cm.id
        WHERE cm.role = 'assistant'
          AND cm.created_at > NOW() - INTERVAL '30 days'
          AND cma.chunks_found > 0
    """)).all()

    if answers:
        no_answer_count = sum(1 for (content,) in answers if _is_no_answer(content))
        result["no_answer_rate"] = round(no_answer_count / len(answers), 4)

    return result


def collect_segmented_metrics(session: Session) -> tuple[dict, dict]:
    """Collect metrics grouped by query_type and product."""
    by_qt_rows = session.execute(text("""
        SELECT
            cma.query_type,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE cma.chunks_found = 0) AS empty_count,
            AVG(cma.top_similarity) AS avg_sim,
            AVG(cma.total_ms) AS avg_e2e,
            AVG(cma.search_ms) AS avg_search
        FROM chat_message_analytics cma
        WHERE cma.created_at > NOW() - INTERVAL '30 days'
          AND cma.query_type IS NOT NULL
        GROUP BY cma.query_type
        ORDER BY total DESC
    """)).mappings().all()

    metrics_by_qt: dict = {}
    for r in by_qt_rows:
        qt = r["query_type"]
        metrics_by_qt[qt] = {
            "total": r["total"],
            "empty_retrieval_rate": round(r["empty_count"] / r["total"], 4) if r["total"] else 0,
            "avg_similarity": round(r["avg_sim"], 4) if r["avg_sim"] else None,
            "avg_e2e_ms": round(r["avg_e2e"], 1) if r["avg_e2e"] else None,
            "avg_search_ms": round(r["avg_search"], 1) if r["avg_search"] else None,
        }

    by_prod_rows = session.execute(text("""
        SELECT
            cs.product_filter,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE cma.chunks_found = 0) AS empty_count,
            AVG(cma.top_similarity) AS avg_sim,
            AVG(cma.total_ms) AS avg_e2e
        FROM chat_message_analytics cma
        JOIN chat_sessions cs ON cs.id = cma.session_id
        WHERE cma.created_at > NOW() - INTERVAL '30 days'
          AND cs.product_filter IS NOT NULL
        GROUP BY cs.product_filter
        ORDER BY total DESC
        LIMIT 20
    """)).mappings().all()

    metrics_by_prod: dict = {}
    for r in by_prod_rows:
        pf = r["product_filter"]
        metrics_by_prod[pf] = {
            "total": r["total"],
            "empty_retrieval_rate": round(r["empty_count"] / r["total"], 4) if r["total"] else 0,
            "avg_similarity": round(r["avg_sim"], 4) if r["avg_sim"] else None,
            "avg_e2e_ms": round(r["avg_e2e"], 1) if r["avg_e2e"] else None,
        }

    return metrics_by_qt, metrics_by_prod


def collect_system_metrics(session: Session) -> dict:
    """Phase 2: pgvector benchmark + index health."""
    result: dict = {}

    vc = session.execute(text(
        "SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL"
    )).scalar()
    result["vector_count"] = vc or 0

    try:
        plan_rows = session.execute(text("""
            EXPLAIN (ANALYZE, FORMAT JSON)
            SELECT id
            FROM chunks
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> (SELECT embedding FROM chunks WHERE embedding IS NOT NULL LIMIT 1)
            LIMIT 10
        """)).scalar()
        if plan_rows and isinstance(plan_rows, list):
            exec_time = plan_rows[0].get("Execution Time")
            result["vector_search_ms"] = round(exec_time, 3) if exec_time else None
    except Exception as exc:
        logger.warning("pgvector benchmark failed", exc_info=exc)

    try:
        idx_size = session.execute(text(
            "SELECT pg_relation_size('idx_chunks_embedding') / (1024.0 * 1024.0)"
        )).scalar()
        result["hnsw_index_size_mb"] = round(idx_size, 1) if idx_size else None
    except Exception:
        pass

    return result


def sample_qa_pairs(session: Session, sample_size: int) -> list[dict]:
    """Sample recent Q&A pairs with their context for LLM-as-judge evaluation."""
    rows = session.execute(text("""
        SELECT
            cm_user.content AS question,
            cm_asst.content AS answer,
            cm_asst.sources AS sources,
            cma.top_similarity,
            cma.chunks_found,
            cma.query_type,
            cs.product_filter
        FROM chat_messages cm_asst
        JOIN chat_message_analytics cma ON cma.message_id = cm_asst.id
        JOIN chat_sessions cs ON cs.id = cma.session_id
        LEFT JOIN chat_messages cm_user ON cm_user.id = cma.user_message_id
        WHERE cm_asst.role = 'assistant'
          AND cm_asst.created_at > NOW() - INTERVAL '30 days'
          AND cma.chunks_found > 0
          AND cm_user.content IS NOT NULL
          AND LENGTH(cm_asst.content) > 50
        ORDER BY
            CASE WHEN cm_asst.feedback IS NOT NULL THEN 0 ELSE 1 END,
            RANDOM()
        LIMIT :limit
    """), {"limit": sample_size}).mappings().all()

    samples = []
    for r in rows:
        chunks_text = []
        if r["sources"] and isinstance(r["sources"], dict):
            for src in r["sources"].get("chunks", []):
                chunks_text.append(src.get("content", "")[:500])

        samples.append({
            "question": r["question"],
            "answer": r["answer"],
            "chunks": chunks_text,
            "top_similarity": r["top_similarity"],
            "chunks_found": r["chunks_found"],
            "query_type": r["query_type"],
            "product_filter": r["product_filter"],
        })

    return samples


def evaluate_faithfulness_batch(samples: list[dict]) -> list[float]:
    """Evaluate faithfulness for a batch of samples using Gemini Flash.

    Returns a score 0.0-1.0 for each sample.
    """
    import json
    import httpx

    scores = []
    for sample in samples:
        context = "\n---\n".join(sample["chunks"][:5])
        if not context.strip():
            scores.append(1.0)
            continue

        prompt = f"""You are evaluating the faithfulness of an AI assistant's answer.

Given the context (retrieved document chunks) and the answer, determine what fraction
of claims in the answer are supported by the context.

Context:
{context[:3000]}

Answer:
{sample['answer'][:2000]}

Respond with ONLY a JSON object: {{"score": <float 0.0-1.0>, "reason": "<brief explanation>"}}
A score of 1.0 means every claim is supported. A score of 0.0 means no claims are supported."""

        try:
            resp = httpx.post(
                f"{settings.openai_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.gemini_api_key}"},
                json={
                    "model": "gemini-2.5-flash",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                    "max_tokens": 200,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0]
            parsed = json.loads(content)
            score = max(0.0, min(1.0, float(parsed.get("score", 0.5))))
            scores.append(score)
        except Exception as exc:
            logger.warning("Faithfulness eval failed for sample", exc_info=exc)
            scores.append(0.5)

    return scores


def evaluate_context_precision_batch(samples: list[dict]) -> list[float]:
    """Evaluate context precision — fraction of retrieved chunks that are relevant.

    Returns a score 0.0-1.0 for each sample.
    """
    import json
    import httpx

    scores = []
    for sample in samples:
        if not sample["chunks"]:
            scores.append(0.0)
            continue

        chunks_list = "\n".join(
            f"[Chunk {i+1}]: {c[:300]}" for i, c in enumerate(sample["chunks"][:5])
        )

        prompt = f"""You are evaluating retrieval quality for a RAG system.

Question: {sample['question'][:500]}

Retrieved chunks:
{chunks_list}

For each chunk, determine if it is relevant to answering the question.
Respond with ONLY a JSON object: {{"relevant": [true/false, ...], "precision": <float 0.0-1.0>}}
where precision = count(relevant=true) / total chunks."""

        try:
            resp = httpx.post(
                f"{settings.openai_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.gemini_api_key}"},
                json={
                    "model": "gemini-2.5-flash",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                    "max_tokens": 200,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0]
            parsed = json.loads(content)
            score = max(0.0, min(1.0, float(parsed.get("precision", 0.5))))
            scores.append(score)
        except Exception as exc:
            logger.warning("Context precision eval failed for sample", exc_info=exc)
            scores.append(0.5)

    return scores


def run_full_evaluation(run_id: int) -> None:
    """Execute the full RAG evaluation pipeline.

    Called from a Celery task. Uses synchronous DB sessions.
    """
    from app.celery_app import _get_sync_engine
    from app.models import RagEvalRun

    engine = _get_sync_engine()

    def _update(run: RagEvalRun, session: Session, **kwargs):
        for k, v in kwargs.items():
            setattr(run, k, v)
        session.commit()

    try:
        with Session(engine) as session:
            run = session.get(RagEvalRun, run_id)
            if not run:
                logger.error("RagEvalRun not found", extra={"run_id": run_id})
                return

            _update(run, session, progress_percent=5, progress_stage="Collecting aggregate metrics...")

            agg = collect_aggregate_metrics(session)
            _update(run, session, progress_percent=15, progress_stage="Collecting segmented metrics...")

            metrics_by_qt, metrics_by_prod = collect_segmented_metrics(session)
            _update(run, session,
                    progress_percent=20,
                    progress_stage="Running pgvector benchmark...",
                    metrics_by_query_type=metrics_by_qt,
                    metrics_by_product=metrics_by_prod,
                    **{k: v for k, v in agg.items() if v is not None})

            sys_metrics = collect_system_metrics(session)
            _update(run, session,
                    progress_percent=30,
                    progress_stage="Sampling Q&A pairs...",
                    **{k: v for k, v in sys_metrics.items() if v is not None})

            samples = sample_qa_pairs(session, run.sample_size)

        if not samples:
            with Session(engine) as session:
                run = session.get(RagEvalRun, run_id)
                _update(run, session,
                        status="completed",
                        progress_percent=100,
                        progress_stage="done",
                        finished_at=datetime.now(timezone.utc),
                        details=[])
            return

        with Session(engine) as session:
            run = session.get(RagEvalRun, run_id)
            _update(run, session, progress_percent=35, progress_stage=f"Evaluating faithfulness 0/{len(samples)}...")

        faithfulness_scores = []
        batch_size = 5
        for i in range(0, len(samples), batch_size):
            batch = samples[i:i + batch_size]
            batch_scores = evaluate_faithfulness_batch(batch)
            faithfulness_scores.extend(batch_scores)

            pct = 35 + int((i + len(batch)) / len(samples) * 30)
            with Session(engine) as session:
                run = session.get(RagEvalRun, run_id)
                _update(run, session,
                        progress_percent=pct,
                        progress_stage=f"Evaluating faithfulness {i + len(batch)}/{len(samples)}...")

        with Session(engine) as session:
            run = session.get(RagEvalRun, run_id)
            _update(run, session, progress_percent=70, progress_stage=f"Evaluating context precision 0/{len(samples)}...")

        precision_scores = []
        for i in range(0, len(samples), batch_size):
            batch = samples[i:i + batch_size]
            batch_scores = evaluate_context_precision_batch(batch)
            precision_scores.extend(batch_scores)

            pct = 70 + int((i + len(batch)) / len(samples) * 25)
            with Session(engine) as session:
                run = session.get(RagEvalRun, run_id)
                _update(run, session,
                        progress_percent=pct,
                        progress_stage=f"Evaluating context precision {i + len(batch)}/{len(samples)}...")

        details = []
        mrr_values = []
        for idx, sample in enumerate(samples):
            f_score = faithfulness_scores[idx] if idx < len(faithfulness_scores) else None
            p_score = precision_scores[idx] if idx < len(precision_scores) else None

            if p_score and p_score > 0:
                mrr_values.append(1.0)
            else:
                mrr_values.append(0.0)

            details.append({
                "question": sample["question"][:300],
                "answer": sample["answer"][:500],
                "chunks_count": len(sample["chunks"]),
                "top_similarity": sample["top_similarity"],
                "query_type": sample["query_type"],
                "product_filter": sample["product_filter"],
                "faithfulness": round(f_score, 4) if f_score is not None else None,
                "context_precision": round(p_score, 4) if p_score is not None else None,
            })

        avg_faithfulness = sum(faithfulness_scores) / len(faithfulness_scores) if faithfulness_scores else None
        avg_precision = sum(precision_scores) / len(precision_scores) if precision_scores else None
        avg_mrr = sum(mrr_values) / len(mrr_values) if mrr_values else None

        with Session(engine) as session:
            run = session.get(RagEvalRun, run_id)
            run.status = "completed"
            run.progress_percent = 100
            run.progress_stage = "done"
            run.finished_at = datetime.now(timezone.utc)
            run.faithfulness = round(avg_faithfulness, 4) if avg_faithfulness is not None else None
            run.context_precision = round(avg_precision, 4) if avg_precision is not None else None
            run.mrr = round(avg_mrr, 4) if avg_mrr is not None else None
            run.details = details
            run.eval_model = "gemini-2.5-flash"
            session.commit()

        logger.info("RAG evaluation completed", extra={
            "run_id": run_id,
            "samples": len(samples),
            "faithfulness": avg_faithfulness,
            "context_precision": avg_precision,
        })

    except Exception as exc:
        logger.error("RAG evaluation failed", extra={"run_id": run_id}, exc_info=exc)
        try:
            with Session(engine) as session:
                run = session.get(RagEvalRun, run_id)
                if run:
                    run.status = "failed"
                    run.error_message = str(exc)[:2000]
                    run.finished_at = datetime.now(timezone.utc)
                    run.progress_stage = "failed"
                    session.commit()
        except Exception:
            pass
