import logging
import time
import json
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
from functools import wraps
import traceback
import asyncio

class PerformanceLogger:
    """Specialized logger for tracking PMID query performance and timing."""
    
    def __init__(self):
        self.logger = logging.getLogger('performance')
        self.logger.setLevel(logging.INFO)
        
        # Ensure the performance logger doesn't propagate to root logger
        self.logger.propagate = False
        
        # Create performance-specific handler
        from logging.handlers import RotatingFileHandler
        perf_handler = RotatingFileHandler(
            'logs/performance.log',
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        )
        perf_handler.setFormatter(formatter)
        self.logger.addHandler(perf_handler)
    
    def log_pmid_query_start(self, pmid: str, user_agent: str = None, ip_address: str = None):
        """Log the start of a PMID query."""
        self.logger.info(
            f"PMID_QUERY_START - PMID: {pmid} | "
            f"User-Agent: {user_agent or 'Unknown'} | "
            f"IP: {ip_address or 'Unknown'} | "
            f"Timestamp: {datetime.now().isoformat()}"
        )
    
    def log_pmid_query_end(self, pmid: str, duration: float, success: bool, 
                          cached: bool = False, error: str = None):
        """Log the completion of a PMID query."""
        status = "SUCCESS" if success else "FAILED"
        cache_status = "CACHED" if cached else "FRESH"
        
        self.logger.info(
            f"PMID_QUERY_END - PMID: {pmid} | "
            f"Status: {status} | "
            f"Duration: {duration:.2f}s | "
            f"Cache: {cache_status} | "
            f"Error: {error or 'None'} | "
            f"Timestamp: {datetime.now().isoformat()}"
        )
    
    def log_api_call(self, service: str, operation: str, pmid: str, 
                     duration: float, success: bool, error: str = None):
        """Log external API calls (PubMed, PMC, Gemini)."""
        status = "SUCCESS" if success else "FAILED"
        
        self.logger.info(
            f"API_CALL - Service: {service} | "
            f"Operation: {operation} | "
            f"PMID: {pmid} | "
            f"Duration: {duration:.2f}s | "
            f"Status: {status} | "
            f"Error: {error or 'None'} | "
            f"Timestamp: {datetime.now().isoformat()}"
        )
    
    def log_cache_operation(self, operation: str, pmid: str, 
                           cache_type: str, duration: float, success: bool):
        """Log cache operations."""
        status = "SUCCESS" if success else "FAILED"
        
        self.logger.info(
            f"CACHE_OP - Operation: {operation} | "
            f"PMID: {pmid} | "
            f"Type: {cache_type} | "
            f"Duration: {duration:.3f}s | "
            f"Status: {status} | "
            f"Timestamp: {datetime.now().isoformat()}"
        )
    
    def log_analysis_step(self, pmid: str, step: str, duration: float, 
                         details: Dict[str, Any] = None):
        """Log individual analysis steps."""
        details_str = f" | Details: {json.dumps(details)}" if details else ""
        
        self.logger.info(
            f"ANALYSIS_STEP - PMID: {pmid} | "
            f"Step: {step} | "
            f"Duration: {duration:.2f}s{details_str} | "
            f"Timestamp: {datetime.now().isoformat()}"
        )
    
    def log_performance_metrics(self, pmid: str, metrics: Dict[str, Any]):
        """Log detailed performance metrics for a PMID query."""
        self.logger.info(
            f"PERFORMANCE_METRICS - PMID: {pmid} | "
            f"Metrics: {json.dumps(metrics, default=str)} | "
            f"Timestamp: {datetime.now().isoformat()}"
        )
    
    def log_error(self, pmid: str, error: Exception, context: str = None):
        """Log errors with full context."""
        error_details = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
            "context": context
        }
        
        self.logger.error(
            f"ERROR - PMID: {pmid} | "
            f"Context: {context or 'Unknown'} | "
            f"Error: {json.dumps(error_details, default=str)} | "
            f"Timestamp: {datetime.now().isoformat()}"
        )

def log_performance(func):
    """Decorator to automatically log function performance."""
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        start_time = time.time()
        pmid = None
        
        # Try to extract PMID from arguments
        for arg in args:
            if isinstance(arg, str) and arg.isdigit():
                pmid = arg
                break
        
        if not pmid:
            for key, value in kwargs.items():
                if isinstance(value, str) and value.isdigit():
                    pmid = value
                    break
        
        try:
            result = await func(*args, **kwargs)
            duration = time.time() - start_time
            
            # Log successful execution
            perf_logger = PerformanceLogger()
            perf_logger.log_analysis_step(
                pmid or "Unknown",
                f"{func.__module__}.{func.__name__}",
                duration,
                {"success": True}
            )
            
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            
            # Log error
            perf_logger = PerformanceLogger()
            perf_logger.log_error(
                pmid or "Unknown",
                e,
                f"{func.__module__}.{func.__name__}"
            )
            
            raise
    
    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        start_time = time.time()
        pmid = None
        
        # Try to extract PMID from arguments
        for arg in args:
            if isinstance(arg, str) and arg.isdigit():
                pmid = arg
                break
        
        if not pmid:
            for key, value in kwargs.items():
                if isinstance(value, str) and value.isdigit():
                    pmid = value
                    break
        
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            
            # Log successful execution
            perf_logger = PerformanceLogger()
            perf_logger.log_analysis_step(
                pmid or "Unknown",
                f"{func.__module__}.{func.__name__}",
                duration,
                {"success": True}
            )
            
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            
            # Log error
            perf_logger = PerformanceLogger()
            perf_logger.log_error(
                pmid or "Unknown",
                e,
                f"{func.__module__}.{func.__name__}"
            )
            
            raise
    
    # Return appropriate wrapper based on function type
    # Use inspect.iscoroutinefunction for better compatibility
    import inspect
    if inspect.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper

# Global instance
perf_logger = PerformanceLogger()
