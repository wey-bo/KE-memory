"""The canonical literal value contract.

Numbers are carried as strings on purpose. A JSON number would be read back through a
float somewhere and `0.1 + 0.2` would stop being the value that was written, which for
money and measured quantities is a correctness question rather than a formatting one.
The patterns therefore fix a single canonical spelling, so equal values have equal
bytes and can be hashed.

`MoneyValue.amount` and `QuantityValue.value` deliberately do not share a field name:
the shipped vectors include `{"amount": "3", "unit": "kg"}` as *invalid*, because a
quantity spelled like money is the confusion the distinct names prevent.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr

MONEY_AMOUNT_PATTERN = r"^(?:0|-?[1-9][0-9]*)(?:\.[0-9]+)?$"
CURRENCY_PATTERN = r"^[A-Z]{3}$"
QUANTITY_VALUE_PATTERN = r"^(?:0|-?(?:(?:[1-9][0-9]*)(?:\.[0-9]*[1-9])?|0\.[0-9]*[1-9]))$"


class _LiteralRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MoneyValue(_LiteralRecord):
    """An amount with an ISO 4217 currency.

    The amount pattern permits trailing zeros (`"1.50"`), because in money they are
    significant: a price quoted to the cent is not the same statement as one quoted to
    the unit.
    """

    amount: Annotated[str, Field(pattern=MONEY_AMOUNT_PATTERN)]
    currency: Annotated[str, Field(pattern=CURRENCY_PATTERN)]


class QuantityValue(_LiteralRecord):
    """A magnitude with a unit.

    Unlike money, the pattern forbids trailing zeros, so one magnitude has exactly one
    spelling and `"3"` cannot also arrive as `"3.0"`. The unit is any non-empty string:
    this layer does not own a unit vocabulary, and inventing one here would put a second
    authority beside the ontology.
    """

    value: Annotated[str, Field(pattern=QUANTITY_VALUE_PATTERN)]
    unit: Annotated[str, Field(min_length=1)]


CanonicalLiteralValue = StrictBool | StrictStr | MoneyValue | QuantityValue
"""The four literal shapes a `typed_value` may carry.

`None` is absent by construction: the contract forbids a null `canonical_value`, and a
type that cannot express it needs no runtime check.

Strict scalars matter here. With plain `bool | str`, pydantic's union coercion accepts
`True` as the string `"True"`, which would make the boolean and string branches
indistinguishable and silently rewrite the value being asserted.
"""
