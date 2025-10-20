#!/usr/bin/env python3
"""
Log Cleanup for BioAnalyzer
============================

This script helps manage log files by cleaning up old entries and rotating logs.
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
import shutil

class LogCleanup:
    """Log file cleanup and management."""
    
    def __init__(self, log_dir="logs"):
        self.log_dir = Path(log_dir)
        self.log_files = {
            "main": self.log_dir / "bioanalyzer.log",
            "performance": self.log_dir / "performance.log",
            "errors": self.log_dir / "errors.log",
            "api": self.log_dir / "api_calls.log"
        }
    
    def cleanup_old_logs(self, days=7):
        """Remove log files older than specified days."""
        cutoff_date = datetime.now() - timedelta(days=days)
        removed_count = 0
        
        print(f"🧹 Cleaning up logs older than {days} days...")
        
        for log_file in self.log_dir.glob("*.log.*"):
            try:
                # Check if it's a rotated log file
                if log_file.name.endswith(('.1', '.2', '.3', '.4', '.5')):
                    # Get file modification time
                    mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                    if mtime < cutoff_date:
                        log_file.unlink()
                        print(f"✅ Removed old log: {log_file.name}")
                        removed_count += 1
            except Exception as e:
                print(f"❌ Error removing {log_file.name}: {e}")
        
        print(f"✅ Cleanup complete. Removed {removed_count} old log files.")
    
    def rotate_logs(self):
        """Manually rotate log files."""
        print("🔄 Rotating log files...")
        
        for log_type, log_file in self.log_files.items():
            if not log_file.exists():
                continue
            
            try:
                # Create backup with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_name = f"{log_file.stem}_{timestamp}{log_file.suffix}"
                backup_path = self.log_dir / backup_name
                
                # Copy current log to backup
                shutil.copy2(log_file, backup_path)
                
                # Clear current log
                with open(log_file, 'w') as f:
                    f.write('')
                
                print(f"✅ Rotated {log_type}: {backup_name}")
                
            except Exception as e:
                print(f"❌ Error rotating {log_type}: {e}")
    
    def compress_logs(self):
        """Compress old log files to save space."""
        import gzip
        
        print("🗜️  Compressing old log files...")
        compressed_count = 0
        
        for log_file in self.log_dir.glob("*.log.*"):
            if log_file.name.endswith(('.1', '.2', '.3', '.4', '.5')):
                try:
                    # Skip already compressed files
                    if log_file.suffix == '.gz':
                        continue
                    
                    # Compress file
                    with open(log_file, 'rb') as f_in:
                        compressed_path = log_file.with_suffix(log_file.suffix + '.gz')
                        with gzip.open(compressed_path, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    
                    # Remove original file
                    log_file.unlink()
                    print(f"✅ Compressed: {log_file.name} -> {compressed_path.name}")
                    compressed_count += 1
                    
                except Exception as e:
                    print(f"❌ Error compressing {log_file.name}: {e}")
        
        print(f"✅ Compression complete. Compressed {compressed_count} files.")
    
    def show_log_info(self):
        """Show information about log files."""
        print("📊 LOG FILES INFORMATION")
        print("=" * 50)
        
        total_size = 0
        
        for log_type, log_file in self.log_files.items():
            if log_file.exists():
                size = log_file.stat().st_size
                size_mb = size / (1024 * 1024)
                total_size += size
                
                # Count lines
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        line_count = sum(1 for _ in f)
                except:
                    line_count = 0
                
                print(f"{log_type.upper():12} | {size_mb:6.2f} MB | {line_count:8d} lines")
            else:
                print(f"{log_type.upper():12} | Not found")
        
        # Check for rotated logs
        rotated_logs = list(self.log_dir.glob("*.log.*"))
        if rotated_logs:
            print(f"\n🔄 ROTATED LOGS ({len(rotated_logs)} files):")
            for log_file in sorted(rotated_logs):
                size = log_file.stat().st_size
                size_kb = size / 1024
                mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                age = datetime.now() - mtime
                
                if age.days > 0:
                    age_str = f"{age.days}d ago"
                else:
                    age_str = f"{age.seconds // 3600}h ago"
                
                print(f"  {log_file.name:30} | {size_kb:6.1f} KB | {age_str}")
        
        print(f"\n💾 Total log size: {total_size / (1024 * 1024):.2f} MB")
    
    def reset_logs(self, confirm=True):
        """Reset all log files (clear content)."""
        if confirm:
            response = input("Are you sure you want to reset ALL log files? (y/N): ")
            if response.lower() != 'y':
                print("Log reset cancelled.")
                return
        
        print("🔄 Resetting all log files...")
        
        for log_type, log_file in self.log_files.items():
            if log_file.exists():
                try:
                    with open(log_file, 'w') as f:
                        f.write('')
                    print(f"✅ Reset {log_type} log")
                except Exception as e:
                    print(f"❌ Error resetting {log_type}: {e}")
        
        print("✅ All log files have been reset.")

def main():
    parser = argparse.ArgumentParser(description="BioAnalyzer Log Cleanup")
    parser.add_argument("--cleanup", type=int, metavar="DAYS",
                       help="Clean up logs older than DAYS")
    parser.add_argument("--rotate", action="store_true",
                       help="Rotate log files")
    parser.add_argument("--compress", action="store_true",
                       help="Compress old log files")
    parser.add_argument("--info", action="store_true",
                       help="Show log file information")
    parser.add_argument("--reset", action="store_true",
                       help="Reset all log files")
    parser.add_argument("--logs", default="logs",
                       help="Log directory path (default: logs)")
    
    args = parser.parse_args()
    
    cleanup = LogCleanup(args.logs)
    
    if args.cleanup:
        cleanup.cleanup_old_logs(args.cleanup)
    elif args.rotate:
        cleanup.rotate_logs()
    elif args.compress:
        cleanup.compress_logs()
    elif args.info:
        cleanup.show_log_info()
    elif args.reset:
        cleanup.reset_logs()
    else:
        # Default: show info
        cleanup.show_log_info()

if __name__ == "__main__":
    main()
