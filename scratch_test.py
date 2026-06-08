import asyncio
import json
import os
import sys
from app.services.bugsigdb_analyzer import analyze_paper_with_rag, get_pubmed_retriever

async def test_extraction():
    pmid = "24273047"
    print(f"Testing extraction for PMID {pmid}...")
    
    # Check API keys
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    print(f"GEMINI_API_KEY set: {bool(gemini_key)}")
    
    retriever = get_pubmed_retriever()
    if not retriever:
        print("Error: PubMedRetriever not available")
        return
        
    print("Fetching paper texts...")
    texts = retriever.fetch_paper_metadata(pmid)
    if not texts:
        print(f"Failed to fetch paper for PMID {pmid}")
        return
        
    print("Running analyze_paper_with_rag...")
    # Run with RAG disabled first to see simple extraction
    res_no_rag = await analyze_paper_with_rag(pmid, use_rag=False)
    print("\n=== Result WITHOUT RAG ===")
    print(json.dumps(res_no_rag, indent=2))
    
    # Run with RAG enabled
    res_rag = await analyze_paper_with_rag(pmid, use_rag=True)
    print("\n=== Result WITH RAG ===")
    print(json.dumps(res_rag, indent=2))

if __name__ == "__main__":
    asyncio.run(test_extraction())
