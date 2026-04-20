"""CLI entry-point for the systematic review screening agent."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
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
        "--log",
        default="screening.log",
        help="Path to save the terminal log output (default: screening.log).",
    )
    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    # Load .env from the project root (or cwd)
    load_dotenv()

    args = parse_args(argv)

    # Initialize logging
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

    # A formatação agora ocorre isoladamente por artigo via função em prompts.py

    # -- Build graph --
    provider_label = args.provider or "env/default"
    logger.info(f"🤖 Initializing Graph (provider: {provider_label})...")
    graph = build_graph()
    logger.info("   Graph compiled successfully.\n")

    # -- Seção de configuração do grafo --
    
    context: ScreeningContext = {"provider": provider_label}

    # -- Process articles --
    results: list[dict] = []
    total = len(articles)
    accepted = 0
    rejected = 0

    logger.info(f"{'='*60}")
    logger.info(f" Screening {total} articles")
    logger.info(f"{'='*60}\n")

    # Helper para descobrir a posição no range fornecido.
    # Se '--rows 837-1110' -> start_row_offset será 837. 
    start_row_offset = 1
    if args.rows:
        try:
            start_row_offset = int(args.rows.split("-")[0])
        except Exception:
            pass

    for idx, article in enumerate(articles, start=1):
        _log_progress(idx, total, article)
        
        config = RunnableConfig(
            configurable={
                "thread_id": str(article.id)
            }
        )    
        human_text = build_human_prompt(
            article, args.inclusion, args.exclusion
        )

        try:
            output = graph.invoke(
                {"messages": HumanMessage(content=human_text)},
                config=config,
                context=context
            )
            
            # O output agora é um OutputState nativo.
            result = output
            
            results.append(result)

            if result["decision"] == "ACCEPTED":
                accepted += 1
                logger.info("   → ✅ ACCEPTED")
            else:
                reasons = ", ".join(result["rejection_reasons"])
                logger.info(f"   → ❌ REJECTED ({reasons})")
                rejected += 1

        except Exception as e:
            error_str = str(e).lower()
            
            # ------------------------------------------------------------
            # Proteção contra Abuso de Limite (Quotas/RateLimits)
            # ------------------------------------------------------------
            if any(term in error_str for term in ["429", "quota", "exhausted", "limit", "too many requests"]):
                logger.error(f"🛑 CRITICAL: API Limit / Quota exceeded during article {article.id}! Error: {e}")
                
                # Identificar aonde o robô parou com sucesso
                last_successful_idx = idx - 1
                last_successful_global_row = start_row_offset + last_successful_idx - 1
                
                logger.warning("")
                logger.warning("=====================================================")
                logger.warning(f"⚠️ EXECUTION HALTED TO PREVENT PROGRESS LOSS ⚠️")
                logger.warning(f"   Last fully processed successfully: ")
                logger.warning(f"   -> Relative index in loop: {last_successful_idx} of {total}")
                logger.warning(f"   -> Immediate previous row (parameter for --rows) was around: {last_successful_global_row}")
                
                if last_successful_idx > 0:
                    logger.warning(f"   On your next run, you should probably start at: --rows {last_successful_global_row + 1}-...")
                else:
                    logger.warning(f"   No articles were processed successfully in this batch.")
                logger.warning("=====================================================\n")

                break # Sai do loop para pular pros steps de salvamento
            else:
                logger.error(f"   ⚠️  Generic error processing article {article.id}: {e}")
                # Create a fallback REJECTED result to not lose track
                result = {
                    "decision": "REJECTED",
                    "rejection_reasons": ["ERROR"],
                    "justification": f"Processing error: {e}",
                }
                results.append(result)
                rejected += 1

        # Rate-limit delay (skip on last article)
        if idx < total and args.delay > 0:
            time.sleep(args.delay)

    # Precisamos fatiar (slice) os `articles` caso tenhamos feito o break protegendo contra limitação
    processed_articles = articles[:len(results)]
    
    # Montar os metadados de execução para a planilha
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


def _log_progress(idx: int, total: int, article: Article) -> None:
    """Log a progress line for the current article."""
    pct = idx / total * 100
    title_display = article.title[:70]
    if len(article.title) > 70:
        title_display += "..."
    logger.info(f"[{idx}/{total}] ({pct:.0f}%) ID={article.id}: {title_display}")


if __name__ == "__main__":
    main()
