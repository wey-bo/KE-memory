from ke_memory_demo.online.keol_bridge import KEOLBundleCompiler as LegacyKEOLBundleCompiler
from ke_memory_demo.ontology import ElasticsearchVocabulary as LegacyElasticsearchVocabulary
from ke_memory_ontology import (
    ElasticsearchVocabulary,
    KEOLBundleCompiler,
    OntologyVocabulary,
)


def test_new_ontology_package_owns_vocabulary_and_keol_projection() -> None:
    assert ElasticsearchVocabulary is LegacyElasticsearchVocabulary
    assert KEOLBundleCompiler is LegacyKEOLBundleCompiler
    assert OntologyVocabulary

