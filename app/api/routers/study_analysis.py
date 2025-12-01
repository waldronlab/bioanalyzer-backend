"""
Study Analysis API Router

Handles URL-based study analysis requests.
"""
import asyncio
import logging
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, HttpUrl

from app.services.web_scraper import WebScraperService
from app.services.image_processor import ImageProcessorService
from app.services.converter_service import ConverterService
from app.services.vector_store_service import VectorStoreService
from app.services.agent_orchestrator import AgentOrchestrator
from app.utils.chunking import ChunkingService
from app.models.extraction_schemas import StudyAnalysisResult
from app.models.unified_qa import UnifiedQA
from app.utils.config import GEMINI_API_KEY

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["Study Analysis"])

# In-memory storage for job status (use Redis in production)
job_store = {}


class AnalyzeURLRequest(BaseModel):
    """Request to analyze a URL."""
    url: HttpUrl
    embedding_model: Optional[str] = "gemini/text-embedding-004"
    llm_model: Optional[str] = "gemini/gemini-2.0-flash"


class JobStatus(BaseModel):
    """Job status response."""
    job_id: str
    status: str  # pending, processing, completed, failed
    progress: Optional[str] = None
    result: Optional[StudyAnalysisResult] = None
    error: Optional[str] = None


@router.post("/analyze-url")
async def analyze_url(
    request: AnalyzeURLRequest,
    background_tasks: BackgroundTasks
) -> JobStatus:
    """
    Start analysis of a study URL.
    
    This endpoint initiates the complete workflow:
    1. Scrape URL to markdown
    2. Process images with visual LLM
    3. Convert and merge content
    4. Chunk and vectorize
    5. Extract experiments and signatures
    
    Returns a job ID for tracking progress.
    """
    job_id = str(uuid.uuid4())
    
    # Initialize job status
    job_store[job_id] = JobStatus(
        job_id=job_id,
        status="pending",
        progress="Job queued"
    )
    
    # Start background processing
    background_tasks.add_task(
        process_url_analysis,
        job_id=job_id,
        url=str(request.url),
        embedding_model=request.embedding_model,
        llm_model=request.llm_model
    )
    
    logger.info(f"Started analysis job {job_id} for URL: {request.url}")
    
    return job_store[job_id]


@router.get("/analysis-status/{job_id}")
async def get_analysis_status(job_id: str) -> JobStatus:
    """
    Get the status of an analysis job.
    
    Args:
        job_id: Job identifier
        
    Returns:
        Current job status
    """
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    return job_store[job_id]


@router.get("/analysis-result/{job_id}")
async def get_analysis_result(job_id: str) -> StudyAnalysisResult:
    """
    Get the result of a completed analysis job.
    
    Args:
        job_id: Job identifier
        
    Returns:
        Analysis result
    """
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    job = job_store[job_id]
    
    if job.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job {job_id} is not completed (status: {job.status})"
        )
    
    if not job.result:
        raise HTTPException(
            status_code=500,
            detail=f"Job {job_id} completed but no result available"
        )
    
    return job.result


async def process_url_analysis(
    job_id: str,
    url: str,
    embedding_model: str,
    llm_model: str
):
    """
    Background task to process URL analysis.
    
    This implements the complete 7-step workflow.
    """
    try:
        # Update status
        job_store[job_id].status = "processing"
        job_store[job_id].progress = "Step 1/7: Scraping URL"
        
        # Step 1 & 2: Scrape URL
        scraper = WebScraperService()
        scrape_result = await scraper.scrape_url_to_markdown(url)
        logger.info(f"Job {job_id}: Scraped {len(scrape_result['markdown'])} chars")
        
        # Step 3: Process images
        job_store[job_id].progress = "Step 3/7: Processing images"
        image_processor = ImageProcessorService()
        visual_llm = None
        if GEMINI_API_KEY:
            try:
                visual_llm = UnifiedQA(
                    use_gemini=True,
                    gemini_api_key=GEMINI_API_KEY
                )
            except Exception as e:
                logger.warning(f"Job {job_id}: Unable to initialize visual LLM: {e}")

        image_descriptions = []
        
        for i, img_url in enumerate(scrape_result['images'][:10]):  # Limit to 10 images
            parsed_media = await image_processor.process_image_url(img_url, index=i)
            if parsed_media:
                description = f"Image {i+1} from study"
                if visual_llm:
                    generated_description = await image_processor.describe_image_with_llm(
                        parsed_media=parsed_media,
                        llm_service=visual_llm
                    )
                    if generated_description:
                        description = generated_description
                else:
                    description = (
                        f"Image {i+1} - visual description unavailable "
                        f"(configure GEMINI_API_KEY for vision support)."
                    )
                image_descriptions.append({
                    "url": img_url,
                    "description": description
                })
        
        logger.info(f"Job {job_id}: Processed {len(image_descriptions)} images")
        
        # Step 4: Convert and merge
        job_store[job_id].progress = "Step 4/7: Creating enhanced markdown"
        converter = ConverterService()
        enhanced_md = await converter.create_enhanced_markdown(
            base_markdown=scrape_result['markdown'],
            image_descriptions=image_descriptions,
            downloaded_files=scrape_result['files'],
            source_url=url
        )
        
        logger.info(f"Job {job_id}: Created enhanced markdown ({len(enhanced_md)} chars)")
        
        # Step 5: Chunk and vectorize
        job_store[job_id].progress = "Step 5/7: Chunking and vectorizing"
        chunker = ChunkingService(chunk_chars=3000, overlap=100)
        chunks = await chunker.chunk_markdown(
            markdown=enhanced_md,
            doc_name=f"study_{job_id[:8]}",
            doc_key=job_id
        )
        
        vector_store = VectorStoreService(
            store_type="numpy",
            embedding_model=embedding_model
        )
        await vector_store.add_texts(chunks)
        
        logger.info(f"Job {job_id}: Vectorized {len(chunks)} chunks")
        
        # Step 6: Extract experiments and signatures
        job_store[job_id].progress = "Step 6/7: Extracting experiments and signatures"
        orchestrator = AgentOrchestrator(
            llm_model=llm_model,
            embedding_model=embedding_model
        )
        
        result = await orchestrator.analyze_study(
            chunks=chunks,
            study_id=job_id,
            source_url=url
        )
        
        logger.info(
            f"Job {job_id}: Extracted {len(result.experiments)} experiments, "
            f"{result.total_signatures} signatures"
        )
        
        # Step 7: Complete
        job_store[job_id].status = "completed"
        job_store[job_id].progress = "Analysis complete"
        job_store[job_id].result = result
        
        # Cleanup
        scraper.cleanup_downloads()
        image_processor.cleanup_cache()
        
        logger.info(f"Job {job_id}: Completed successfully")
        
    except Exception as e:
        logger.error(f"Job {job_id}: Failed with error: {e}")
        job_store[job_id].status = "failed"
        job_store[job_id].error = str(e)
