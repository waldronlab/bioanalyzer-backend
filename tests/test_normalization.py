from app.normalization.body_site import normalize_body_site
from app.normalization.condition import normalize_condition
from app.normalization.host_species import normalize_host_species
from app.normalization.sample_size import normalize_sample_size
from app.normalization.sequencing_type import normalize_sequencing_type


def test_host_species_normalization_variants():
    assert normalize_host_species("humans") == ("Homo sapiens", "PRESENT")
    assert normalize_host_species("mice model") == ("Mus musculus", "PRESENT")
    assert normalize_host_species("rats") == ("Rattus norvegicus", "PRESENT")
    assert normalize_host_species("dogs") == ("Canis lupus familiaris", "PRESENT")
    assert normalize_host_species("") == ("", "ABSENT")
    assert normalize_host_species("mice and rats")[1] == "PARTIALLY_PRESENT"


def test_body_site_normalization_variants():
    assert normalize_body_site("stool samples") == ("feces", "PRESENT")
    assert normalize_body_site("gut microbiome") == ("feces", "PRESENT")
    assert normalize_body_site("salivary swab") == ("saliva", "PRESENT")
    assert normalize_body_site("nasal cavity swab") == ("nasal cavity", "PRESENT")
    assert normalize_body_site("blood plasma")[0] == "blood"
    assert normalize_body_site("") == ("", "ABSENT")


def test_condition_normalization_variants():
    assert normalize_condition("Parkinson's disease patients") == (
        "Parkinson disease",
        "PRESENT",
    )
    assert normalize_condition("type 2 diabetes cohort") == (
        "type 2 diabetes mellitus",
        "PRESENT",
    )
    assert normalize_condition("obese adults") == ("obesity", "PRESENT")
    assert normalize_condition("healthy controls") == ("healthy", "PRESENT")
    assert normalize_condition("COVID-19 cases") == ("COVID-19", "PRESENT")
    assert normalize_condition("") == ("", "ABSENT")


def test_sequencing_type_normalization_variants():
    assert normalize_sequencing_type("16S rRNA gene sequencing") == ("16S", "PRESENT")
    assert normalize_sequencing_type("whole metagenome shotgun sequencing") == (
        "shotgun",
        "PRESENT",
    )
    assert normalize_sequencing_type("ITS1 sequencing") == ("ITS", "PRESENT")
    assert normalize_sequencing_type("RNA-seq metatranscriptomics") == (
        "RNA-seq",
        "PRESENT",
    )
    assert normalize_sequencing_type("") == ("", "ABSENT")
    assert normalize_sequencing_type("new custom chemistry")[1] == "PARTIALLY_PRESENT"


def test_sample_size_normalization_variants():
    assert normalize_sample_size(98) == ("98", "PRESENT")
    assert normalize_sample_size("1,200 participants") == ("1200", "PRESENT")
    assert normalize_sample_size("ninety eight") == ("98", "PRESENT")
    assert normalize_sample_size("about 65 volunteers") == ("65", "PRESENT")
    assert normalize_sample_size(None) == ("", "ABSENT")
    assert normalize_sample_size("unknown sample count")[1] == "PARTIALLY_PRESENT"
