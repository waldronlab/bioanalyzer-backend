import logging
from typing import Dict, List, Optional, Union
from pathlib import Path
from datetime import datetime
import pytz
import google.generativeai as genai
import os
import json
from app.utils.config import GEMINI_TIMEOUT
import asyncio
import time

logger = logging.getLogger(__name__)

class GeminiQA:
    """Enhanced QA system using an external model API for biomedical paper analysis."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash", results_dir: Optional[Path] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model
        logger.info(f"Initializing GeminiQA with model: {self.model}")  # Debug log for model name
        self.results_dir = results_dir or Path("results")
        self.results_dir.mkdir(parents=True, exist_ok=True)
        if not self.api_key:
            logger.warning("No model API key provided. Set GEMINI_API_KEY in your environment.")
        genai.configure(api_key=self.api_key)
        
        # Debug: List available Gemini models
        try:
            available_models = [m.name for m in genai.list_models() if 'gemini' in m.name.lower()]
            logger.info(f"Available Gemini models: {available_models}")
        except Exception as e:
            logger.warning(f"Could not list models: {e}")

    def estimate_confidence(self, key_findings):
        if not key_findings:
            return 0.0
        return min(1.0, 0.3 + 0.15 * len(key_findings))

    def estimate_category_scores(self, key_findings):
        categories = {
            "microbiome": ["microbiome", "microbial", "bacteria", "microbiota"],
            "methods": ["16s", "metagenomic", "sequencing", "amplicon", "shotgun", "transcriptomic", "qpcr", "fish"],
            "analysis": ["enriched", "depleted", "increased", "decreased", "differential", "higher abundance", "lower abundance"],
            "body_sites": ["gut", "oral", "skin", "lung", "vaginal", "intestinal", "colon", "mouth", "dermal", "epidermis", "airway", "bronchial", "cervical"],
            "diseases": ["ibd", "cancer", "tumor", "carcinoma", "neoplasm", "obesity", "diabetes", "infection", "autoimmune", "arthritis", "lupus", "multiple sclerosis"]
        }
        text = " ".join(key_findings).lower()
        scores = {}
        for cat, keywords in categories.items():
            count = sum(1 for kw in keywords if kw in text)
            scores[cat] = min(1.0, count / max(1, len(keywords)))
        return scores

    def parse_gemini_output(self, key_findings):
        findings = []
        suggested_topics = []
        in_suggested = False
        for line in key_findings:
            if 'Suggested Topics' in line or 'Suggested Topics for Future Research' in line:
                in_suggested = True
                continue
            if in_suggested:
                if line.strip().startswith('*') or line.strip().startswith('-'):
                    suggested_topics.append(line.strip('*- ').strip())
                elif line.strip() == '' or line.strip().startswith('**'):
                    continue
                else:
                    in_suggested = False
            if not in_suggested:
                findings.append(line)
        return findings, suggested_topics

    def extract_found_terms(self, key_findings):
        categories = {
            "microbiome": ["microbiome", "microbial", "bacteria", "microbiota"],
            "methods": ["16s", "metagenomic", "sequencing", "amplicon", "shotgun", "transcriptomic", "qpcr", "fish"],
            "analysis": ["enriched", "depleted", "increased", "decreased", "differential", "higher abundance", "lower abundance"],
            "body_sites": ["gut", "oral", "skin", "lung", "vaginal", "intestinal", "colon", "mouth", "dermal", "epidermis", "airway", "bronchial", "cervical"],
            "diseases": ["ibd", "cancer", "tumor", "carcinoma", "neoplasm", "obesity", "diabetes", "infection", "autoimmune", "arthritis", "lupus", "multiple sclerosis"]
        }
        text = " ".join(key_findings).lower()
        found = {}
        for cat, keywords in categories.items():
            found[cat] = [kw for kw in keywords if kw in text]
        return found

    def parse_enhanced_analysis(self, analysis_text: str) -> Dict[str, Union[str, float, List[str]]]:
        try:
            lines = analysis_text.split('\n')
            curation_analysis = {
                "readiness": "UNKNOWN",
                "explanation": "",
                "microbial_signatures": "Unknown",
                "signature_types": [],
                "data_quality": "Unknown",
                "statistical_significance": "Unknown",
                "required_fields": [],
                "missing_fields": [],
                "data_completeness": "Unknown",
                "specific_reasons": [],
                "confidence": 0.0,
                "examples": [],
                "general_factors_present": [],
                "human_animal_factors_present": [],
                "environmental_factors_present": [],
                "missing_critical_factors": [],
                "factor_based_score": 0.0
            }
            
            current_section = ""
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                if "CURATION READINESS ASSESSMENT:" in line:
                    current_section = "readiness"
                    continue
                elif "DETAILED EXPLANATION:" in line:
                    current_section = "explanation"
                    continue
                elif "FACTOR-BASED ANALYSIS:" in line:
                    current_section = "factor_analysis"
                    continue
                elif "MICROBIAL SIGNATURE ANALYSIS:" in line:
                    current_section = "signatures"
                    continue
                elif "CURATABLE CONTENT ASSESSMENT:" in line:
                    current_section = "content"
                    continue
                elif "SPECIFIC REASONS" in line:
                    current_section = "reasons"
                    continue
                elif "CONFIDENCE LEVEL:" in line:
                    current_section = "confidence"
                    continue
                elif "EXAMPLES AND EVIDENCE:" in line:
                    current_section = "examples"
                    continue
                
                if current_section == "readiness":
                    line_upper = line.upper()
                    if "READY FOR CURATION" in line_upper:
                        curation_analysis["readiness"] = "READY"
                    elif "NOT READY FOR CURATION" in line_upper:
                        curation_analysis["readiness"] = "NOT_READY"
                    elif "READY" in line_upper and "NOT" not in line_upper:
                        curation_analysis["readiness"] = "READY"
                    elif "NOT READY" in line_upper:
                        curation_analysis["readiness"] = "NOT_READY"
                    elif "UNKNOWN" in line_upper or "UNCLEAR" in line_upper:
                        curation_analysis["readiness"] = "UNKNOWN"
                elif current_section == "explanation":
                    curation_analysis["explanation"] += line + " "
                elif current_section == "factor_analysis":
                    if "General Factors Present:" in line:
                        factors_text = line.split(":", 1)[1] if ":" in line else ""
                        curation_analysis["general_factors_present"] = [f.strip() for f in factors_text.split(",") if f.strip()]
                    elif "Human/Animal Factors Present:" in line:
                        factors_text = line.split(":", 1)[1] if ":" in line else ""
                        curation_analysis["human_animal_factors_present"] = [f.strip() for f in factors_text.split(",") if f.strip()]
                    elif "Environmental Factors Present:" in line:
                        factors_text = line.split(":", 1)[1] if ":" in line else ""
                        curation_analysis["environmental_factors_present"] = [f.strip() for f in factors_text.split(",") if f.strip()]
                    elif "Missing Critical Factors:" in line:
                        factors_text = line.split(":", 1)[1] if ":" in line else ""
                        curation_analysis["missing_critical_factors"] = [f.strip() for f in factors_text.split(",") if f.strip()]
                elif current_section == "signatures":
                    if "Presence of microbial signatures:" in line:
                        if "yes" in line.lower():
                            curation_analysis["microbial_signatures"] = "Present"
                        elif "no" in line.lower():
                            curation_analysis["microbial_signatures"] = "Absent"
                        elif "partial" in line.lower():
                            curation_analysis["microbial_signatures"] = "Partial"
                    elif "Types of signatures found:" in line:
                        types_text = line.split(":", 1)[1] if ":" in line else ""
                        curation_analysis["signature_types"] = [t.strip() for t in types_text.split(",") if t.strip()]
                    elif "Quality of signature data:" in line:
                        if "high" in line.lower():
                            curation_analysis["data_quality"] = "High"
                        elif "medium" in line.lower():
                            curation_analysis["data_quality"] = "Medium"
                        elif "low" in line.lower():
                            curation_analysis["data_quality"] = "Low"
                    elif "Statistical significance:" in line:
                        if "yes" in line.lower():
                            curation_analysis["statistical_significance"] = "Yes"
                        elif "no" in line.lower():
                            curation_analysis["statistical_significance"] = "No"
                        elif "insufficient" in line.lower():
                            curation_analysis["statistical_significance"] = "Insufficient"
                elif current_section == "content":
                    if "Missing required fields:" in line:
                        fields_text = line.split(":", 1)[1] if ":" in line else ""
                        curation_analysis["missing_fields"] = [f.strip() for f in fields_text.split(",") if f.strip()]
                    elif "Data completeness:" in line:
                        if "complete" in line.lower():
                            curation_analysis["data_completeness"] = "Complete"
                        elif "partial" in line.lower():
                            curation_analysis["data_completeness"] = "Partial"
                        elif "insufficient" in line.lower():
                            curation_analysis["data_completeness"] = "Insufficient"
                elif current_section == "reasons":
                    if line.startswith("-") or line.startswith("*"):
                        curation_analysis["specific_reasons"].append(line.lstrip("- *").strip())
                elif current_section == "confidence":
                    import re
                    confidence_match = re.search(r'(\d+\.?\d*)', line)
                    if confidence_match:
                        curation_analysis["confidence"] = float(confidence_match.group(1))
                elif current_section == "examples":
                    if line.startswith("-") or line.startswith("*"):
                        curation_analysis["examples"].append(line.lstrip("- *").strip())
            
            curation_analysis["explanation"] = curation_analysis["explanation"].strip()
            total_factors = len(curation_analysis["general_factors_present"]) + \
                           len(curation_analysis["human_animal_factors_present"]) + \
                           len(curation_analysis["environmental_factors_present"])
            max_factors = 16
            curation_analysis["factor_based_score"] = min(1.0, total_factors / max_factors)
            
            return curation_analysis
            
        except Exception as e:
            logger.error(f"Error parsing enhanced analysis: {str(e)}")
            return {
                "readiness": "ERROR",
                "explanation": f"Error parsing analysis: {str(e)}",
                "microbial_signatures": "Unknown",
                "signature_types": [],
                "data_quality": "Unknown",
                "statistical_significance": "Unknown",
                "required_fields": [],
                "missing_fields": [],
                "data_completeness": "Unknown",
                "specific_reasons": [],
                "confidence": 0.0,
                "examples": [],
                "general_factors_present": [],
                "human_animal_factors_present": [],
                "environmental_factors_present": [],
                "missing_critical_factors": [],
                "factor_based_score": 0.0
            }

    async def analyze_paper(self, paper_content: Dict[str, str]) -> Dict[str, Union[str, float, Dict[str, float]]]:
        try:
            content = f"Title: {paper_content.get('title', '')}\n"
            content += f"Abstract: {paper_content.get('abstract', '')}\n"
            if paper_content.get('full_text'):
                content += f"Full Text: {paper_content['full_text']}\n"

            prompt = """You are an expert scientific curator specializing in microbial signature analysis. Your task is to analyze this paper and provide a comprehensive assessment of its curation readiness based on the methods and experimental design.

