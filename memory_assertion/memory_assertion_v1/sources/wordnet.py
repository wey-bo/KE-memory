"""WordNet 3.0 sense records, read from `index.sense`.

Each line is `sense_key synset_offset sense_number tag_cnt`, and the sense key is taken
verbatim. That is the whole point: keys look like `'hood%1:15:00::`, `.22%1:06:00::` and
`s_gravenhage%1:15:00::`, so 1,390 of them contain leading dots, apostrophes or slashes.
Any pattern this module invented for `lemma.pos.sense` would reject real senses, and
WordNet already publishes an authoritative identity -- there is nothing to improve on.

The lemma is recovered by splitting on the first `%`, which is safe because the sense key
grammar reserves `%` as the lemma terminator.
"""

from __future__ import annotations

import zipfile
from collections.abc import Iterator
from pathlib import Path

from memory_assertion_v1.sources.records import SourceLocation, WordNetSenseRecord

INDEX_SENSE_MEMBER = "wordnet/index.sense"


class WordNetParseError(ValueError):
    """A line in `index.sense` does not have the documented shape."""


def parse_index_sense_line(line: str, location: SourceLocation) -> WordNetSenseRecord:
    """Parse one `index.sense` line.

    Raises rather than skipping: a malformed line in a frozen corpus means the artifact is
    not the artifact it claims to be, and silently dropping it would let a truncated
    download pass as a smaller vocabulary.
    """
    fields = line.split()
    if len(fields) < 3:
        raise WordNetParseError(f"expected at least 3 fields, got {len(fields)}: {line!r}")
    sense_key, synset_offset, sense_number = fields[0], fields[1], fields[2]
    lemma, separator, _ = sense_key.partition("%")
    if not separator or not lemma:
        raise WordNetParseError(f"sense key has no lemma terminator: {sense_key!r}")
    if not sense_number.isdigit() or int(sense_number) < 1:
        raise WordNetParseError(f"sense number is not a positive integer: {sense_number!r}")
    return WordNetSenseRecord(
        location=location,
        sense_key=sense_key,
        lemma=lemma,
        synset_offset=synset_offset,
        sense_number=int(sense_number),
    )


def iter_sense_records(
    archive: Path, artifact_sha256: str, *, member: str = INDEX_SENSE_MEMBER
) -> Iterator[WordNetSenseRecord]:
    """Stream every sense in the archive.

    A generator because `index.sense` holds 206,941 lines: a caller counting senses or
    filtering to a handful of lemmas should not have to hold them all.
    """
    location = SourceLocation(artifact_sha256=artifact_sha256, member_path=member)
    with zipfile.ZipFile(archive) as bundle, bundle.open(member) as stream:
        for raw in stream:
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            yield parse_index_sense_line(line, location)
