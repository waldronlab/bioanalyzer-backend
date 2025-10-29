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
   BioAnalyzer - Curatable Signature Analysis Tool
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

📥 Retrieval Commands:
   BioAnalyzer retrieve <pmid>          Retrieve full paper text and metadata
   BioAnalyzer retrieve <pmid1,pmid2>   Retrieve multiple papers
   BioAnalyzer retrieve --file <file>  Retrieve papers from file

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
   BioAnalyzer retrieve 12345678
   BioAnalyzer retrieve 12345678,87654321 --save
   BioAnalyzer retrieve --file pmids.txt --format json
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
            print(" Error: Docker is not installed or not available.")
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
            
            print(" All containers built successfully!")
            return True
            
        except subprocess.CalledProcessError as e:
            print(f" Error building containers: {e}")
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
            # Check if container already exists
            check_result = subprocess.run(
                ["docker", "ps", "-a", "--filter", f"name={self.container_name}", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                check=False
            )
            
            if check_result.stdout.strip():
                # Container exists - check if it's running
                ps_result = subprocess.run(
                    ["docker", "ps", "--filter", f"name={self.container_name}", "--format", "{{.Names}}"],
                    capture_output=True,
                    text=True,
                    check=False
                )
                
                if ps_result.stdout.strip():
                    # Container is already running
                    print(f"⚠️  Container '{self.container_name}' is already running!")
                    print(f"✅ Backend API is available at http://localhost:8000")
                    return True
                else:
                    # Container exists but is stopped - remove it first
                    print(f"🧹 Removing existing stopped container '{self.container_name}'...")
                    subprocess.run(
                        ["docker", "rm", self.container_name],
                        capture_output=True,
                        check=False
                    )
            
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
                frontend_name = "bioanalyzer-frontend"
                # Check if frontend container already exists
                frontend_check = subprocess.run(
                    ["docker", "ps", "-a", "--filter", f"name={frontend_name}", "--format", "{{.Names}}"],
                    capture_output=True,
                    text=True,
                    check=False
                )
                
                if frontend_check.stdout.strip():
                    # Container exists - check if it's running
                    frontend_ps = subprocess.run(
                        ["docker", "ps", "--filter", f"name={frontend_name}", "--format", "{{.Names}}"],
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    
                    if frontend_ps.stdout.strip():
                        print(f"⚠️  Frontend container '{frontend_name}' is already running!")
                    else:
                        # Container exists but is stopped - remove it first
                        print(f"🧹 Removing existing stopped frontend container...")
                        subprocess.run(
                            ["docker", "rm", frontend_name],
                            capture_output=True,
                            check=False
                        )
                        print("🌐 Starting frontend...")
                        subprocess.run([
                            "docker", "run", "-d", "--name", frontend_name,
                            "-p", "3000:80", "bioanalyzer-frontend"
                        ], check=True)
                        print("✅ Frontend is running at http://localhost:3000")
                else:
                    print("🌐 Starting frontend...")
                    subprocess.run([
                        "docker", "run", "-d", "--name", frontend_name,
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
        elif output_format == 'xml':
            self.display_xml_results(results)
        else:
            self.display_table_results(results)
    
    def display_table_results(self, results: List[Dict[str, Any]]):
        """Display results in table format."""
        if not results:
            print("No results to display.")
            return
        
        print("\n" + "="*80)
        print("🧬 BIOANALYZER - CURATABLE SIGNATURE ANALYSIS RESULTS")
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
    
    def display_xml_results(self, results: List[Dict[str, Any]]):
        """Display results in XML format."""
        if not results:
            print("No results to display.")
            return
        
        print('<?xml version="1.0" encoding="UTF-8"?>')
        print('<BioAnalyzerResults>')
        
        for result in results:
            print(f'  <Analysis>')
            print(f'    <PMID>{result.get("pmid", "")}</PMID>')
            print(f'    <Title>{result.get("title", "")}</Title>')
            print(f'    <Journal>{result.get("journal", "")}</Journal>')
            print(f'    <ProcessingTime>{result.get("processing_time", 0)}</ProcessingTime>')
            
            fields = result.get('fields', {})
            print(f'    <Fields>')
            
            field_names = {
                'host_species': 'HostSpecies',
                'body_site': 'BodySite', 
                'condition': 'Condition',
                'sequencing_type': 'SequencingType',
                'taxa_level': 'TaxaLevel',
                'sample_size': 'SampleSize'
            }
            
            for field_key, field_name in field_names.items():
                field_data = fields.get(field_key, {})
                status = field_data.get('status', 'UNKNOWN')
                value = field_data.get('value', 'N/A')
                confidence = field_data.get('confidence', 0.0)
                
                print(f'      <{field_name}>')
                print(f'        <Status>{status}</Status>')
                print(f'        <Value><![CDATA[{value}]]></Value>')
                print(f'        <Confidence>{confidence:.2f}</Confidence>')
                print(f'      </{field_name}>')
            
            print(f'    </Fields>')
            print(f'    <Summary><![CDATA[{result.get("curation_summary", "")}]]></Summary>')
            print(f'  </Analysis>')
        
        print('</BioAnalyzerResults>')
    
    def save_results(self, results: List[Dict[str, Any]], filename: str, output_format: str):
        """Save results to a file."""
        if output_format == 'json':
            content = json.dumps(results, indent=2, ensure_ascii=False)
        elif output_format == 'csv':
            content = self.get_csv_content(results)
        elif output_format == 'xml':
            content = self.get_xml_content(results)
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
    
    def get_xml_content(self, results: List[Dict[str, Any]]) -> str:
        """Get XML content for results."""
        if not results:
            return '<?xml version="1.0" encoding="UTF-8"?>\n<BioAnalyzerResults></BioAnalyzerResults>'
        
        xml_content = ['<?xml version="1.0" encoding="UTF-8"?>']
        xml_content.append('<BioAnalyzerResults>')
        
        for result in results:
            xml_content.append('  <Analysis>')
            xml_content.append(f'    <PMID>{result.get("pmid", "")}</PMID>')
            xml_content.append(f'    <Title>{result.get("title", "")}</Title>')
            xml_content.append(f'    <Journal>{result.get("journal", "")}</Journal>')
            xml_content.append(f'    <ProcessingTime>{result.get("processing_time", 0)}</ProcessingTime>')
            
            fields = result.get('fields', {})
            xml_content.append('    <Fields>')
            
            field_names = {
                'host_species': 'HostSpecies',
                'body_site': 'BodySite', 
                'condition': 'Condition',
                'sequencing_type': 'SequencingType',
                'taxa_level': 'TaxaLevel',
                'sample_size': 'SampleSize'
            }
            
            for field_key, field_name in field_names.items():
                field_data = fields.get(field_key, {})
                status = field_data.get('status', 'UNKNOWN')
                value = field_data.get('value', 'N/A')
                confidence = field_data.get('confidence', 0.0)
                
                xml_content.append(f'      <{field_name}>')
                xml_content.append(f'        <Status>{status}</Status>')
                xml_content.append(f'        <Value><![CDATA[{value}]]></Value>')
                xml_content.append(f'        <Confidence>{confidence:.2f}</Confidence>')
                xml_content.append(f'      </{field_name}>')
            
            xml_content.append('    </Fields>')
            xml_content.append(f'    <Summary><![CDATA[{result.get("curation_summary", "")}]]></Summary>')
            xml_content.append('  </Analysis>')
        
        xml_content.append('</BioAnalyzerResults>')
        return '\n'.join(xml_content)
    
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

    async def retrieve_papers(self, pmids: List[str], output_format: str = 'table', 
                           output_file: Optional[str] = None, save_to_file: bool = False):
        """Retrieve papers and return results."""
        try:
            retriever = self._get_pubmed_retriever()
            results = self._fetch_papers_data(retriever, pmids)
            self._process_retrieval_results(results, output_format, output_file, save_to_file)
        except Exception as e:
            self._handle_retrieval_error(e)
    
    def _get_pubmed_retriever(self):
        """Get a PubMed retriever instance."""
        try:
            from app.services.standalone_pubmed_retriever import StandalonePubMedRetriever
            return StandalonePubMedRetriever()
        except ImportError:
            # Fallback to inline implementation
            return self._create_standalone_retriever()
    
    def _fetch_papers_data(self, retriever, pmids: List[str]) -> List[Dict[str, Any]]:
        """Fetch paper data for all PMIDs."""
        total = len(pmids)
        print(f"📥 Retrieving {total} paper(s)...")
        
        results = []
        for i, pmid in enumerate(pmids, 1):
            paper_data = self._fetch_single_paper(retriever, pmid)
            self._log_retrieval_progress(i, total, paper_data)
            results.append(paper_data)
        
        return results
    
    def _fetch_single_paper(self, retriever, pmid: str) -> Dict[str, Any]:
        """Fetch data for a single paper."""
        try:
            return retriever.get_full_paper_data(pmid)
        except Exception as e:
            return {
                "pmid": pmid,
                "error": f"Retrieval failed: {str(e)}",
                "retrieval_timestamp": time.time()
            }
    
    def _log_retrieval_progress(self, current: int, total: int, paper_data: Dict[str, Any]):
        """Log the progress of paper retrieval."""
        pmid = paper_data.get('pmid', 'unknown')
        print(f"[{current}/{total}] Retrieved PMID: {pmid}")
        
        if "error" in paper_data:
            print(f"❌ Retrieval failed for PMID {pmid}: {paper_data['error']}")
        else:
            print(f"✅ Successfully retrieved PMID {pmid}")
            if paper_data.get('has_full_text'):
                print(f"   📖 Full text available")
            else:
                print(f"   📄 Abstract only")
    
    def _process_retrieval_results(self, results: List[Dict[str, Any]], output_format: str, 
                                 output_file: Optional[str], save_to_file: bool):
        """Process and output the retrieval results."""
        if not results:
            print("❌ No results obtained.")
            return
        
        if save_to_file:
            self._save_individual_papers(results)
        
        if output_file:
            self.save_retrieval_results(results, output_file, output_format)
        else:
            self.display_retrieval_results(results, output_format)
    
    def _save_individual_papers(self, results: List[Dict[str, Any]]):
        """Save individual papers to separate files."""
        for paper_data in results:
            if "error" not in paper_data:
                self._save_individual_paper(paper_data)
    
    def _handle_retrieval_error(self, error: Exception):
        """Handle retrieval errors."""
        print(f"❌ Error: {error}")
        print("Please check your internet connection and try again.")
    
    def _create_standalone_retriever(self):
        """Create a fallback standalone PubMed retriever."""
        # This is a minimal fallback implementation
        # The main implementation is in standalone_pubmed_retriever.py
        import requests
        from xml.etree import ElementTree
        
        class FallbackRetriever:
            def __init__(self):
                self.session = requests.Session()
                self.session.headers.update({
                    "User-Agent": "BioAnalyzer/1.0 (contact: bioanalyzer@example.com)"
                })
            
            def get_full_paper_data(self, pmid: str) -> Dict[str, Any]:
                try:
                    # Simple metadata retrieval as fallback
                    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
                    params = {
                        "db": "pubmed",
                        "id": pmid,
                        "retmode": "xml",
                        "email": "bioanalyzer@example.com",
                        "tool": "BioAnalyzer"
                    }
                    
                    response = self.session.get(url, params=params, timeout=10)
                    response.raise_for_status()
                    
                    root = ElementTree.fromstring(response.text)
                    article = root.find(".//PubmedArticle/MedlineCitation/Article")
                    
                    if article is None:
                        return {"pmid": pmid, "error": "No article found"}
                    
                    title = article.findtext("ArticleTitle", default="N/A")
                    journal = article.findtext("Journal/Title", default="N/A")
                    
                    return {
                        "pmid": pmid,
                        "title": title,
                        "abstract": "",
                        "journal": journal,
                        "authors": [],
                        "publication_date": "",
                        "full_text": "",
                        "has_full_text": False,
                        "retrieval_timestamp": time.time()
                    }
                except Exception as e:
                    return {
                        "pmid": pmid,
                        "error": f"Retrieval failed: {str(e)}",
                        "retrieval_timestamp": time.time()
                    }
        
        return FallbackRetriever()
    
    def _save_individual_paper(self, paper_data: Dict[str, Any]) -> str:
        """Save individual paper data to a JSON file."""
        try:
            pmid = paper_data.get("pmid", "unknown")
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"paper_data_{pmid}_{timestamp}.json"
            filepath = Path("results") / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(paper_data, f, indent=2, ensure_ascii=False)
            
            print(f"   💾 Saved to: {filepath}")
            return str(filepath)
            
        except Exception as e:
            print(f"   ❌ Error saving paper data: {e}")
            return ""

    def display_retrieval_results(self, results: List[Dict[str, Any]], output_format: str):
        """Display retrieval results in the specified format."""
        if output_format == 'json':
            print(json.dumps(results, indent=2, ensure_ascii=False))
        elif output_format == 'csv':
            self.display_csv_retrieval_results(results)
        else:
            self.display_table_retrieval_results(results)

    def display_table_retrieval_results(self, results: List[Dict[str, Any]]):
        """Display retrieval results in table format."""
        if not results:
            print("No results to display.")
            return
        
        print("\n" + "="*80)
        print("📥 BIOANALYZER - PUBMED PAPER RETRIEVAL RESULTS")
        print("="*80)
        
        for result in results:
            if "error" in result:
                print(f"\n❌ PMID: {result.get('pmid', 'N/A')}")
                print(f"Error: {result['error']}")
                continue
            
            print(f"\n📄 PMID: {result.get('pmid', 'N/A')}")
            print(f"📝 Title: {result.get('title', 'N/A')}")
            print(f"📰 Journal: {result.get('journal', 'N/A')}")
            print(f"👥 Authors: {', '.join(result.get('authors', [])[:3])}{' et al.' if len(result.get('authors', [])) > 3 else ''}")
            print(f"📅 Publication Date: {result.get('publication_date', 'N/A')}")
            print(f"📖 Full Text: {'✅ Available' if result.get('has_full_text') else '❌ Not available'}")
            
            # Show abstract preview
            abstract = result.get('abstract', '')
            if abstract:
                preview = abstract[:200] + "..." if len(abstract) > 200 else abstract
                print(f"📋 Abstract Preview: {preview}")
            
            # Show full text preview if available
            if result.get('has_full_text'):
                full_text = result.get('full_text', '')
                if full_text:
                    preview = full_text[:300] + "..." if len(full_text) > 300 else full_text
                    print(f"📄 Full Text Preview: {preview}")
            
            print("-" * 60)

    def display_csv_retrieval_results(self, results: List[Dict[str, Any]]):
        """Display retrieval results in CSV format."""
        if not results:
            print("No results to display.")
            return
        
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        headers = ['PMID', 'Title', 'Journal', 'Authors', 'Publication Date', 
                  'Has Full Text', 'Abstract Length', 'Full Text Length', 'Error']
        writer.writerow(headers)
        
        # Data rows
        for result in results:
            row = [
                result.get('pmid', ''),
                result.get('title', ''),
                result.get('journal', ''),
                '; '.join(result.get('authors', [])),
                result.get('publication_date', ''),
                'Yes' if result.get('has_full_text') else 'No',
                len(result.get('abstract', '')),
                len(result.get('full_text', '')),
                result.get('error', '')
            ]
            writer.writerow(row)
        
        print(output.getvalue())

    def save_retrieval_results(self, results: List[Dict[str, Any]], filename: str, output_format: str):
        """Save retrieval results to a file."""
        if output_format == 'json':
            content = json.dumps(results, indent=2, ensure_ascii=False)
        elif output_format == 'csv':
            content = self.get_csv_retrieval_content(results)
        else:
            content = self.get_table_retrieval_content(results)
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"💾 Retrieval results saved to: {filename}")

    def get_csv_retrieval_content(self, results: List[Dict[str, Any]]) -> str:
        """Get CSV content for retrieval results."""
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        headers = ['PMID', 'Title', 'Journal', 'Authors', 'Publication Date', 
                  'Has Full Text', 'Abstract Length', 'Full Text Length', 'Error']
        writer.writerow(headers)
        
        # Data rows
        for result in results:
            row = [
                result.get('pmid', ''),
                result.get('title', ''),
                result.get('journal', ''),
                '; '.join(result.get('authors', [])),
                result.get('publication_date', ''),
                'Yes' if result.get('has_full_text') else 'No',
                len(result.get('abstract', '')),
                len(result.get('full_text', '')),
                result.get('error', '')
            ]
            writer.writerow(row)
        
        return output.getvalue()

    def get_table_retrieval_content(self, results: List[Dict[str, Any]]) -> str:
        """Get table content for retrieval results."""
        content = "BIOANALYZER - PUBMED PAPER RETRIEVAL RESULTS\n"
        content += "=" * 50 + "\n\n"
        
        for result in results:
            if "error" in result:
                content += f"PMID: {result.get('pmid', 'N/A')}\n"
                content += f"Error: {result['error']}\n\n"
                continue
            
            content += f"PMID: {result.get('pmid', 'N/A')}\n"
            content += f"Title: {result.get('title', 'N/A')}\n"
            content += f"Journal: {result.get('journal', 'N/A')}\n"
            content += f"Authors: {', '.join(result.get('authors', [])[:3])}{' et al.' if len(result.get('authors', [])) > 3 else ''}\n"
            content += f"Publication Date: {result.get('publication_date', 'N/A')}\n"
            content += f"Full Text: {'Available' if result.get('has_full_text') else 'Not available'}\n"
            
            abstract = result.get('abstract', '')
            if abstract:
                content += f"Abstract: {abstract[:200]}{'...' if len(abstract) > 200 else ''}\n"
            
            content += "\n" + "-" * 40 + "\n\n"
        
        return content


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
  BioAnalyzer retrieve 12345678       # Retrieve single paper
  BioAnalyzer retrieve 12345678,87654321 --save  # Retrieve multiple papers and save
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
    analyze_parser.add_argument('--format', choices=['table', 'json', 'csv', 'xml'], 
                              default='table', help='Output format')
    analyze_parser.add_argument('--output', '-o', help='Output file')
    analyze_parser.add_argument('--verbose', '-v', action='store_true',
                              help='Verbose output')
    
    # Fields command
    fields_parser = subparsers.add_parser('fields', help='Show field information')
    
    # Retrieve command
    retrieve_parser = subparsers.add_parser('retrieve', help='Retrieve full paper text and metadata')
    retrieve_parser.add_argument('pmids', nargs='*', help='PubMed IDs to retrieve')
    retrieve_parser.add_argument('--file', '-f', help='File containing PMIDs')
    retrieve_parser.add_argument('--format', choices=['table', 'json', 'csv', 'xml'], 
                                default='table', help='Output format')
    retrieve_parser.add_argument('--output', '-o', help='Output file')
    retrieve_parser.add_argument('--save', '-s', action='store_true',
                               help='Save individual paper data to files')
    retrieve_parser.add_argument('--verbose', '-v', action='store_true',
                               help='Verbose output')
    
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
    
    if args.command == 'retrieve':
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
            print("Usage: BioAnalyzer retrieve <pmid1> [pmid2] ...")
            print("   or: BioAnalyzer retrieve <pmid1,pmid2,pmid3>")
            print("   or: BioAnalyzer retrieve --file <file>")
            return
        
        # Remove duplicates while preserving order
        seen = set()
        unique_pmids = []
        for pmid in pmids:
            if pmid not in seen:
                seen.add(pmid)
                unique_pmids.append(pmid)
        
        asyncio.run(cli.retrieve_papers(
            unique_pmids, 
            args.format, 
            args.output,
            args.save
        ))
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