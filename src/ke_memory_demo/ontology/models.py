from __future__ import annotations

from typing import Annotated, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from ke_memory_demo.domain import OntologyRole
from ke_memory_demo.settings import (
    AppSettings,
    ElasticsearchFields,
    ElasticsearchRoles,
)


NonEmptyString = Annotated[str, Field(min_length=1)]
PositiveFloat = Annotated[float, Field(gt=0, allow_inf_nan=False)]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class OntologyError(RuntimeError):
    """Base error for local ontology adapter contract failures."""


class OntologyAuthenticationError(OntologyError):
    """Elasticsearch rejected the configured credentials."""


class OntologyUnavailableError(OntologyError):
    """Elasticsearch could not provide a usable response."""


class OntologyNotFoundError(OntologyError):
    """A required Elasticsearch index or document does not exist."""


class OntologySchemaError(OntologyError):
    """Elasticsearch data does not satisfy the vocabulary schema."""


class OntologyDriftError(OntologyError):
    """The pinned Elasticsearch index identity changed."""


class _OntologyModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ElasticsearchConnection(_OntologyModel):
    endpoint: NonEmptyString
    index: NonEmptyString
    api_key: SecretStr = Field(repr=False, exclude=True)
    timeout_seconds: PositiveFloat
    fields: ElasticsearchFields
    roles: ElasticsearchRoles

    @field_validator("endpoint")
    @classmethod
    def _validate_endpoint(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
            hostname = parsed.hostname
            port = parsed.port
        except ValueError as exc:
            raise ValueError("endpoint must be a valid HTTP(S) URL") from exc
        if parsed.scheme not in {"http", "https"} or hostname is None:
            raise ValueError("endpoint must be a valid HTTP(S) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("endpoint must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("endpoint must not contain a query or fragment")
        netloc = hostname
        if ":" in hostname and not hostname.startswith("["):
            netloc = f"[{hostname}]"
        if port is not None:
            netloc = f"{netloc}:{port}"
        path = parsed.path.rstrip("/")
        return urlunsplit((parsed.scheme, netloc, path, "", ""))

    @field_validator("index")
    @classmethod
    def _validate_index(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("index must not be empty")
        if value == "_all" or any(character in value for character in (",", "*", "?", "/", "\\")):
            raise ValueError("index must be one concrete non-wildcard name")
        if value in {".", ".."} or any(ord(character) < 32 for character in value):
            raise ValueError("index must not contain path traversal or control characters")
        return value

    @model_validator(mode="after")
    def _validate_role_mapping(self) -> ElasticsearchConnection:
        assignments = (
            (OntologyRole.CONCEPT, self.roles.concept),
            (OntologyRole.INDIVIDUAL, self.roles.individual),
            (OntologyRole.OPERATOR, self.roles.operator),
        )
        seen: dict[str, OntologyRole] = {}
        for role, source_types in assignments:
            for source_type in source_types:
                previous = seen.get(source_type)
                if previous is not None:
                    raise ValueError(
                        f"source type {source_type!r} is assigned to both "
                        f"{previous.value} and {role.value}"
                    )
                seen[source_type] = role
        return self

    @classmethod
    def from_app_settings(cls, settings: AppSettings) -> ElasticsearchConnection:
        endpoint, index, api_key = settings.require_es_connection()
        return cls(
            endpoint=endpoint,
            index=index,
            api_key=SecretStr(api_key),
            timeout_seconds=settings.es.request_timeout_seconds,
            fields=settings.es.fields,
            roles=settings.es.roles,
        )


class OntologyHealth(_OntologyModel):
    cluster_name: NonEmptyString
    status: Literal["green", "yellow", "red"]
    timed_out: bool


class IndexIdentity(_OntologyModel):
    index_name: NonEmptyString
    index_uuid: NonEmptyString
    mapping_sha256: Sha256Hex


class OntologyRelation(_OntologyModel):
    source_document_id: NonEmptyString
    relation_type: NonEmptyString
    target_id: NonEmptyString


class OntologyTerm(_OntologyModel):
    document_id: NonEmptyString
    canonical_term: NonEmptyString
    source_type: NonEmptyString
    role: OntologyRole | None
    aliases: tuple[NonEmptyString, ...] = ()
    relations: tuple[OntologyRelation, ...] = ()

    @model_validator(mode="after")
    def _validate_relations(self) -> OntologyTerm:
        keys = [(relation.relation_type, relation.target_id) for relation in self.relations]
        if len(keys) != len(set(keys)):
            raise ValueError("ontology term contains duplicate relations")
        return self
