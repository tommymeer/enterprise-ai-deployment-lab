"""Small, fixed retailer dataset used by the interactive support demo."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Mapping

from .domain import CarrierEvidenceSnapshot, MatchStatus, OrderReference, RetrievalStatus, ShipmentReference

_RETRIEVED_AT = datetime(2026, 8, 31, 14, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class SyntheticRetailerRecord:
    customer_order_id: str
    customer_id: str
    order: OrderReference
    shipment: ShipmentReference
    carrier_evidence: CarrierEvidenceSnapshot | None
    refund_amount_minor: int


def _record(customer_order_id: str, suffix: str, order_value: str, item_category: str,
            carrier: str, tracking_id: str, *, evidence: bool = True,
            picture_proof: bool = True, refund_amount_minor: int = 5_000) -> SyntheticRetailerRecord:
    order_id, shipment_id = f"retailer-order-{suffix}", f"retailer-shipment-{suffix}"
    shipment = ShipmentReference(shipment_id, carrier, tracking_id, _RETRIEVED_AT,
        _RETRIEVED_AT, RetrievalStatus.SUCCESS)
    snapshot = None if not evidence else CarrierEvidenceSnapshot(
        f"carrier-evidence-{suffix}", shipment_id, "delivered", _RETRIEVED_AT,
        ("out_for_delivery", "delivered"), picture_proof, _RETRIEVED_AT, RetrievalStatus.SUCCESS)
    return SyntheticRetailerRecord(customer_order_id, f"customer-{suffix}",
        OrderReference(order_id, MatchStatus.MATCHED, order_value, item_category,
            "42 Synthetic Market St", _RETRIEVED_AT, RetrievalStatus.SUCCESS),
        shipment, snapshot, refund_amount_minor)


_RECORDS = (
    _record("12345", "1001", "50.00 USD", "home_goods", "Parcel North", "PN-84001"),
    _record("24680", "1002", "42.00 USD", "apparel", "SwiftShip", "SS-24680", picture_proof=False, refund_amount_minor=4_200),
    _record("31415", "1003", "36.00 USD", "books", "Parcel North", "PN-31415", evidence=False, refund_amount_minor=3_600),
    _record("27182", "1004", "150.00 USD", "small_electronics", "SwiftShip", "SS-27182", refund_amount_minor=15_000),
)

SYNTHETIC_RETAILER_ORDERS: Mapping[str, SyntheticRetailerRecord] = MappingProxyType(
    {record.customer_order_id: record for record in _RECORDS})


def find_synthetic_order(customer_order_id: str) -> SyntheticRetailerRecord | None:
    return SYNTHETIC_RETAILER_ORDERS.get(customer_order_id)


def not_found_order(customer_order_id: str) -> OrderReference:
    return OrderReference(customer_order_id, MatchStatus.NOT_FOUND, None, None, None,
        _RETRIEVED_AT, RetrievalStatus.SUCCESS)


@dataclass(frozen=True, slots=True)
class SyntheticRetailerOrderLookup:
    def __call__(self, customer_order_id: str) -> OrderReference:
        record = find_synthetic_order(customer_order_id)
        return record.order if record else not_found_order(customer_order_id)


@dataclass(frozen=True, slots=True)
class SyntheticRetailerShipmentLookup:
    def __call__(self, shipment_id: str) -> ShipmentReference:
        return next(record.shipment for record in _RECORDS if record.shipment.ref_id == shipment_id)


@dataclass(frozen=True, slots=True)
class SyntheticRetailerCarrierEvidenceLookup:
    def __call__(self, shipment: ShipmentReference) -> CarrierEvidenceSnapshot | None:
        record = next(record for record in _RECORDS if record.shipment.ref_id == shipment.ref_id)
        return record.carrier_evidence