## COMPREHENSIVE CURATION READINESS CRITERIA

### GENERAL FACTORS (Applicable to ALL Study Types)
A paper is READY FOR CURATION if it contains ALL of the following fundamental factors:
1. Specific Microbial Taxa Identification
2. Differential Abundance/Compositional Changes
3. Proper Experimental Design
4. Microbiota Characterization Methodology
5. Quantitative Data/Statistical Significance
6. Data Availability/Repository Information

### METHODS-SPECIFIC ASSESSMENT CRITERIA
7. Sequencing and Molecular Methods
8. Statistical and Analytical Methods
9. Sample Collection and Processing
10. Experimental Design Quality

### SPECIFIC FACTORS FOR HUMAN/ANIMAL STUDIES
11. Host Health Outcome/Phenotype Associations
12. Host/Study Population Characteristics
13. Intervention/Exposure Details (if applicable)
14. Sample Type from Host
15. Proposed Molecular Mechanisms/Pathways

### SPECIFIC FACTORS FOR ENVIRONMENTAL STUDIES
16. Environmental Context/Associated Factors
17. Sample Type from Environment
18. Geospatial Data (Highly Valued)
19. Study Duration/Seasonality
20. Associated Chemical/Physical Measurements

### ENVIRONMENTAL STUDIES CRITERIA (Simplified Check)
A paper is READY FOR CURATION if it contains ANY of the following:
1. Indoor environment microbiome studies with human health implications
2. Built environment studies (hospitals, schools, transportation, public spaces)
3. Agricultural/food safety studies with microbial analysis
4. Industrial environment studies with health implications
5. Environmental studies with clear microbial signatures and health relevance

