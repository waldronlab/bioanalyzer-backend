#!/usr/bin/env python3
"""
BioAnalyzer CLI - User-Friendly Command Line Interface
=====================================================

This CLI provides a simple, user-friendly interface for BioAnalyzer.
All commands are designed to be intuitive and easy to use.

Usage:
    BioAnalyzer help                    # Show help
    BioAnalyzer build                   # Build Docker containers
    BioAnalyzer start                   # Start the application
    BioAnalyzer analyze <pmid>          # Analyze a single paper
    BioAnalyzer analyze <pmid1,pmid2>   # Analyze multiple papers
    BioAnalyzer status                  # Check system status
    BioAnalyzer stop                    # Stop the application
"""

import asyncio
import json
import sys
import argparse
import os
import subprocess
import time
import csv
from pathlib import Path
from typing import List, Optional, Dict, Any
import logging

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BioAnalyzerCLI:
    """User-friendly Command Line Interface for BioAnalyzer."""
    
    def __init__(self):
        self.container_name = "bioanalyzer-api"
        self.image_name = "bioanalyzer-backend"
        self.verbose = False
    
    def print_banner(self):
        """Print the BioAnalyzer banner."""
        print("""
🧬 =============================================== 🧬
   BioAnalyzer - BugSigDB Field Analysis Tool
🧬 =============================================== 🧬
        """)
    
    def print_help(self):
        """Print comprehensive help information."""
        self.print_banner()
        print("""
📋 AVAILABLE COMMANDS:
=====================

🔧 Setup Commands:
   BioAnalyzer build                    Build Docker containers
   BioAnalyzer start                    Start the application
   BioAnalyzer stop                     Stop the application
   BioAnalyzer restart                  Restart the application
   BioAnalyzer status                   Check system status

🔬 Analysis Commands:
   BioAnalyzer analyze <pmid>           Analyze a single paper
   BioAnalyzer analyze <pmid1,pmid2>    Analyze multiple papers
   BioAnalyzer analyze --file <file>    Analyze papers from file
   BioAnalyzer fields                   Show field information

📊 Output Options:
   --format json|csv|table             Output format (default: table)
   --output <file>                     Save results to file
   --verbose                           Verbose output

📖 Examples:
   BioAnalyzer build
   BioAnalyzer start
   BioAnalyzer analyze 12345678
   BioAnalyzer analyze 12345678,87654321
   BioAnalyzer analyze --file pmids.txt --format json
   BioAnalyzer fields
   BioAnalyzer status
   BioAnalyzer stop

🌐 Web Interface:
   Once started, visit: http://localhost:3000
   API Documentation: http://localhost:8000/docs

❓ Need Help?
   BioAnalyzer help                    Show this help
   BioAnalyzer <command> --help        Show command-specific help
        """)
    
    def check_docker(self):
        """Check if Docker is available."""
        try:
            subprocess.run(["docker", "--version"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("❌ Error: Docker is not installed or not available.")
            print("Please install Docker to use BioAnalyzer.")
            return False
    
    def check_image(self):
        """Check if the Docker image exists."""
        try:
            subprocess.run(["docker", "image", "inspect", self.image_name], 
                          capture_output=True, check=True)
            return True
        except subprocess.CalledProcessError:
            return False
    
    def build_containers(self):
        """Build Docker containers."""
        print("🔨 Building BioAnalyzer containers...")
        
        if not self.check_docker():
            return False
        
        try:
            # Build the backend image
            print("📦 Building backend image...")
            result = subprocess.run([
                "docker", "build", "-t", self.image_name, "."
            ], cwd=project_root, check=True)
            
            print("✅ Backend image built successfully!")
            
            # Check if frontend directory exists
            frontend_dir = project_root.parent / "BioAnalyzer-Frontend"
            if frontend_dir.exists():
                print("📦 Building frontend image...")
                subprocess.run([
                    "docker", "build", "-t", "bioanalyzer-frontend", "."
                ], cwd=frontend_dir, check=True)
                print("✅ Frontend image built successfully!")
            
            print("🎉 All containers built successfully!")
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Error building containers: {e}")
            return False
    
    def start_application(self):
        """Start the BioAnalyzer application."""
        print("🚀 Starting BioAnalyzer application...")
        
        if not self.check_docker():
            return False
        
        if not self.check_image():
            print("❌ Docker image not found. Building containers first...")
            if not self.build_containers():
                return False
        
        try:
            # Start backend container
            print("🔧 Starting backend API...")
            subprocess.run([
                "docker", "run", "-d", "--name", self.container_name,
                "-p", "8000:8000", self.image_name
            ], check=True)
            
            # Wait for backend to be ready
            print("⏳ Waiting for backend to be ready...")
            time.sleep(5)
            
            # Check if backend is running
            if self.check_backend_health():
                print("✅ Backend API is running at http://localhost:8000")
            else:
                print("⚠️  Backend started but may not be fully ready yet")
            
            # Start frontend if available
            frontend_dir = project_root.parent / "BioAnalyzer-Frontend"
            if frontend_dir.exists():
                print("🌐 Starting frontend...")
                subprocess.run([
                    "docker", "run", "-d", "--name", "bioanalyzer-frontend",
                    "-p", "3000:80", "bioanalyzer-frontend"
                ], check=True)
                print("✅ Frontend is running at http://localhost:3000")
            
            print("\n🎉 BioAnalyzer is now running!")
            print("📱 Web Interface: http://localhost:3000")
            print("🔧 API Documentation: http://localhost:8000/docs")
            print("💡 Use 'BioAnalyzer status' to check system status")
            
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Error starting application: {e}")
            return False
    
    def stop_application(self):
        """Stop the BioAnalyzer application."""
        print("🛑 Stopping BioAnalyzer application...")
        
        try:
            # Stop and remove containers
            containers = [self.container_name, "bioanalyzer-frontend"]
            
            for container in containers:
                try:
                    subprocess.run(["docker", "stop", container], 
                                 capture_output=True, check=True)
                    subprocess.run(["docker", "rm", container], 
                                 capture_output=True, check=True)
                    print(f"✅ Stopped {container}")
                except subprocess.CalledProcessError:
                    pass  # Container might not exist
            
            print("✅ BioAnalyzer application stopped")
            return True
            
        except Exception as e:
            print(f"❌ Error stopping application: {e}")
            return False
    
    def restart_application(self):
        """Restart the BioAnalyzer application."""
        print("🔄 Restarting BioAnalyzer application...")
        self.stop_application()
        time.sleep(2)
        return self.start_application()
    
    def check_backend_health(self):
        """Check if the backend is healthy."""
        try:
            import requests
            response = requests.get("http://localhost:8000/health", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def get_system_status(self):
        """Get system status information."""
        print("📊 BioAnalyzer System Status")
        print("=" * 40)
        
        # Check Docker
        docker_available = self.check_docker()
        print(f"Docker: {'✅ Available' if docker_available else '❌ Not Available'}")
        
        if not docker_available:
            return
        
        # Check image
        image_exists = self.check_image()
        print(f"Backend Image: {'✅ Built' if image_exists else '❌ Not Built'}")
        
        # Check containers
        try:
            result = subprocess.run([
                "docker", "ps", "--filter", f"name={self.container_name}", "--format", "{{.Status}}"
            ], capture_output=True, text=True, check=True)
            
            if result.stdout.strip():
                print(f"Backend Container: ✅ {result.stdout.strip()}")
            else:
                print("Backend Container: ❌ Not Running")
        except:
            print("Backend Container: ❌ Not Running")
        
        # Check frontend
        try:
            result = subprocess.run([
                "docker", "ps", "--filter", "name=bioanalyzer-frontend", "--format", "{{.Status}}"
            ], capture_output=True, text=True, check=True)
            
            if result.stdout.strip():
                print(f"Frontend Container: ✅ {result.stdout.strip()}")
            else:
                print("Frontend Container: ❌ Not Running")
        except:
            print("Frontend Container: ❌ Not Running")
        
        # Check API health
        if self.check_backend_health():
            print("API Health: ✅ Healthy")
            print("🌐 Web Interface: http://localhost:3000")
            print("🔧 API Documentation: http://localhost:8000/docs")
        else:
            print("API Health: ❌ Not Responding")
    
    def interactive_analysis(self):
        """Start interactive analysis mode."""
        self.print_banner()
        print("🔬 Interactive Analysis Mode")
        print("=" * 40)
        print("Enter PMIDs to analyze (one per line, or comma-separated)")
        print("Type 'help' for commands, 'quit' to exit")
        print()
        
        while True:
            try:
                user_input = input("BioAnalyzer> ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'q']:
                    print("👋 Goodbye!")
                    break
                elif user_input.lower() == 'help':
                    print("""
📋 Available commands:
   <pmid>                    Analyze a single paper
   <pmid1,pmid2,pmid3>      Analyze multiple papers
   help                      Show this help
   quit                      Exit interactive mode
                    """)
                    continue
                elif not user_input:
                    continue
                
                # Parse PMIDs
                pmids = []
                if ',' in user_input:
                    pmids = [p.strip() for p in user_input.split(',') if p.strip()]
                else:
                    pmids = [user_input]
                
                if pmids:
                    print(f"🔬 Analyzing {len(pmids)} paper(s)...")
                    asyncio.run(self.analyze_papers_interactive(pmids))
                
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
    
    async def analyze_papers_interactive(self, pmids: List[str]):
        """Analyze papers in interactive mode."""
        try:
            import requests
            
            for i, pmid in enumerate(pmids, 1):
                print(f"\n[{i}/{len(pmids)}] Analyzing PMID: {pmid}")
                
                try:
                    # Use API instead of direct import
                    response = requests.get(f"http://localhost:8000/api/v1/analyze/{pmid}", timeout=60)
                    
                    if response.status_code == 200:
                        result = response.json()
                        print(f"✅ Analysis completed for PMID {pmid}")
                        
                        # Show quick summary
                        fields = result.get('fields', {})
                        present_count = sum(1 for f in fields.values() if f.get('status') == 'PRESENT')
                        print(f"   📊 Fields present: {present_count}/6")
                        
                        # Show field status
                        field_names = {
                            'host_species': 'Host Species',
                            'body_site': 'Body Site',
                            'condition': 'Condition',
                            'sequencing_type': 'Sequencing Type',
                            'taxa_level': 'Taxa Level',
                            'sample_size': 'Sample Size'
                        }
                        
                        for field_key, field_name in field_names.items():
                            field_data = fields.get(field_key, {})
                            status = field_data.get('status', 'UNKNOWN')
                            status_icons = {
                                'PRESENT': '✅',
                                'PARTIALLY_PRESENT': '⚠️',
                                'ABSENT': '❌'
                            }
                            icon = status_icons.get(status, '❓')
                            print(f"   {icon} {field_name}: {status}")
                    else:
                        error_detail = response.json().get('detail', 'Unknown error')
                        print(f"❌ Analysis failed for PMID {pmid}: {error_detail}")
                        
                except requests.exceptions.RequestException as e:
                    print(f"❌ Error connecting to API for PMID {pmid}: {e}")
                except Exception as e:
                    print(f"❌ Error analyzing PMID {pmid}: {e}")
        
        except ImportError:
            print("❌ Error: requests module not available. Please install it: pip install requests")
        except Exception as e:
            print(f"❌ Error: {e}")
    
    async def analyze_papers(self, pmids: List[str], output_format: str = 'table', output_file: Optional[str] = None):
        """Analyze papers and return results."""
        try:
            import requests
            
            results = []
            total = len(pmids)
            
            print(f"🔬 Analyzing {total} paper(s)...")
            
            for i, pmid in enumerate(pmids, 1):
                print(f"[{i}/{total}] Analyzing PMID: {pmid}")
                
                try:
                    # Use API instead of direct import
                    response = requests.get(f"http://localhost:8000/api/v1/analyze/{pmid}", timeout=60)
                    
                    if response.status_code == 200:
                        result = response.json()
                        results.append(result)
                        print(f"✅ Analysis completed for PMID {pmid}")
                    else:
                        error_detail = response.json().get('detail', 'Unknown error')
                        print(f"❌ Analysis failed for PMID {pmid}: {error_detail}")
                        
                except requests.exceptions.RequestException as e:
                    print(f"❌ Error connecting to API for PMID {pmid}: {e}")
                except Exception as e:
                    print(f"❌ Error analyzing PMID {pmid}: {e}")
            
            if results:
                if output_file:
                    self.save_results(results, output_file, output_format)
                else:
                    self.display_results(results, output_format)
            else:
                print("❌ No results obtained.")
                
        except ImportError:
            print("❌ Error: requests module not available. Please install it: pip install requests")
        except Exception as e:
            print(f"❌ Error: {e}")
    
    def display_results(self, results: List[Dict[str, Any]], output_format: str):
        """Display results in the specified format."""
        if output_format == 'json':
            print(json.dumps(results, indent=2, ensure_ascii=False))
        elif output_format == 'csv':
            self.display_csv_results(results)
        else:
            self.display_table_results(results)
    
    def display_table_results(self, results: List[Dict[str, Any]]):
        """Display results in table format."""
        if not results:
            print("No results to display.")
            return
        
        print("\n" + "="*80)
        print("🧬 BIOANALYZER - BugSigDB FIELD ANALYSIS RESULTS")
        print("="*80)
        
        for result in results:
            print(f"\n📄 PMID: {result.get('pmid', 'N/A')}")
            print(f"📝 Title: {result.get('title', 'N/A')}")
            print(f"📰 Journal: {result.get('journal', 'N/A')}")
            print("-" * 60)
            
            fields = result.get('fields', {})
            field_names = {
                'host_species': 'Host Species',
                'body_site': 'Body Site',
                'condition': 'Condition',
                'sequencing_type': 'Sequencing Type',
                'taxa_level': 'Taxa Level',
                'sample_size': 'Sample Size'
            }
            
            for field_key, field_name in field_names.items():
                field_data = fields.get(field_key, {})
                status = field_data.get('status', 'UNKNOWN')
                value = field_data.get('value', 'N/A')
                confidence = field_data.get('confidence', 0.0)
                
                status_icons = {
                    'PRESENT': '✅',
                    'PARTIALLY_PRESENT': '⚠️',
                    'ABSENT': '❌'
                }
                icon = status_icons.get(status, '❓')
                
                print(f"{icon} {field_name:20} | {status:20} | {str(value):30} | {confidence:.2f}")
            
            print("-" * 60)
            print(f"📋 Summary: {result.get('curation_summary', 'N/A')}")
            print(f"⏱️  Time: {result.get('processing_time', 0):.2f}s")
            print()
    
    def display_csv_results(self, results: List[Dict[str, Any]]):
        """Display results in CSV format."""
        if not results:
            print("No results to display.")
            return
        
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        headers = ['PMID', 'Title', 'Journal', 'Host Species', 'Host Species Status', 
                  'Body Site', 'Body Site Status', 'Condition', 'Condition Status',
                  'Sequencing Type', 'Sequencing Type Status', 'Taxa Level', 'Taxa Level Status',
                  'Sample Size', 'Sample Size Status', 'Summary', 'Processing Time']
        writer.writerow(headers)
        
        # Data rows
        for result in results:
            fields = result.get('fields', {})
            row = [
                result.get('pmid', ''),
                result.get('title', ''),
                result.get('journal', ''),
                fields.get('host_species', {}).get('value', ''),
                fields.get('host_species', {}).get('status', ''),
                fields.get('body_site', {}).get('value', ''),
                fields.get('body_site', {}).get('status', ''),
                fields.get('condition', {}).get('value', ''),
                fields.get('condition', {}).get('status', ''),
                fields.get('sequencing_type', {}).get('value', ''),
                fields.get('sequencing_type', {}).get('status', ''),
                fields.get('taxa_level', {}).get('value', ''),
                fields.get('taxa_level', {}).get('status', ''),
                fields.get('sample_size', {}).get('value', ''),
                fields.get('sample_size', {}).get('status', ''),
                result.get('curation_summary', ''),
                result.get('processing_time', 0)
            ]
            writer.writerow(row)
        
        print(output.getvalue())
    
    def save_results(self, results: List[Dict[str, Any]], filename: str, output_format: str):
        """Save results to a file."""
        if output_format == 'json':
            content = json.dumps(results, indent=2, ensure_ascii=False)
        elif output_format == 'csv':
            content = self.get_csv_content(results)
        else:
            content = self.get_table_content(results)
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"💾 Results saved to: {filename}")
    
    def get_csv_content(self, results: List[Dict[str, Any]]) -> str:
        """Get CSV content for results."""
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        headers = ['PMID', 'Title', 'Journal', 'Host Species', 'Host Species Status', 
                  'Body Site', 'Body Site Status', 'Condition', 'Condition Status',
                  'Sequencing Type', 'Sequencing Type Status', 'Taxa Level', 'Taxa Level Status',
                  'Sample Size', 'Sample Size Status', 'Summary', 'Processing Time']
        writer.writerow(headers)
        
        # Data rows
        for result in results:
            fields = result.get('fields', {})
            row = [
                result.get('pmid', ''),
                result.get('title', ''),
                result.get('journal', ''),
                fields.get('host_species', {}).get('value', ''),
                fields.get('host_species', {}).get('status', ''),
                fields.get('body_site', {}).get('value', ''),
                fields.get('body_site', {}).get('status', ''),
                fields.get('condition', {}).get('value', ''),
                fields.get('condition', {}).get('status', ''),
                fields.get('sequencing_type', {}).get('value', ''),
                fields.get('sequencing_type', {}).get('status', ''),
                fields.get('taxa_level', {}).get('value', ''),
                fields.get('taxa_level', {}).get('status', ''),
                fields.get('sample_size', {}).get('value', ''),
                fields.get('sample_size', {}).get('status', ''),
                result.get('curation_summary', ''),
                result.get('processing_time', 0)
            ]
            writer.writerow(row)
        
        return output.getvalue()
    
    def get_table_content(self, results: List[Dict[str, Any]]) -> str:
        """Get table content for results."""
        # Implementation similar to display_table_results but return string
        return "Table content implementation"
    
    def show_fields_info(self):
        """Show information about BugSigDB fields."""
        print("""
🧬 BioAnalyzer - BugSigDB Essential Fields
==========================================

📋 6 Essential Fields for BugSigDB Curation:

🧬 Host Species (host_species):
   Description: The host organism being studied (e.g., Human, Mouse, Rat)
   Required: Yes

📍 Body Site (body_site):
   Description: Where the microbiome sample was collected (e.g., Gut, Oral, Skin)
   Required: Yes

🏥 Condition (condition):
   Description: What disease, treatment, or exposure is being studied
   Required: Yes

🔬 Sequencing Type (sequencing_type):
   Description: What molecular method was used (e.g., 16S, metagenomics)
   Required: Yes

🌳 Taxa Level (taxa_level):
   Description: What taxonomic level was analyzed (e.g., phylum, genus, species)
   Required: Yes

👥 Sample Size (sample_size):
   Description: Number of samples or participants analyzed
   Required: Yes

📊 Field Status Values:
   ✅ PRESENT: Information is complete and clear
   ⚠️  PARTIALLY_PRESENT: Some information available but incomplete
   ❌ ABSENT: Information is missing
        """)


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="BioAnalyzer - User-Friendly BugSigDB Analysis Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  BioAnalyzer help                    # Show help
  BioAnalyzer build                   # Build containers
  BioAnalyzer start                   # Start application
  BioAnalyzer analyze 12345678        # Analyze single paper
  BioAnalyzer analyze 12345678,87654321  # Analyze multiple papers
  BioAnalyzer fields                  # Show field information
  BioAnalyzer status                  # Check status
  BioAnalyzer stop                    # Stop application
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Help command
    help_parser = subparsers.add_parser('help', help='Show help information')
    
    # Build command
    build_parser = subparsers.add_parser('build', help='Build Docker containers')
    
    # Start command
    start_parser = subparsers.add_parser('start', help='Start the application')
    start_parser.add_argument('--interactive', '-i', action='store_true',
                            help='Start in interactive mode')
    
    # Stop command
    stop_parser = subparsers.add_parser('stop', help='Stop the application')
    
    # Restart command
    restart_parser = subparsers.add_parser('restart', help='Restart the application')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Check system status')
    
    # Analyze command
    analyze_parser = subparsers.add_parser('analyze', help='Analyze papers')
    analyze_parser.add_argument('pmids', nargs='*', help='PubMed IDs to analyze')
    analyze_parser.add_argument('--file', '-f', help='File containing PMIDs')
    analyze_parser.add_argument('--format', choices=['table', 'json', 'csv'], 
                              default='table', help='Output format')
    analyze_parser.add_argument('--output', '-o', help='Output file')
    analyze_parser.add_argument('--verbose', '-v', action='store_true',
                              help='Verbose output')
    
    # Fields command
    fields_parser = subparsers.add_parser('fields', help='Show field information')
    
    args = parser.parse_args()
    
    cli = BioAnalyzerCLI()
    cli.verbose = args.verbose if hasattr(args, 'verbose') else False
    
    if not args.command or args.command == 'help':
        cli.print_help()
        return
    
    if args.command == 'build':
        cli.build_containers()
        return
    
    if args.command == 'start':
        if args.interactive:
            cli.start_application()
            cli.interactive_analysis()
        else:
            cli.start_application()
        return
    
    if args.command == 'stop':
        cli.stop_application()
        return
    
    if args.command == 'restart':
        cli.restart_application()
        return
    
    if args.command == 'status':
        cli.get_system_status()
        return
    
    if args.command == 'fields':
        cli.show_fields_info()
        return
    
    if args.command == 'analyze':
        pmids = []
        
        # Get PMIDs from different sources
        if args.pmids:
            # Handle comma-separated PMIDs
            for pmid in args.pmids:
                if ',' in pmid:
                    pmids.extend([p.strip() for p in pmid.split(',') if p.strip()])
                else:
                    pmids.append(pmid)
        
        if args.file:
            try:
                with open(args.file, 'r') as f:
                    file_pmids = [line.strip() for line in f if line.strip()]
                    pmids.extend(file_pmids)
            except Exception as e:
                print(f"❌ Error reading file: {e}")
                return
        
        if not pmids:
            print("❌ Error: No PMIDs provided.")
            print("Usage: BioAnalyzer analyze <pmid1> [pmid2] ...")
            print("   or: BioAnalyzer analyze <pmid1,pmid2,pmid3>")
            print("   or: BioAnalyzer analyze --file <file>")
            return
        
        # Remove duplicates while preserving order
        seen = set()
        unique_pmids = []
        for pmid in pmids:
            if pmid not in seen:
                seen.add(pmid)
                unique_pmids.append(pmid)
        
        asyncio.run(cli.analyze_papers(
            unique_pmids, 
            args.format, 
            args.output
        ))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)