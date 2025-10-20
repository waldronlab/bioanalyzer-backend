#!/usr/bin/env python3
"""
Performance Monitor for BioAnalyzer
===================================

This script monitors the performance of PMID queries and helps identify bottlenecks.
"""

import requests
import time
import json
from datetime import datetime
import argparse

def test_pmid_query(pmid, base_url="http://localhost:8000"):
    """Test a single PMID query and measure performance."""
    print(f"Testing PMID: {pmid}")
    
    start_time = time.time()
    
    try:
        # Test health endpoint first
        health_response = requests.get(f"{base_url}/health", timeout=10)
        health_time = time.time() - start_time
        
        if health_response.status_code != 200:
            print(f"❌ Health check failed: {health_response.status_code}")
            return False
            
        print(f"✅ Health check: {health_time:.2f}s")
        
        # Test enhanced analysis endpoint
        analysis_start = time.time()
        response = requests.get(f"{base_url}/enhanced_analysis/{pmid}", timeout=150)  # Increased timeout to 150 seconds
        analysis_time = time.time() - analysis_start
        
        total_time = time.time() - start_time
        
        if response.status_code == 200:
            print(f"✅ Analysis successful: {analysis_time:.2f}s")
            print(f"✅ Total time: {total_time:.2f}s")
            
            # Check if result was cached
            data = response.json()
            if data.get("cached", False):
                print("📋 Result served from cache")
            else:
                print("🔄 Result generated fresh")
                
            return True
        else:
            print(f"❌ Analysis failed: {response.status_code}")
            try:
                error_data = response.json()
                print(f"Error: {error_data.get('detail', 'Unknown error')}")
            except:
                print(f"Error: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ Request timed out")
        return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def test_multiple_pmids(pmids, base_url="http://localhost:8000"):
    """Test multiple PMIDs and provide performance summary."""
    print(f"Testing {len(pmids)} PMIDs...")
    print("=" * 50)
    
    results = []
    total_time = 0
    
    for i, pmid in enumerate(pmids, 1):
        print(f"\n[{i}/{len(pmids)}] ", end="")
        start_time = time.time()
        
        success = test_pmid_query(pmid, base_url)
        query_time = time.time() - start_time
        
        results.append({
            "pmid": pmid,
            "success": success,
            "time": query_time
        })
        
        total_time += query_time
        
        # Add delay between requests to avoid overwhelming the server
        if i < len(pmids):
            time.sleep(1)
    
    # Print summary
    print("\n" + "=" * 50)
    print("PERFORMANCE SUMMARY")
    print("=" * 50)
    
    successful = sum(1 for r in results if r["success"])
    failed = len(results) - successful
    
    print(f"Total PMIDs tested: {len(pmids)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Success rate: {(successful/len(pmids)*100):.1f}%")
    print(f"Total time: {total_time:.2f}s")
    print(f"Average time per PMID: {(total_time/len(pmids)):.2f}s")
    
    if successful > 0:
        successful_times = [r["time"] for r in results if r["success"]]
        print(f"Fastest query: {min(successful_times):.2f}s")
        print(f"Slowest query: {max(successful_times):.2f}s")
    
    # Check cache performance
    try:
        metrics_response = requests.get(f"{base_url}/metrics", timeout=10)
        if metrics_response.status_code == 200:
            metrics = metrics_response.json()
            cache_stats = metrics.get("cache", {})
            print(f"\nCache Statistics:")
            print(f"  Total analyzed: {cache_stats.get('total_curation_analyzed', 'N/A')}")
            print(f"  Cache hit rate: {cache_stats.get('curation_readiness_rate', 'N/A'):.1%}")
            print(f"  Recent activity (24h): {cache_stats.get('recent_analysis_24h', 'N/A')}")
    except:
        print("\nCould not retrieve cache statistics")

def main():
    parser = argparse.ArgumentParser(description="Performance Monitor for BioAnalyzer")
    parser.add_argument("--pmid", help="Single PMID to test")
    parser.add_argument("--pmids", nargs="+", help="Multiple PMIDs to test")
    parser.add_argument("--file", help="File containing PMIDs (one per line)")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL of the API")
    
    args = parser.parse_args()
    
    if args.pmid:
        test_pmid_query(args.pmid, args.url)
    elif args.pmids:
        test_multiple_pmids(args.pmids, args.url)
    elif args.file:
        try:
            with open(args.file, 'r') as f:
                pmids = [line.strip() for line in f if line.strip()]
            test_multiple_pmids(pmids, args.url)
        except FileNotFoundError:
            print(f"File not found: {args.file}")
        except Exception as e:
            print(f"Error reading file: {str(e)}")
    else:
        # Test with some sample PMIDs
        sample_pmids = ["12345", "67890", "11111"]
        print("No PMIDs specified. Testing with sample PMIDs...")
        test_multiple_pmids(sample_pmids, args.url)

if __name__ == "__main__":
    main()
