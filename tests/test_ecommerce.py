import json

import yaml
from langchain_core.messages import AIMessage

from universal_agent.tools.ecommerce import Catalog, OrderItem, quote, search

from .conftest import ROOT, tool_call

CATALOG = Catalog.model_validate(yaml.safe_load((ROOT / "agents" / "ecommerce-example" / "catalog.yaml").read_text()))


def tool_outputs(history):
    return [m["content"] for m in history if m["role"] == "tool"]


def test_search_ranks_by_terms() -> None:
    assert [p.sku for p in search(CATALOG, "camping tent")][0] == "TNT-2P"
    assert search(CATALOG, "zzz") == []


def test_quote_uses_catalog_prices_and_free_shipping() -> None:
    _, subtotal, shipping = quote(CATALOG, [OrderItem(sku="btl-1l", quantity=2)])
    assert (subtotal, shipping) == (59.8, 9.9)
    _, subtotal, shipping = quote(CATALOG, [OrderItem(sku="BKP-55", quantity=1), OrderItem(sku="BTL-1L", quantity=1)])
    assert (subtotal, shipping) == (178.9, 0.0)


def test_quote_rejects_unknown_and_out_of_stock() -> None:
    for items in ([OrderItem(sku="NOPE", quantity=1)], [OrderItem(sku="LMP-HD", quantity=1)], []):
        try:
            quote(CATALOG, items)
        except ValueError:
            continue
        raise AssertionError(f"accepted {items}")


ORDER = {
    "items": [{"sku": "BKP-30", "quantity": 1}],
    "customer_name": "Chris Example",
    "email": "Chris@Example.com",
    "shipping_address": "10 Sample Street, Exampleville",
}


async def test_create_order_after_approval(make_runtime, settings) -> None:
    rt = make_runtime([tool_call("create_order", ORDER), AIMessage(content="Order placed.")])
    pending = await rt.chat("ecommerce-example", "s1", "yes, place it")
    assert pending.status == "awaiting_approval"
    done = await rt.resume("ecommerce-example", "s1", approved=True)
    assert done.reply == "Order placed."
    out = tool_outputs(await rt.history("ecommerce-example", "s1"))[-1]
    assert "Total 99.80 USD (shipping 9.90)" in out
    orders = json.loads((settings.data_dir / "ecommerce-example-orders.json").read_text())
    assert orders[-1]["email"] == "chris@example.com" and orders[-1]["total"] == 99.8
    assert {o["id"] for o in orders} >= {"ORD-1001", "ORD-1002"}  # demo orders seeded


async def test_rejected_order_is_not_created(make_runtime, settings) -> None:
    rt = make_runtime([tool_call("create_order", ORDER), AIMessage(content="Not placed.")])
    await rt.chat("ecommerce-example", "s2", "place it")
    await rt.resume("ecommerce-example", "s2", approved=False)
    path = settings.data_dir / "ecommerce-example-orders.json"
    assert not path.exists() or all(o["customer_name"] != "Chris Example" for o in json.loads(path.read_text()))


async def test_order_status_requires_matching_email(make_runtime) -> None:
    rt = make_runtime(
        [
            tool_call("get_order_status", {"order_id": "ord-1001", "email": "alex@example.com"}),
            tool_call("get_order_status", {"order_id": "ORD-1001", "email": "mallory@example.com"}, "c2"),
            AIMessage(content="done"),
        ]
    )
    await rt.chat("ecommerce-example", "s3", "where is my order?")
    first, second = tool_outputs(await rt.history("ecommerce-example", "s3"))
    assert "status shipped" in first and "TRACK-0001-EXAMPLE" in first
    assert second.startswith("error: no order")


async def test_cancel_only_unshipped(make_runtime) -> None:
    rt = make_runtime(
        [
            tool_call("cancel_order", {"order_id": "ORD-1001", "email": "alex@example.com"}),
            AIMessage(content="Cannot cancel."),
            tool_call("cancel_order", {"order_id": "ORD-1002", "email": "sam@example.com"}, "c2"),
            AIMessage(content="Cancelled."),
        ]
    )
    await rt.chat("ecommerce-example", "s4", "cancel 1001")
    await rt.resume("ecommerce-example", "s4", approved=True)
    await rt.chat("ecommerce-example", "s4", "cancel 1002")
    await rt.resume("ecommerce-example", "s4", approved=True)
    shipped, processing = tool_outputs(await rt.history("ecommerce-example", "s4"))
    assert "can no longer be cancelled" in shipped
    assert processing.startswith("Order ORD-1002 cancelled")
