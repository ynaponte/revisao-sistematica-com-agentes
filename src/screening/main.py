"""CLI entry-point for the systematic review screening agent."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from langchain_core.runnables import RunnableConfig
from langchain_core.messages import HumanMessage

from .graph import build_graph, parse_regex_output
from .models import Article, ScreeningState, ScreeningContext
from .prompts import SCREENING_SYSTEM_PROMPT, build_human_prompt
from .spreadsheet import load_articles, write_results

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Logging Config
# ---------------------------------------------------------------------------

def setup_logging(log_file_path: str) -> None:
    """Configura o logger nativo do Python para console e arquivo."""
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "[{asctime}] {message}",
        style="{",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Handler para o console (Terminal)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    
    # Handler para o arquivo de log
    fh = logging.FileHandler(log_file_path, mode="a", encoding="utf-8")
    fh.setFormatter(formatter)
    
    logger.addHandler(sh)
    logger.addHandler(fh)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="screening",
        description="AI-powered screening agent for systematic review triage.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--input", "-i",
        required=True,
        help="Path to the .xls spreadsheet with articles.",
    )
    p.add_argument(
        "--sheet", "-s",
        default="Papers",
        help="Sheet name containing articles (default: Papers).",
    )
    p.add_argument(
        "--rows", "-r",
        default=None,
        help="Row range to process, 1-based inclusive (e.g. '1-100'). "
             "Default: all rows.",
    )
    p.add_argument(
        "--inclusion",
        nargs="+",
        required=True,
        help="Inclusion criteria (one string per criterion).",
    )
    p.add_argument(
        "--exclusion",
        nargs="+",
        required=True,
        help="Exclusion criteria (one string per criterion).",
    )
    p.add_argument(
        "--output", "-o",
        default=None,
        help="Output .xlsx path. Default: screening_results.xlsx in the "
             "same directory as the input file.",
    )
    p.add_argument(
        "--provider", "-p",
        default=None,
        choices=["gemini", "ollama", "vllm"],
        help="LLM provider override (default: from .env or 'gemini').",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=4.0,
        help="Delay in seconds between LLM calls to respect rate limits "
             "(default: 4.0).",
    )
    p.add_argument(
        "--concurrency", "-c",
        type=int,
        default=1,
        help="Number of articles to process concurrently (default: 1).",
    )
    p.add_argument(
        "--log",
        default="screening.log",
        help="Path to save the terminal log output (default: screening.log).",
    )
    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

async def _screen_article(
    idx: int,
    total: int,
    article: Article,
    graph,
    context: ScreeningContext,
    inclusion: list[str],
    exclusion: list[str],
    semaphore: asyncio.Semaphore,
    delay: float,
) -> dict:
    """Corrotina que processa um único artigo sob o controle do semaphore."""
    async with semaphore:
        _log_progress(idx, total, article)

        config = RunnableConfig(
            configurable={"thread_id": str(article.id)}
        )
        human_text = build_human_prompt(article, inclusion, exclusion)

        try:
            output = await graph.ainvoke(
                {"messages": HumanMessage(content=human_text)},
                config=config,
                context=context,
            )

            result = output

            if result["decision"] == "ACCEPTED":
                logger.info(f"   [{article.id}] → ✅ ACCEPTED")
            else:
                reasons = ", ".join(result["rejection_reasons"])
                logger.info(f"   [{article.id}] → ❌ REJECTED ({reasons})")

        except Exception as e:
            error_str = str(e).lower()

            if any(term in error_str for term in ["429", "quota", "exhausted", "limit", "too many requests"]):
                logger.error(f"🛑 CRITICAL: API Limit / Quota exceeded on article {article.id}! Error: {e}")
                # Propaga para cancelar as demais tasks via gather(return_exceptions=False)
                raise
            else:
                logger.error(f"   ⚠️  Generic error processing article {article.id}: {e}")
                result = {
                    "decision": "REJECTED",
                    "rejection_reasons": ["ERROR"],
                    "justification": f"Processing error: {e}",
                }

        if delay > 0:
            await asyncio.sleep(delay)

        return result


async def _main(argv: list[str] | None = None) -> None:
    load_dotenv()

    args = parse_args(argv)
    setup_logging(args.log)

    logger.info("Starting new screening session...")

    # -- Resolve output path --
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path(args.input).parent / "screening_results.xlsx"

    # -- Load articles --
    logger.info(f"📂 Loading articles from: {args.input}")
    logger.info(f"   Sheet: {args.sheet}")
    if args.rows:
        logger.info(f"   Row range: {args.rows}")

    articles = load_articles(args.input, args.sheet, args.rows)

    if not articles:
        logger.warning("⚠️  No articles found in the specified range. Exiting.")
        sys.exit(1)

    logger.info(f"   Found {len(articles)} articles to screen.\n")

    # -- Print criteria --
    logger.info("✅ Inclusion criteria:")
    for i, c in enumerate(args.inclusion, 1):
        logger.info(f"   I{i}: {c}")
    logger.info("❌ Exclusion criteria:")
    for i, c in enumerate(args.exclusion, 1):
        logger.info(f"   E{i}: {c}")
    logger.info("")

    # -- Build graph --
    provider_label = args.provider or "env/default"
    logger.info(f"🤖 Initializing Graph (provider: {provider_label})...")
    graph = build_graph()
    logger.info("   Graph compiled successfully.\n")

    context: ScreeningContext = {"provider": provider_label}

    total = len(articles)
    logger.info(f"{'='*60}")
    logger.info(f" Screening {total} articles (concurrency={args.concurrency})")
    logger.info(f"{'='*60}\n")

    semaphore = asyncio.Semaphore(args.concurrency)

    tasks = [
        _screen_article(
            idx=idx,
            total=total,
            article=article,
            graph=graph,
            context=context,
            inclusion=args.inclusion,
            exclusion=args.exclusion,
            semaphore=semaphore,
            delay=args.delay,
        )
        for idx, article in enumerate(articles, start=1)
    ]

    # return_exceptions=True para que um erro de quota não cancele tasks já concluídas
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Separar resultados válidos de exceções
    results: list[dict] = []
    processed_articles: list[Article] = []

    for article, outcome in zip(articles, raw_results):
        if isinstance(outcome, BaseException):
            error_str = str(outcome).lower()
            if any(term in error_str for term in ["429", "quota", "exhausted", "limit", "too many requests"]):
                logger.warning(f"   Skipping article {article.id} due to quota error.")
            else:
                logger.warning(f"   Skipping article {article.id} due to unexpected error: {outcome}")
            continue
        results.append(outcome)
        processed_articles.append(article)

    accepted = sum(1 for r in results if r["decision"] == "ACCEPTED")
    rejected = len(results) - accepted

    # -- Metadados --
    if provider_label == "gemini":
        model_used = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    elif provider_label == "ollama":
        model_used = os.getenv("OLLAMA_MODEL", "llama3.1")
    elif provider_label == "vllm":
        model_used = os.getenv("VLLM_MODEL", "meta-llama/Llama-3-8b-instruct")
    else:
        model_used = "unknown"

    metadata = {
        "Provider": provider_label,
        "Model": model_used,
        "Delay": f"{args.delay}s",
        "Concurrency": str(args.concurrency),
        "Range": args.rows if args.rows else "All",
        "Total Analyzed": str(len(processed_articles)),
    }

    # -- Write output --
    logger.info(f"\n{'='*60}")
    logger.info(f" Results Saved: {accepted} accepted, {rejected} rejected out of {len(processed_articles)} analyzed.")
    logger.info(f"{'='*60}\n")

    logger.info(f"💾 Writing partial/full results to: {output_path}")
    write_results(processed_articles, results, args.inclusion, args.exclusion, output_path, metadata=metadata)
    logger.info("   Done! ✨\n")


def main(argv: list[str] | None = None) -> None:
    asyncio.run(_main(argv))


def _log_progress(idx: int, total: int, article: Article) -> None:
    """Log a progress line for the current article."""
    pct = idx / total * 100
    title_display = article.title[:70]
    if len(article.title) > 70:
        title_display += "..."
    logger.info(f"[{idx}/{total}] ({pct:.0f}%) ID={article.id}: {title_display}")


if __name__ == "__main__":
    main()
