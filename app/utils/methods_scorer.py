"""
Methods scoring utility for BugSigDB Analyzer.
Provides quantitative assessment of experimental and analytical methods quality.
"""

import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

@dataclass
class MethodsScore:
    """Structured methods score with detailed breakdown."""
    overall_score: float
    experimental_design: float
    sequencing_methods: float
    analytical_methods: float
    statistical_methods: float
    data_quality: float
    reproducibility: float
    details: Dict[str, List[str]]

class MethodsScorer:
    """Scores papers based on the quality and comprehensiveness of their methods."""
    
    def __init__(self):
        # Define scoring criteria
        self.experimental_criteria = {
            'randomization': ['randomized', 'random', 'randomly assigned'],
            'blinding': ['blinded', 'blind', 'double-blind', 'single-blind'],
            'controls': ['control group', 'control', 'placebo', 'sham'],
            'sample_size': ['power analysis', 'sample size calculation', 'statistical power'],
            'replication': ['replicate', 'replication', 'technical replicate', 'biological replicate']
        }
        
        self.sequencing_criteria = {
            'dna_extraction': ['dna extraction', 'dna isolation', 'genomic dna'],
            'library_prep': ['library preparation', 'library prep', 'adapter ligation'],
            'sequencing_platform': ['illumina', 'pacbio', 'oxford nanopore', 'ion torrent'],
            'quality_control': ['quality control', 'quality filtering', 'qc'],
            'chimera_removal': ['chimera', 'uchime', 'vsearch']
        }
        
        self.analytical_criteria = {
            'diversity_analysis': ['alpha diversity', 'beta diversity', 'shannon', 'simpson'],
            'differential_abundance': ['deseq2', 'edgeR', 'lefse', 'metastats', 'maaslin'],
            'ordination': ['pca', 'pcoa', 'nmds', 'ordination'],
            'machine_learning': ['random forest', 'svm', 'neural network', 'clustering'],
            'network_analysis': ['co-occurrence', 'correlation network', 'network analysis']
        }
        
        self.statistical_criteria = {
            'parametric_tests': ['t-test', 'anova', 'paired t-test'],
            'nonparametric_tests': ['wilcoxon', 'mann-whitney', 'kruskal-wallis'],
            'correlation': ['pearson', 'spearman', 'correlation'],
            'multiple_testing': ['fdr', 'bonferroni', 'benjamini-hochberg'],
            'effect_size': ['cohen\'s d', 'odds ratio', 'relative risk']
        }
        
        self.data_quality_criteria = {
            'data_availability': ['sra', 'ena', 'genbank', 'accession'],
            'code_availability': ['github', 'code repository', 'script'],
            'reproducibility': ['container', 'docker', 'conda', 'environment'],
            'metadata': ['sample metadata', 'clinical data', 'phenotype data']
        }
    
    def score_paper(self, text: str) -> MethodsScore:
        """Score a paper based on its methods description."""
        text_lower = text.lower()
        
        # Score each category
        experimental_score = self._score_category(text_lower, self.experimental_criteria)
        sequencing_score = self._score_category(text_lower, self.sequencing_criteria)
        analytical_score = self._score_category(text_lower, self.analytical_criteria)
        statistical_score = self._score_category(text_lower, self.statistical_criteria)
        data_quality_score = self._score_category(text_lower, self.data_quality_criteria)
        
        # Calculate overall score (weighted average)
        weights = {
            'experimental': 0.25,
            'sequencing': 0.25,
            'analytical': 0.20,
            'statistical': 0.15,
            'data_quality': 0.15
        }
        
        overall_score = (
            experimental_score[0] * weights['experimental'] +
            sequencing_score[0] * weights['sequencing'] +
            analytical_score[0] * weights['analytical'] +
            statistical_score[0] * weights['statistical'] +
            data_quality_score[0] * weights['data_quality']
        )
        
        # Compile details
        details = {
            'experimental_design': experimental_score[1],
            'sequencing_methods': sequencing_score[1],
            'analytical_methods': analytical_score[1],
            'statistical_methods': statistical_score[1],
            'data_quality': data_quality_score[1]
        }
        
        return MethodsScore(
            overall_score=overall_score,
            experimental_design=experimental_score[0],
            sequencing_methods=sequencing_score[0],
            analytical_methods=analytical_score[0],
            statistical_methods=statistical_score[0],
            data_quality=data_quality_score[0],
            reproducibility=data_quality_score[0],  # Use data quality as proxy
            details=details
        )
    
    def _score_category(self, text: str, criteria: Dict[str, List[str]]) -> Tuple[float, List[str]]:
        """Score a specific category based on criteria."""
        found_methods = []
        total_criteria = 0
        
        for category, keywords in criteria.items():
            total_criteria += 1
            for keyword in keywords:
                if keyword in text:
                    found_methods.append(f"{category}: {keyword}")
                    break  # Only count once per category
        
        score = len(found_methods) / total_criteria if total_criteria > 0 else 0.0
        return score, found_methods
    
    def get_methods_summary(self, score: MethodsScore) -> str:
        """Generate a human-readable summary of methods quality."""
        summary_parts = []
        
        if score.overall_score >= 0.8:
            summary_parts.append("Excellent methods quality")
        elif score.overall_score >= 0.6:
            summary_parts.append("Good methods quality")
        elif score.overall_score >= 0.4:
            summary_parts.append("Moderate methods quality")
        else:
            summary_parts.append("Limited methods description")
        
        # Add specific strengths
        strengths = []
        if score.experimental_design >= 0.6:
            strengths.append("strong experimental design")
        if score.sequencing_methods >= 0.6:
            strengths.append("comprehensive sequencing methods")
        if score.analytical_methods >= 0.6:
            strengths.append("robust analytical approaches")
        if score.statistical_methods >= 0.6:
            strengths.append("appropriate statistical methods")
        if score.data_quality >= 0.6:
            strengths.append("good data quality practices")
        
        if strengths:
            summary_parts.append(f"with {', '.join(strengths)}")
        
        return " ".join(summary_parts)
    
    def get_improvement_suggestions(self, score: MethodsScore) -> List[str]:
        """Generate suggestions for improving methods quality."""
        suggestions = []
        
        if score.experimental_design < 0.5:
            suggestions.append("Consider adding randomization and blinding procedures")
        
        if score.sequencing_methods < 0.5:
            suggestions.append("Include detailed sequencing protocols and quality control measures")
        
        if score.analytical_methods < 0.5:
            suggestions.append("Describe bioinformatics pipeline and analytical methods in detail")
        
        if score.statistical_methods < 0.5:
            suggestions.append("Specify statistical tests and multiple testing corrections")
        
        if score.data_quality < 0.5:
            suggestions.append("Provide data availability and code reproducibility information")
        
        return suggestions 