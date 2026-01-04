"""Shared constants for API routers."""

ESSENTIAL_FIELDS_INFO = {
    "host_species": {
        "name": "Host Species",
        "description": "The host organism being studied (e.g., Human, Mouse, Rat)",
        "required": True,
    },
    "body_site": {
        "name": "Body Site",
        "description": "Where the microbiome sample was collected (e.g., Gut, Oral, Skin)",
        "required": True,
    },
    "condition": {
        "name": "Condition",
        "description": "What disease, treatment, or exposure is being studied",
        "required": True,
    },
    "sequencing_type": {
        "name": "Sequencing Type",
        "description": "What molecular method was used (e.g., 16S, metagenomics)",
        "required": True,
    },
    "taxa_level": {
        "name": "Taxa Level",
        "description": "What taxonomic level was analyzed (e.g., phylum, genus, species)",
        "required": True,
    },
    "sample_size": {
        "name": "Sample Size",
        "description": "Number of samples or participants analyzed",
        "required": True,
    },
}

STATUS_VALUES = {
    "PRESENT": "Information is complete and clear",
    "PARTIALLY_PRESENT": "Some information available but incomplete",
    "ABSENT": "Information is missing",
}
