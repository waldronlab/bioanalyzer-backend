#!/usr/bin/env python3
"""
Log Dashboard for BioAnalyzer
==============================

A simple dashboard to monitor logs in real-time with performance metrics.
"""

import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime, timedelta
import argparse
import re # Added missing import for regex

class LogDashboard:
    """Simple log monitoring dashboard."""
    
    def __init__(self, log_dir="logs"):
        self.log_dir = Path(log_dir)
        self.performance_log = self.log_dir / "performance.log"
        self.error_log = self.log_dir / "errors.log"
        self.main_log = self.log_dir / "bioanalyzer.log"
        
        # Statistics
        self.stats = {
            "total_queries": 0,
            "successful_queries": 0,
            "failed_queries": 0,
            "cached_queries": 0,
            "avg_response_time": 0,
            "errors": [],
            "recent_activity": []
        }
        
        # Track file positions
        self.file_positions = {}
        for log_file in [self.performance_log, self.error_log, self.main_log]:
            if log_file.exists():
                self.file_positions[log_file] = log_file.stat().st_size
            else:
                self.file_positions[log_file] = 0
    
    def update_stats(self):
        """Update statistics from log files."""
        self._update_performance_stats()
        self._update_error_stats()
        self._update_recent_activity()
    
    def _update_performance_stats(self):
        """Update performance statistics."""
        if not self.performance_log.exists():
            return
        
        try:
            with open(self.performance_log, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            # Reset counters
            self.stats["total_queries"] = 0
            self.stats["successful_queries"] = 0
            self.stats["failed_queries"] = 0
            self.stats["cached_queries"] = 0
            response_times = []
            
            for line in lines:
                if "PMID_QUERY_END" in line:
                    self.stats["total_queries"] += 1
                    
                    # Parse status
                    if "Status: SUCCESS" in line:
                        self.stats["successful_queries"] += 1
                    elif "Status: FAILED" in line:
                        self.stats["failed_queries"] += 1
                    
                    # Parse cache status
                    if "Cache: CACHED" in line:
                        self.stats["cached_queries"] += 1
                    
                    # Parse duration
                    duration_match = re.search(r'Duration: ([\d.]+)s', line)
                    if duration_match:
                        response_times.append(float(duration_match.group(1)))
            
            # Calculate average response time
            if response_times:
                self.stats["avg_response_time"] = sum(response_times) / len(response_times)
                
        except Exception as e:
            print(f"Error updating performance stats: {e}")
    
    def _update_error_stats(self):
        """Update error statistics."""
        if not self.error_log.exists():
            return
        
        try:
            with open(self.error_log, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Get last 10 errors
            recent_errors = []
            for line in lines[-10:]:
                if line.strip():
                    # Extract error summary
                    error_match = re.search(r'ERROR - PMID: (\d+) \| Context: (.+?) \|', line)
                    if error_match:
                        pmid = error_match.group(1)
                        context = error_match.group(2)
                        recent_errors.append(f"PMID {pmid}: {context}")
            
            self.stats["errors"] = recent_errors[-5:]  # Keep last 5 errors
            
        except Exception as e:
            print(f"Error updating error stats: {e}")
    
    def _update_recent_activity(self):
        """Update recent activity."""
        if not self.main_log.exists():
            return
        
        try:
            with open(self.main_log, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Get last 10 log entries
            recent_lines = lines[-10:]
            self.stats["recent_activity"] = []
            
            for line in recent_lines:
                if line.strip():
                    # Extract timestamp and message
                    timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                    if timestamp_match:
                        timestamp = timestamp_match.group(1)
                        # Extract meaningful part of the message
                        message = line.split(' - ', 2)[-1] if ' - ' in line else line.strip()
                        self.stats["recent_activity"].append(f"{timestamp}: {message}")
            
        except Exception as e:
            print(f"Error updating recent activity: {e}")
    
    def display_dashboard(self):
        """Display the dashboard."""
        os.system('clear' if os.name == 'posix' else 'cls')
        
        print("🚀 BioAnalyzer Log Dashboard")
        print("=" * 60)
        print(f"📅 Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # Performance Overview
        print("📊 PERFORMANCE OVERVIEW")
        print("-" * 30)
        print(f"Total PMID Queries: {self.stats['total_queries']}")
        print(f"Successful: {self.stats['successful_queries']} ✅")
        print(f"Failed: {self.stats['failed_queries']} ❌")
        print(f"Cached Results: {self.stats['cached_queries']} 📋")
        print(f"Avg Response Time: {self.stats['avg_response_time']:.2f}s")
        
        # Success rate
        if self.stats['total_queries'] > 0:
            success_rate = (self.stats['successful_queries'] / self.stats['total_queries']) * 100
            print(f"Success Rate: {success_rate:.1f}%")
        print()
        
        # Recent Errors
        if self.stats['errors']:
            print("❌ RECENT ERRORS")
            print("-" * 20)
            for error in self.stats['errors']:
                print(f"• {error}")
            print()
        
        # Recent Activity
        if self.stats['recent_activity']:
            print("📝 RECENT ACTIVITY")
            print("-" * 20)
            for activity in self.stats['recent_activity'][-5:]:  # Show last 5
                print(f"• {activity}")
            print()
        
        # File Status
        print("📁 LOG FILES STATUS")
        print("-" * 20)
        for log_name, log_file in [("Main", self.main_log), ("Performance", self.performance_log), ("Errors", self.error_log)]:
            if log_file.exists():
                size = log_file.stat().st_size
                size_kb = size / 1024
                print(f"{log_name}: {size_kb:.1f} KB")
            else:
                print(f"{log_name}: Not found")
        
        print()
        print("Press Ctrl+C to stop monitoring")
    
    def monitor(self, refresh_interval=5):
        """Monitor logs with periodic updates."""
        print("Starting log monitoring...")
        print("Press Ctrl+C to stop")
        
        try:
            while True:
                self.update_stats()
                self.display_dashboard()
                time.sleep(refresh_interval)
                
        except KeyboardInterrupt:
            print("\n👋 Monitoring stopped.")

def main():
    parser = argparse.ArgumentParser(description="BioAnalyzer Log Dashboard")
    parser.add_argument("--refresh", "-r", type=int, default=5,
                       help="Refresh interval in seconds (default: 5)")
    parser.add_argument("--logs", default="logs",
                       help="Log directory path (default: logs)")
    
    args = parser.parse_args()
    
    dashboard = LogDashboard(args.logs)
    dashboard.monitor(args.refresh)

if __name__ == "__main__":
    main()
