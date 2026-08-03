"""Parse Princeton WordNet 3.0 out of the database files, with no ``nltk`` dependency.

``nltk`` is not installed and installing into this venv is off-limits, so this reads the
``data.<pos>`` files directly. That is not a workaround so much as the simpler option: the
WordNet database format is a documented line format (see ``wndb(5)``), and the fields this
project needs -- synset id, lemma, gloss, hypernym -- are the first ones on the line.

Format of a data line, fields space-separated:

    offset lex_filenum ss_type w_cnt word lex_id [word lex_id...] p_cnt [ptr...] | gloss

``w_cnt`` and the pointer count are hexadecimal and decimal respectively, which is the one
genuinely surprising part of the format and the reason the two are parsed differently.
Lines beginning with two spaces are the copyright header, not data.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
import zipfile

from ke_memory_demo.ontology_sources.models import (
    SourceAcquisition,
    WordNetSnapshot,
    WordNetSynset,
)

# ss_type letters as they appear in the database. Adjective satellites ("s") live in
# data.adj and are folded into "a", matching WordNet's own convention.
_POS_FILES: dict[str, str] = {
    "n": "wordnet/data.noun",
    "v": "wordnet/data.verb",
    "a": "wordnet/data.adj",
    "r": "wordnet/data.adv",
}
_LEXNAMES = "wordnet/lexnames"
# "@" is hypernym, "@i" is instance hypernym; both are the is-a edge this project cares
# about, and the pointer symbol is the first field of a pointer group.
_HYPERNYM_SYMBOLS = frozenset({"@", "@i"})
_SAMPLE_PER_POS = 5


class WordNetParseError(ValueError):
    """A WordNet database file did not match the documented line format."""


def load_wordnet(archive: Path, acquisition: SourceAcquisition) -> WordNetSnapshot:
    """Parse every synset in the archive and return a compact, counted snapshot."""
    with zipfile.ZipFile(archive) as bundle:
        lexnames = _read_lexnames(bundle)
        counts: dict[str, int] = {}
        sample: list[WordNetSynset] = []
        for pos, member in sorted(_POS_FILES.items()):
            synsets = list(_parse_data_file(bundle.read(member), pos, lexnames))
            if not synsets:
                raise WordNetParseError(f"{member} yielded no synsets")
            counts[pos] = len(synsets)
            sample.extend(synsets[:_SAMPLE_PER_POS])

    return WordNetSnapshot(
        release="3.0",
        acquisition=acquisition,
        synset_count_by_pos=counts,
        lexname_count=len(lexnames),
        sample=tuple(sample),
    )


def _read_lexnames(bundle: zipfile.ZipFile) -> dict[int, str]:
    """Map lex_filenum to its semantic field name, e.g. 04 -> ``noun.act``."""
    text = bundle.read(_LEXNAMES).decode("utf-8", errors="replace")
    names: dict[int, str] = {}
    for line in text.splitlines():
        fields = line.split("\t")
        if len(fields) < 2:
            continue
        names[int(fields[0])] = fields[1].strip()
    if not names:
        raise WordNetParseError("lexnames file was empty")
    return names


def _parse_data_file(
    raw: bytes, pos: str, lexnames: dict[int, str]
) -> Iterator[WordNetSynset]:
    text = raw.decode("utf-8", errors="replace")
    for line in text.splitlines():
        # The licence header is the only non-data content and is indented by two spaces.
        if not line.strip() or line.startswith("  "):
            continue
        yield _parse_data_line(line, pos, lexnames)


def _parse_data_line(line: str, pos: str, lexnames: dict[int, str]) -> WordNetSynset:
    body, _, gloss = line.partition("|")
    fields = body.split()
    if len(fields) < 4:
        raise WordNetParseError(f"data line has too few fields: {line[:60]!r}")

    offset, lex_filenum, ss_type = fields[0], int(fields[1]), fields[2]
    word_count = int(fields[3], 16)
    cursor = 4
    words: list[str] = []
    for _ in range(word_count):
        # Each word is followed by a hexadecimal lex_id that is not needed downstream.
        words.append(fields[cursor])
        cursor += 2
    if not words:
        raise WordNetParseError(f"synset {offset} listed no words")

    pointer_count = int(fields[cursor])
    cursor += 1
    hypernyms: list[str] = []
    for _ in range(pointer_count):
        symbol, target, target_pos = fields[cursor], fields[cursor + 1], fields[cursor + 2]
        if symbol in _HYPERNYM_SYMBOLS:
            hypernyms.append(f"{target_pos}#{target}")
        cursor += 4

    return WordNetSynset(
        synset_id=f"{pos}#{offset}",
        offset=offset,
        # ss_type is retained rather than the file's pos so an adjective satellite stays
        # visible as "s" instead of being silently relabelled.
        pos=ss_type,
        lexname=lexnames.get(lex_filenum, f"lexnum.{lex_filenum:02d}"),
        words=tuple(words),
        gloss=gloss.strip(),
        hypernyms=tuple(hypernyms),
    )
