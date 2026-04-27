"""Screening API routes and background tasks."""

import asyncio
import json
import uuid
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
# Structure: { job_id: {"status": "running"|"completed"|"failed", "progress": 0, "total": 0, "output_path": str, "error": str} }
jobs: Dict[str, Dict[str, Any]] = {}

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


async def process_articles_task(
    job_id: str,
    file_path: Path,
    inclusion: list[str],
    exclusion: list[str],
    provider: str,
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
        
        semaphore = asyncio.Semaphore(2)
        
        async def process_single(article: Article):
            async with semaphore:
                config = RunnableConfig(configurable={"thread_id": str(article.id)})
                human_text = build_human_prompt(article, inclusion, exclusion)
                
                try:
                    output = await graph.ainvoke(
                        {"messages": HumanMessage(content=human_text)},
                        config=config,
                        context=context,
                    )
                    result = output
                except Exception as e:
                    result = {
                        "decision": "REJECTED",
                        "rejection_reasons": ["ERROR"],
                        "justification": f"Processing error: {e}",
                    }
                
                jobs[job_id]["progress"] += 1
                return result

        tasks = [process_single(article) for article in articles]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        cleaned_results = []
        results_summary = []
        for article, r in zip(articles, results):
            if isinstance(r, BaseException):
                res = {
                        "decision": "REJECTED",
                        "rejection_reasons": ["ERROR"],
                        "justification": f"System error: {r}",
                }
            else:
                res = r
            
            cleaned_results.append(res)
            results_summary.append({
                "id": article.id,
                "title": article.title,
                "decision": res.get("decision", "ERROR"),
                "reasons": ", ".join(res.get("rejection_reasons", []))
            })


        output_path = UPLOAD_DIR / f"results_{job_id}.xlsx"
        write_results(
            articles=articles, 
            results=cleaned_results, 
            inclusion_criteria=inclusion, 
            exclusion_criteria=exclusion, 
            output_path=output_path, 
            metadata={"Provider": provider, "Total Analyzed": str(len(articles))}
        )
        
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["output_path"] = str(output_path)
        jobs[job_id]["results_summary"] = results_summary

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)


@router.post("/screen")
async def start_screening(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    inclusion: str = Form(...),  
    exclusion: str = Form(...),  
    provider: str = Form("gemini")
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
        "results_summary": []
    }

    background_tasks.add_task(
        process_articles_task,
        job_id=job_id,
        file_path=file_path,
        inclusion=inc_list,
        exclusion=exc_list,
        provider=provider
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
    if job["status"] != "completed" or not job["output_path"]:
        raise HTTPException(status_code=400, detail="Job is not completed yet")
        
    file_path = Path(job["output_path"])
    if not file_path.exists():
        raise HTTPException(status_code=500, detail="Result file missing")
        
    return FileResponse(
        path=file_path,
        filename=f"screening_results.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
