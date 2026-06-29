from app.normalization.body_site import normalize_body_site
from app.normalization.condition import normalize_condition
from app.normalization.host_species import normalize_host_species
from app.normalization.ols import format_ontology_id
from app.normalization.sample_size import normalize_sample_size
from app.normalization.sequencing_type import normalize_sequencing_type
from app.normalization.taxa_level import normalize_taxa_level


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

    # Unmatched text falls back to the "other" vocab value (status PRESENT,
    # not PARTIALLY_PRESENT — it was found, just not classifiable), and the
    # original wording is preserved on .raw for the "Sequencing Type Raw"
    # side column.
    t = normalize_sequencing_type("new custom chemistry")
    assert t.label == "other"
    assert t.status == "PRESENT"
    assert t.raw == "new custom chemistry"

    # A matched phrase still preserves .raw, but callers should treat the
    # column as unnecessary when raw == normalized value.
    t = normalize_sequencing_type("16S rRNA gene sequencing")
    assert t.label == "16S"
    assert t.raw == "16S rRNA gene sequencing"


def test_taxa_level_normalization_variants():
    t = normalize_taxa_level("genus level analysis")
    assert t.label == "genus"
    assert t.status == "PRESENT"
    assert t.ontology_id == ""

    t = normalize_taxa_level("operational taxonomic units")
    assert t.label == "OTU"
    assert t.status == "PRESENT"

    t = normalize_taxa_level("amplicon sequence variants")
    assert t.label == "ASV"

    t = normalize_taxa_level("species and genus")
    assert t.status == "PARTIALLY_PRESENT"

    t = normalize_taxa_level("")
    assert t.status == "ABSENT"


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


def test_sample_size_ambiguous_multi_number_resolution():
    # Rule (see _resolve_ambiguous_count docstring): the first number
    # immediately followed by a sample-related noun wins, in reading order.
    t = normalize_sample_size("98 cases and 45 controls")
    assert t.label == "98"
    assert t.status == "PRESENT"

    # An explicit "total of N" overrides the per-cohort numbers.
    t = normalize_sample_size(
        "98 cases and 45 controls were included, for a total of 143 participants"
    )
    assert t.label == "143"

    # A leading year must not be mistaken for the sample size.
    t = normalize_sample_size("In 2019, 65 volunteers were enrolled")
    assert t.label == "65"

    # A percentage mentioned alongside the real count must not be picked up.
    t = normalize_sample_size("A total of 120 participants (60% female) were recruited")
    assert t.label == "120"

    # No anchored noun and no "total of" — falls back to the first number,
    # but a bare year-shaped number is excluded as a likely false positive.
    t = normalize_sample_size("Collected in 2020")
    assert t.status == "PARTIALLY_PRESENT"
