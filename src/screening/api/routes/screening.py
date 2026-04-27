"""Screening API routes and background tasks."""

import asyncio
import json
import uuid
import logging
import os
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import HumanMessage

from ...graph import build_graph
from ...models import ScreeningContext, Article
from ...prompts import build_human_prompt
from ...spreadsheet import load_articles, write_results

router = APIRouter(prefix="/api")

# In-memory job tracker for the MVP
# Structure: { job_id: {"status": "running"|"completed"|"failed", "progress": 0, "total": 0, "output_path": str, "error": str, "cancelled": bool, "results_summary": list, "total_tokens": int} }
jobs: Dict[str, Dict[str, Any]] = {}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


async def process_articles_task(
    job_id: str,
    file_path: Path,
    inclusion: list[str],
    exclusion: list[str],
    provider: str,
    concurrency: int,
):
    """Background task that runs the AI screening graph."""
    try:
        articles = load_articles(file_path)
        if not articles:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = "No valid articles found in the uploaded file."
            return

        jobs[job_id]["total"] = len(articles)
        
        graph = build_graph()
        context: ScreeningContext = {"provider": provider}
        
        semaphore = asyncio.Semaphore(concurrency)
        
        async def process_single(article: Article):
            if jobs[job_id].get("cancelled"):
                res = {
                    "decision": "CANCELLED",
                    "rejection_reasons": ["Stopped by user"],
                    "justification": "Process stopped before this article."
                }
                jobs[job_id]["progress"] += 1
                jobs[job_id]["results_summary"].append({
                    "id": article.id,
                    "title": article.title,
                    "decision": res["decision"],
                    "reasons": res["rejection_reasons"][0]
                })
                return res
            
            async with semaphore:
                # Check again in case it was cancelled while waiting for semaphore
                if jobs[job_id].get("cancelled"):
                    res = {
                        "decision": "CANCELLED",
                        "rejection_reasons": ["Stopped by user"],
                        "justification": "Process stopped."
                    }
                    jobs[job_id]["progress"] += 1
                    jobs[job_id]["results_summary"].append({
                        "id": article.id,
                        "title": article.title,
                        "decision": res["decision"],
                        "reasons": res["rejection_reasons"][0]
                    })
                    return res

                config = RunnableConfig(configurable={"thread_id": str(article.id)})
                human_text = build_human_prompt(article, inclusion, exclusion)
                
                try:
                    output = await graph.ainvoke(
                        {"messages": HumanMessage(content=human_text)},
                        config=config,
                        context=context,
                    )
                    
                    tokens = 0
                    if "messages" in output and output["messages"]:
                        last_msg = output["messages"][-1]
                        if hasattr(last_msg, "usage_metadata") and last_msg.usage_metadata:
                            tokens = last_msg.usage_metadata.get("total_tokens", 0)

                    # Extrair APENAS os campos finais para liberar memoria (GC) das mensagens
                    result = {
                        "decision": output.get("decision", "ERROR"),
                        "rejection_reasons": output.get("rejection_reasons", []),
                        "justification": output.get("justification", ""),
                        "tokens": tokens
                    }
                except Exception as e:
                    logger.error(f"Erro ao processar artigo {article.id}: {str(e)}", exc_info=True)
                    result = {
                        "decision": "REJECTED",
                        "rejection_reasons": [f"API ERROR: {str(e)}"],
                        "justification": f"Processing error: {e}",
                        "tokens": 0
                    }
                
                jobs[job_id]["progress"] += 1
                jobs[job_id]["total_tokens"] += result.get("tokens", 0)
                
                # Update live summary
                jobs[job_id]["results_summary"].append({
                    "id": article.id,
                    "title": article.title,
                    "decision": result.get("decision", "ERROR"),
                    "reasons": ", ".join(result.get("rejection_reasons", [])),
                    "justification": result.get("justification", "")
                })
                
                # Atraso de segurança para não sobrecarregar LLMs locais (ex: Ollama)
                await asyncio.sleep(10)
                
                return result

        tasks = [process_single(article) for article in articles]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        cleaned_results = []
        for article, r in zip(articles, results):
            if isinstance(r, BaseException):
                res = {
                        "decision": "REJECTED",
                        "rejection_reasons": [f"SYSTEM ERROR: {str(r)}"],
                        "justification": f"System error: {r}",
                }
            else:
                res = r
            
            cleaned_results.append(res)

        output_path = UPLOAD_DIR / f"results_{job_id}.xlsx"
        write_results(
            articles=articles, 
            results=cleaned_results, 
            inclusion_criteria=inclusion, 
            exclusion_criteria=exclusion, 
            output_path=output_path, 
            metadata={"Provider": provider, "Total Analyzed": str(len(articles))}
        )
        
        jobs[job_id]["status"] = "completed" if not jobs[job_id].get("cancelled") else "cancelled"
        jobs[job_id]["output_path"] = str(output_path)

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)


@router.post("/screen")
async def start_screening(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    inclusion: str = Form(...),  
    exclusion: str = Form(...),  
    provider: str = Form("gemini"),
    concurrency: int = Form(2)
):
    """Endpoint to upload a file and start the screening process."""
    try:
        inc_list = json.loads(inclusion)
        exc_list = json.loads(exclusion)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format for criteria")

    job_id = str(uuid.uuid4())
    file_extension = Path(file.filename).suffix if file.filename else ".csv"
    file_path = UPLOAD_DIR / f"{job_id}{file_extension}"

    with open(file_path, "wb") as f:
        f.write(await file.read())

    jobs[job_id] = {
        "status": "running",
        "progress": 0,
        "total": 0,
        "output_path": None,
        "error": None,
        "cancelled": False,
        "results_summary": [],
        "total_tokens": 0
    }

    background_tasks.add_task(
        process_articles_task,
        job_id=job_id,
        file_path=file_path,
        inclusion=inc_list,
        exclusion=exc_list,
        provider=provider,
        concurrency=concurrency
    )

    return {"job_id": job_id, "message": "Screening started"}


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Check the status and progress of a screening job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return jobs[job_id]


@router.get("/jobs/{job_id}/download")
async def download_results(job_id: str):
    """Download the final Excel file for a completed job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
        
    job = jobs[job_id]
    if job["status"] not in ("completed", "cancelled") or not job["output_path"]:
        raise HTTPException(status_code=400, detail="Job is not finished yet")
        
    file_path = Path(job["output_path"])
    if not file_path.exists():
        raise HTTPException(status_code=500, detail="Result file missing")
        
    return FileResponse(
        path=file_path,
        filename=f"screening_results.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@router.post("/jobs/{job_id}/stop")
async def stop_job(job_id: str):
    """Signals a running job to stop and save progress."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if jobs[job_id]["status"] == "running":
        jobs[job_id]["cancelled"] = True
        return {"message": "Job stopping. Saving progress..."}
    
    return {"message": f"Job is already {jobs[job_id]['status']}"}

@router.get("/config")
async def get_config():
    """Return configured models from environment."""
    return {
        "models": {
            "gemini": os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            "ollama": os.getenv("OLLAMA_MODEL", "llama3.1"),
            "openai": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "anthropic": os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest"),
            "deepseek": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            "vllm": os.getenv("VLLM_MODEL", "meta-llama/Llama-3-8b-instruct")
        }
    }
