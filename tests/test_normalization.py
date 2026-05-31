from app.normalization.body_site import normalize_body_site
from app.normalization.condition import normalize_condition
from app.normalization.host_species import normalize_host_species
from app.normalization.ols import format_ontology_id
from app.normalization.sample_size import normalize_sample_size
from app.normalization.sequencing_type import normalize_sequencing_type


def test_format_ontology_id():
    assert format_ontology_id("EFO_0002508", "EFO") == "EFO:0002508"
    assert format_ontology_id("UBERON_0001988", "UBERON") == "UBERON:0001988"
    assert format_ontology_id("EFO:0002508", "EFO") == "EFO:0002508"


def test_host_species_normalization_variants():
    t = normalize_host_species("humans")
    assert t.label == "Homo sapiens"
    assert t.ontology_id == "NCBITaxon:9606"
    assert t.status == "PRESENT"
    assert t.mapping_confidence == 1.0

    t = normalize_host_species("mice model")
    assert t.label == "Mus musculus"
    assert t.ontology_id == "NCBITaxon:10090"

    t = normalize_host_species("rats")
    assert t.label == "Rattus norvegicus"
    assert t.ontology_id == "NCBITaxon:10116"

    t = normalize_host_species("dogs")
    assert t.label == "Canis lupus familiaris"
    assert t.ontology_id == "NCBITaxon:9615"

    t = normalize_host_species("")
    assert t.status == "ABSENT"
    assert t.ontology_id == ""

    t = normalize_host_species("mice and rats")
    assert t.status == "PARTIALLY_PRESENT"
    assert t.ontology_id != ""


def test_body_site_normalization_variants():
    t = normalize_body_site("stool samples")
    assert t.label == "feces"
    assert t.ontology_id == "UBERON:0001988"
    assert t.status == "PRESENT"

    t = normalize_body_site("gut microbiome")
    assert t.label == "feces"
    assert t.ontology_id == "UBERON:0001988"

    t = normalize_body_site("salivary swab")
    assert t.label == "saliva"
    assert t.ontology_id == "UBERON:0001836"

    t = normalize_body_site("nasal cavity swab")
    assert t.label == "nasal cavity"

    t = normalize_body_site("blood plasma")
    assert t.label == "blood"
    assert t.ontology_id == "UBERON:0000178"

    t = normalize_body_site("")
    assert t.status == "ABSENT"


def test_condition_normalization_variants():
    t = normalize_condition("Parkinson's disease patients")
    assert t.label == "Parkinson disease"
    assert t.ontology_id == "EFO:0002508"
    assert t.status == "PRESENT"

    t = normalize_condition("type 2 diabetes cohort")
    assert t.label == "type 2 diabetes mellitus"
    assert t.ontology_id == "EFO:0001360"

    t = normalize_condition("obese adults")
    assert t.label == "obesity"
    assert t.ontology_id == "EFO:0001073"

    t = normalize_condition("healthy controls")
    assert t.label == "healthy"
    assert t.status == "PRESENT"

    t = normalize_condition("COVID-19 cases")
    assert t.label == "COVID-19"
    assert t.ontology_id == "EFO:0003601"

    t = normalize_condition("")
    assert t.status == "ABSENT"


def test_sequencing_type_normalization_variants():
    t = normalize_sequencing_type("16S rRNA gene sequencing")
    assert t.label == "16S"
    assert t.status == "PRESENT"
    assert t.ontology_id == ""

    t = normalize_sequencing_type("whole metagenome shotgun sequencing")
    assert t.label == "shotgun"

    t = normalize_sequencing_type("shotgun metagenomics study")
    assert t.label == "metagenomics"
    assert t.status == "PRESENT"

    t = normalize_sequencing_type("ITS1 sequencing")
    assert t.label == "ITS"

    t = normalize_sequencing_type("RNA-seq metatranscriptomics")
    assert t.label == "RNA-seq"

    t = normalize_sequencing_type("")
    assert t.status == "ABSENT"

    t = normalize_sequencing_type("new custom chemistry")
    assert t.status == "PARTIALLY_PRESENT"


def test_sample_size_normalization_variants():
    t = normalize_sample_size(98)
    assert t.label == "98"
    assert t.status == "PRESENT"

    t = normalize_sample_size("1,200 participants")
    assert t.label == "1200"

    t = normalize_sample_size("ninety eight")
    assert t.label == "98"

    t = normalize_sample_size("about 65 volunteers")
    assert t.label == "65"

    t = normalize_sample_size(None)
    assert t.status == "ABSENT"

    t = normalize_sample_size("unknown sample count")
    assert t.status == "PARTIALLY_PRESENT"