### NOT READY FOR CURATION Criteria
A paper is NOT READY FOR CURATION only if:
- It's purely a review article with no original research
- It contains NO microbial data or sequencing results
- It only mentions "microbiome" in passing without specific findings
- It lacks any quantitative or qualitative microbial data
- It's purely ecological without health implications
- It contains no quantitative microbial analysis

Please provide a detailed analysis in the following structured format:

**CURATION READINESS ASSESSMENT:**
[Start with a clear statement: "READY FOR CURATION" or "NOT READY FOR CURATION"]

**DETAILED EXPLANATION:**
[Provide a comprehensive explanation of why the paper is or isn't ready for curation]

**FACTOR-BASED ANALYSIS:**
- General Factors Present: [List which of the 6 general factors are present]
- Human/Animal Factors Present: [List which of the 5 human/animal factors are present, if applicable]
- Environmental Factors Present: [List which of the 5 environmental factors are present, if applicable]
- Missing Critical Factors: [List any missing factors that prevent curation readiness]

**MICROBIAL SIGNATURE ANALYSIS:**
- Presence of microbial signatures: [Yes/No/Partial]
- Types of signatures found: [List specific types like "differential abundance", "community composition"]
- Quality of signature data: [High/Medium/Low]
- Statistical significance: [Yes/No/Insufficient]

**CURATABLE CONTENT ASSESSMENT:**
- Missing required fields: [List what's missing, if any]

**SPECIFIC REASONS FOR READINESS/NON-READINESS:**
[If NOT READY, explain exactly what's missing]
[If READY, explain what makes it suitable]

**KEY FINDINGS:**
[List the main scientific findings related to microbial signatures]

**SUGGESTED TOPICS FOR FUTURE RESEARCH:**
[List potential follow-up studies]

**CONFIDENCE LEVEL:**
[Provide a confidence score (0.0-1.0) with explanation]

**EXAMPLES AND EVIDENCE:**
[Provide specific examples from the text]

CRITICAL: If the paper contains ANY specific microbial taxa identification, abundance data, or microbial community analysis, it should be marked as READY FOR CURATION."""

            model = genai.GenerativeModel(self.model)
            response = await model.generate_content_async(
                f"{prompt}\n\nAnalyze this paper:\n{content}",
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=500,
                    top_p=0.8,
                    top_k=20
                ),
                safety_settings=[
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"}
                ]
            )
            analysis_text = response.text.strip()

            if self.results_dir:
                timestamp = datetime.now(pytz.UTC).strftime("%Y%m%d_%H%M%S")
                paper_title = paper_content.get('title', 'unknown').replace(' ', '_')
                filename = self.results_dir / f"model_analysis_{timestamp}_{paper_title[:50]}.txt"
                with open(filename, 'w') as f:
                    f.write(analysis_text)
                logger.info(f"Analysis saved to {filename}")

            logger.info(f"Raw model response for debugging:\n{analysis_text}")
            curation_analysis = self.parse_enhanced_analysis(analysis_text)
            logger.info(f"Parsed curation analysis: {curation_analysis}")
            
            key_findings_raw = [line.strip() for line in analysis_text.split('\n') if line.strip()]
            confidence = self.estimate_confidence(key_findings_raw)
            category_scores = self.estimate_category_scores(key_findings_raw)
            findings, suggested_topics = self.parse_gemini_output(key_findings_raw)
            found_terms = self.extract_found_terms(key_findings_raw)

            return {
                "key_findings": findings,
                "confidence": confidence,
                "status": "success",
                "suggested_topics": suggested_topics,
                "found_terms": found_terms,
                "category_scores": category_scores,
                "num_tokens": len(analysis_text.split()),
                "curation_analysis": curation_analysis,
                "raw_analysis": analysis_text
            }
        except asyncio.TimeoutError:
            logger.error("Paper analysis request timed out")
            return {
                "error": "Request timed out",
                "confidence": 0.0,
                "status": "error",
                "key_findings": ["Analysis timed out"],
                "suggested_topics": [],
                "found_terms": {},
                "category_scores": {},
                "num_tokens": 0,
                "curation_analysis": {
                    "readiness": "ERROR",
                    "explanation": "Analysis timed out",
                    "microbial_signatures": "Unknown",
                    "missing_fields": [],
                    "confidence": 0.0
                }
            }
        except Exception as e:
            error_str = str(e)
            logger.error(f"Model API error in paper analysis: {error_str}")
            return {
                "error": error_str,
                "confidence": 0.0,
                "status": "error",
                "key_findings": ["Error analyzing paper"],
                "suggested_topics": [],
                "found_terms": {},
                "category_scores": {},
                "num_tokens": 0,
                "curation_analysis": {
                    "readiness": "ERROR",
                    "explanation": f"Error during analysis: {error_str}",
                    "microbial_signatures": "Unknown",
                    "missing_fields": [],
                    "confidence": 0.0
                }
            }

    async def analyze_paper_enhanced(self, prompt: str) -> Dict[str, Union[str, float, List[str]]]:
        try:
            if not self.api_key:
                logger.error("No Gemini API key provided")
                return {
                    "error": "No Gemini API key available. Please set the GEMINI_API_KEY environment variable.",
                    "error_type": "MissingAPIKey",
                    "key_findings": "{}",
                    "confidence": 0.0,
                    "status": "error",
                    "debug_info": {
                        "issue": "Missing API key",
                        "solution": "Set GEMINI_API_KEY environment variable",
                        "timestamp": datetime.now().isoformat()
                    }
                }
            
            model = genai.GenerativeModel(self.model)
            
            enhanced_structured_prompt = f"""
            You are a specialized AI assistant for BugSigDB curation with expertise in microbial signature analysis. Your task is to analyze scientific papers and extract specific information in a structured JSON format with high accuracy.

            {prompt}

            CRITICAL EXTRACTION GUIDELINES FOR ACCURACY:

            1. HOST SPECIES EXTRACTION:
               - Look for explicit mentions: "Human participants", "Mouse model", "Rat study", "Environmental samples"
               - Check study population descriptions, methods section, and abstract
               - For environmental studies, identify: "Built environment", "Indoor air", "Soil samples", "Water samples"
               - Be specific: "Human" not "mammal", "Mouse" not "rodent"
               - If "Human participants" or "Human subjects" found, mark PRESENT with confidence 0.9

            2. BODY SITE EXTRACTION:
               - Human/Animal: Look for "fecal", "oral swab", "skin sample", "vaginal swab", "nasal swab"
               - Environmental: Look for "indoor surface", "restroom", "hospital room", "classroom", "office"
               - Check sample collection methods and study location descriptions
               - Be precise: "Gut" not "digestive system", "Indoor air" not "air"
               - If "fecal samples" or "stool samples" found, mark PRESENT with confidence 0.9

            3. CONDITION EXTRACTION:
               - Look for disease names: "IBD", "Obesity", "Diabetes", "Cancer"
               - Check experimental conditions: "Antibiotic treatment", "Diet intervention", "Seasonal changes"
               - Identify comparative studies: "Men vs women", "Healthy vs diseased", "Before vs after"
               - Be specific: "Type 2 Diabetes" not "diabetes", "Crohn's disease" not "IBD"
               - If disease names or experimental conditions found, mark PRESENT with confidence 0.9

            4. SEQUENCING TYPE EXTRACTION:
               - Look for specific methods: "16S rRNA gene sequencing", "V4 region amplification"
               - Check for platforms: "Illumina MiSeq", "Next-generation sequencing"
               - Identify techniques: "Shotgun metagenomics", "Amplicon sequencing"
               - Be precise: "16S rRNA" not "sequencing", "Metagenomics" not "genomics"
               - If "16S" or "sequencing" found, mark PRESENT with confidence 0.9

            5. TAXA LEVEL EXTRACTION:
               - Look for taxonomic classifications: "Phylum Proteobacteria", "Genus Bacteroides"
               - Check for specific names: "E. coli", "B. fragilis", "Lactobacillus spp."
               - Identify analysis levels: "Phylum level", "Genus level", "Species level"
               - Be specific: "Bacteroides fragilis" not "Bacteroides", "Proteobacteria phylum" not "bacteria"
               - If taxonomic names or levels found, mark PRESENT with confidence 0.9

            6. SAMPLE SIZE EXTRACTION:
               - Look for numbers: "n=50 participants", "100 samples", "Three time points"
               - Check study design: "Multiple floors sampled", "Longitudinal study with 6 visits"
               - Identify sample counts: "48 fecal samples", "24 oral swabs"
               - Be precise: "n=50" not "multiple samples", "100 samples" not "large sample size"
               - If numbers or sample counts found, mark PRESENT with confidence 0.9

            CONFIDENCE SCORING GUIDELINES:
            - PRESENT (0.8-1.0): Information is explicitly stated and clear
            - PARTIALLY_PRESENT (0.4-0.7): Information is implied or partially described
            - ABSENT (0.0): Information is completely missing or unclear

            JSON RESPONSE REQUIREMENTS:
            - Return ONLY valid JSON without any explanatory text
            - Ensure all field names match exactly: "host_species", "body_site", "condition", "sequencing_type", "taxa_level", "sample_size"
            - Each field must have: "primary"/"site"/"description"/"method"/"level"/"size", "confidence", "status", "reason_if_missing", "suggestions_for_curation"
            - Use proper JSON syntax with double quotes for strings
            - Include all required sub-fields for each main field

            CRITICAL INSTRUCTIONS:
            1. READ THE TEXT THOROUGHLY - Do not skim. Read every section carefully.
            2. LOOK FOR EXPLICIT MENTIONS - If the text says "Human participants", that's PRESENT with 0.9 confidence.
            3. CHECK MULTIPLE SECTIONS - Title, abstract, methods, results, discussion.
            4. USE CONTEXT CLUES - If it mentions "fecal samples from patients", that's host "Human" and body site "Gut" with 0.9 confidence.
            5. BE CONFIDENT - If you find clear information, use high confidence (0.8-1.0).
            6. DON'T GUESS - Only mark as ABSENT if you're absolutely certain the information is missing.
            7. EXTRACT ACTUAL INFORMATION - Don't infer or guess. Look for what's explicitly stated.

            IMPORTANT: You must respond with ONLY valid JSON. Do not include any explanatory text before or after the JSON. The response should be parseable by json.loads().
            """

            logger.info(f"Starting model API call with {GEMINI_TIMEOUT}s timeout...")
            start_time = time.time()
            
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: model.generate_content(
                    enhanced_structured_prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.1,
                        max_output_tokens=500,
                        top_p=0.7,
                        top_k=10
                    )
                )),
                timeout=GEMINI_TIMEOUT
            )
            
            elapsed_time = time.time() - start_time
            logger.info(f"Gemini API call completed in {elapsed_time:.2f}s")
            
            if not response or not response.text:
                return {
                    "error": "No response generated",
                    "key_findings": "{}",
                    "confidence": 0.0
                }
            
            response_text = response.text.strip()
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_text = response_text[json_start:json_end]
            else:
                json_text = response_text
            
            try:
                parsed_json = json.loads(json_text)
                validated_json = self._validate_and_normalize_json(parsed_json)
                confidence = self._calculate_enhanced_confidence(validated_json)
                
                return {
                    "key_findings": json.dumps(validated_json, indent=2),
                    "confidence": confidence,
                    "status": "success"
                }
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON response: {e}")
                logger.warning(f"Raw response: {response_text[:500]}...")
                fallback_json = self._create_fallback_json()
                
                return {
                    "key_findings": json.dumps(fallback_json, indent=2),
                    "confidence": 0.0,
                    "status": "fallback",
                    "error": f"JSON parsing failed: {str(e)}"
                }
        except asyncio.TimeoutError:
            logger.error("Enhanced paper analysis request timed out")
            return {
                "error": "Request timed out",
                "error_type": "Timeout",
                "key_findings": "{}",
                "confidence": 0.0,
                "status": "error",
                "debug_info": {
                    "issue": "Timeout during API call",
                    "timestamp": datetime.now().isoformat()
                }
            }
        except Exception as e:
            error_msg = str(e)
            error_type = type(e).__name__
            
            if "quota" in error_msg.lower() or "quota exceeded" in error_msg.lower():
                error_detail = "Model API quota exceeded. Please check your API usage limits."
                logger.error(f"Model API quota exceeded: {error_msg}")
            elif "permission" in error_msg.lower() or "access" in error_msg.lower():
                error_detail = "Model API access denied. Check API key permissions and IP restrictions."
                logger.error(f"Model API access denied: {error_msg}")
            elif "authentication" in error_msg.lower() or "invalid" in error_msg.lower():
                error_detail = "Model API authentication failed. Check your API key."
                logger.error(f"Model API authentication failed: {error_msg}")
            elif "network" in error_msg.lower() or "connection" in error_msg.lower():
                error_detail = "Network connectivity issue. Check your internet connection."
                logger.error(f"Network connectivity issue: {error_msg}")
            elif "timeout" in error_msg.lower():
                error_detail = "Model API request timed out. The service may be slow or unavailable."
                logger.error(f"Model API timeout: {error_msg}")
            else:
                error_detail = f"Unexpected error: {error_msg}"
                logger.error(f"Unexpected error in Model API: {error_msg}")
            
            logger.error(f"Error type: {error_type}")
            logger.error(f"Error details: {error_detail}")
            logger.error(f"Full error: {error_msg}")
            
            return {
                "error": error_detail,
                "error_type": error_type,
                "key_findings": "{}",
                "confidence": 0.0,
                "status": "error",
                "debug_info": {
                    "original_error": error_msg,
                    "error_type": error_type,
                    "timestamp": datetime.now().isoformat()
                }
            }

    def _validate_and_normalize_json(self, parsed_json: Dict) -> Dict:
        required_fields = {
            "host_species": {"primary": "Unknown", "confidence": 0.0, "status": "ABSENT", "reason_if_missing": "Field not found in analysis", "suggestions_for_curation": "Review paper for host species information"},
            "body_site": {"site": "Unknown", "confidence": 0.0, "status": "ABSENT", "reason_if_missing": "Field not found in analysis", "suggestions_for_curation": "Review paper for body site information"},
            "condition": {"description": "Unknown", "confidence": 0.0, "status": "ABSENT", "reason_if_missing": "Field not found in analysis", "suggestions_for_curation": "Review paper for condition information"},
            "sequencing_type": {"method": "Unknown", "confidence": 0.0, "status": "ABSENT", "reason_if_missing": "Field not found in analysis", "suggestions_for_curation": "Review paper for sequencing method information"},
            "taxa_level": {"level": "Unknown", "confidence": 0.0, "status": "ABSENT", "reason_if_missing": "Field not found in analysis", "suggestions_for_curation": "Review paper for taxonomic level information"},
            "sample_size": {"size": "Unknown", "confidence": 0.0, "status": "ABSENT", "reason_if_missing": "Field not found in analysis", "suggestions_for_curation": "Review paper for sample size information"}
        }
        
        for field_name, default_structure in required_fields.items():
            if field_name not in parsed_json:
                parsed_json[field_name] = default_structure.copy()
            else:
                field_data = parsed_json[field_name]
                if not isinstance(field_data, dict):
                    parsed_json[field_name] = default_structure.copy()
                else:
                    for key, default_value in default_structure.items():
                        if key not in field_data:
                            field_data[key] = default_value
        
        missing_fields = [
            field for field in required_fields.keys()
            if parsed_json.get(field, {}).get("status") != "PRESENT"
        ]
        
        parsed_json["missing_fields"] = missing_fields
        parsed_json["curation_preparation_summary"] = self._generate_curation_summary(parsed_json, missing_fields)
        
        return parsed_json

    def _create_fallback_json(self) -> Dict:
        return {
            "host_species": {"primary": "Unknown", "confidence": 0.0, "status": "ABSENT", "reason_if_missing": "Analysis failed - re-run required", "suggestions_for_curation": "Re-run analysis with corrected prompt"},
            "body_site": {"site": "Unknown", "confidence": 0.0, "status": "ABSENT", "reason_if_missing": "Analysis failed - re-run required", "suggestions_for_curation": "Re-run analysis with corrected prompt"},
            "condition": {"description": "Unknown", "confidence": 0.0, "status": "ABSENT", "reason_if_missing": "Analysis failed - re-run required", "suggestions_for_curation": "Re-run analysis with corrected prompt"},
            "sequencing_type": {"method": "Unknown", "confidence": 0.0, "status": "ABSENT", "reason_if_missing": "Analysis failed - re-run required", "suggestions_for_curation": "Re-run analysis with corrected prompt"},
            "taxa_level": {"level": "Unknown", "confidence": 0.0, "status": "ABSENT", "reason_if_missing": "Analysis failed - re-run required", "suggestions_for_curation": "Re-run analysis with corrected prompt"},
            "sample_size": {"size": "Unknown", "confidence": 0.0, "status": "ABSENT", "reason_if_missing": "Analysis failed - re-run required", "suggestions_for_curation": "Re-run analysis with corrected prompt"},
            "missing_fields": ["host_species", "body_site", "condition", "sequencing_type", "taxa_level", "sample_size"],
            "curation_preparation_summary": "Analysis failed - re-run required"
        }

    def _calculate_enhanced_confidence(self, validated_json: Dict) -> float:
        try:
            confidence_scores = []
            for field_name, field_data in validated_json.items():
                if field_name in ["missing_fields", "curation_preparation_summary"]:
                    continue
                if not isinstance(field_data, dict):
                    continue
                status = field_data.get("status", "ABSENT")
                field_confidence = field_data.get("confidence", 0.0)
                if status == "PRESENT":
                    content_key = self._get_content_key_for_field(field_name)
                    content_value = field_data.get(content_key, "")
                    if content_value and content_value.lower() not in ["unknown", "not specified", ""]:
                        confidence_scores.append(min(1.0, field_confidence + 0.1))
                    else:
                        confidence_scores.append(field_confidence)
                elif status == "PARTIALLY_PRESENT":
                    confidence_scores.append(field_confidence)
                else:
                    confidence_scores.append(0.0)
            
            if not confidence_scores:
                return 0.0
            weighted_scores = [score * 1.2 if score >= 0.8 else score for score in confidence_scores]
            final_confidence = sum(weighted_scores) / len(weighted_scores)
            return min(1.0, final_confidence)
        except Exception as e:
            logger.warning(f"Error calculating enhanced confidence: {str(e)}")
            return 0.5

    def _get_content_key_for_field(self, field_name: str) -> str:
        content_keys = {
            "host_species": "primary",
            "body_site": "site",
            "condition": "description",
            "sequencing_type": "method",
            "taxa_level": "level",
            "sample_size": "size"
        }
        return content_keys.get(field_name, "value")

    def _generate_curation_summary(self, parsed_json: Dict, missing_fields: List[str]) -> str:
        if not missing_fields:
            return "All required fields are present. Paper is ready for curation."
        if len(missing_fields) == 1:
            return f"Missing 1 field: {missing_fields[0]}. Review paper for this information."
        elif len(missing_fields) <= 3:
            return f"Missing {len(missing_fields)} fields: {', '.join(missing_fields)}. Paper needs additional review."
        else:
            return f"Missing {len(missing_fields)} fields: {', '.join(missing_fields)}. Paper requires significant review before curation."

    async def chat(self, prompt: str) -> dict:
        try:
            chat_prompt = (
                "You are a helpful scientific assistant. Answer the user's question or message conversationally. "
                "If the user provides a paper context, use it to inform your answer."
            )
            model = genai.GenerativeModel(self.model)
            response = await asyncio.wait_for(
                model.generate_content_async(
                    f"{chat_prompt}\nUser: {prompt}",
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.3,
                        max_output_tokens=300,
                        top_p=0.9,
                        top_k=40
                    ),
                    safety_settings=[
                        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
                        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
                        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
                        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"}
                    ]
                ),
                timeout=GEMINI_TIMEOUT
            )
            # Handle safety filter responses
            if response.candidates and response.candidates[0].finish_reason == 2:
                logger.warning("Response blocked by safety filters, using fallback")
                return {
                    "text": "I apologize, but I cannot process this request due to safety filters. Please try rephrasing your question.",
                    "confidence": 0.0
                }
            
            reply = response.text.strip() if response.text else "No response generated"
            confidence = 1.0 if reply else 0.0
            return {
                "text": reply,
                "confidence": confidence
            }
        except asyncio.TimeoutError:
            logger.error(f"Chat request timed out after {GEMINI_TIMEOUT} seconds")
            return {"text": f"[Error: Request timed out after {GEMINI_TIMEOUT} seconds]", "confidence": 0.0}
        except Exception as e:
            logger.error(f"Model API error in chat: {str(e)}")
            return {
                "text": f"[Error: {str(e)}]",
                "confidence": 0.0
            }