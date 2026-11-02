"""E-commerce tools used by ``agents/ecommerce-example``.

The catalog is ``agents/<agent>/catalog.yaml``; orders are stored in ``DATA_DIR/<agent>-orders.json`` (a stand-in for
your store's database or API). Replace ``OrderStore`` and ``load_catalog`` with calls to your platform; keep the
tool signatures and risk levels.

Safety properties:

* Prices, stock and totals are computed from the catalog, never taken from the model.
* Creating and cancelling orders are ``write`` tools and wait for human approval.
* Order lookups and cancellations require the e-mail used on the order.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from .registry import ToolContext, register_tool

_WORD = re.compile(r"\w+", re.UNICODE)
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CANCELLABLE = {"placed", "processing"}


class Product(BaseModel):
    sku: str
    name: str
    price: float = Field(ge=0)
    stock: int = Field(ge=0)
    description: str = ""
    tags: list[str] = []


class Catalog(BaseModel):
    currency: str = "USD"
    shipping_flat: float = Field(default=0, ge=0)
    free_shipping_over: float | None = None
    products: list[Product]

    def get(self, sku: str) -> Product | None:
        return next((p for p in self.products if p.sku.lower() == sku.strip().lower()), None)


class OrderItem(BaseModel):
    sku: str = Field(description="Product SKU from search_products")
    quantity: int = Field(ge=1, le=20)


def load_catalog(agent_dir: Path) -> Catalog:
    return Catalog.model_validate(yaml.safe_load((agent_dir / "catalog.yaml").read_text(encoding="utf-8")))


def search(catalog: Catalog, query: str, limit: int = 5) -> list[Product]:
    terms = {t.lower() for t in _WORD.findall(query) if len(t) > 1}
    scored = []
    for product in catalog.products:
        words = {w.lower() for w in _WORD.findall(f"{product.sku} {product.name} {product.description} {' '.join(product.tags)}")}
        score = len(terms & words)
        if score:
            scored.append((score, product))
    scored.sort(key=lambda pair: -pair[0])
    return [p for _, p in scored[:limit]]


class OrderStore:
    """JSON-file order store. Seeds demo orders from ``demo_orders.yaml`` on first use."""

    def __init__(self, path: Path, seed: Path | None = None) -> None:
        self.path = path
        self.seed = seed
        self._lock = threading.Lock()

    def all(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            orders = yaml.safe_load(self.seed.read_text(encoding="utf-8")) if self.seed and self.seed.is_file() else []
            self._write(orders or [])
        data: list[dict[str, Any]] = json.loads(self.path.read_text(encoding="utf-8"))
        return data

    def _write(self, orders: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(orders, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        tmp.replace(self.path)

    def find(self, order_id: str, email: str) -> dict[str, Any] | None:
        return next((o for o in self.all() if o["id"] == order_id.strip().upper() and o["email"] == email), None)

    def add(self, order: dict[str, Any]) -> None:
        with self._lock:
            self._write([*self.all(), order])

    def set_status(self, order_id: str, status: str) -> None:
        with self._lock:
            orders = self.all()
            for order in orders:
                if order["id"] == order_id:
                    order["status"] = status
            self._write(orders)


def _email(value: str) -> str:
    email = value.strip().lower()
    if not _EMAIL.match(email):
        raise ValueError("invalid e-mail")
    return email


def _store(ctx: ToolContext) -> OrderStore:
    return OrderStore(ctx.settings.data_dir / f"{ctx.agent_name}-orders.json", ctx.agent_dir / "demo_orders.yaml")


def quote(catalog: Catalog, items: list[OrderItem]) -> tuple[list[dict[str, Any]], float, float]:
    """Validate items against the catalog. Returns (lines, subtotal, shipping). Raises ValueError."""
    if not items:
        raise ValueError("the order has no items")
    lines: list[dict[str, Any]] = []
    for item in items:
        product = catalog.get(item.sku)
        if product is None:
            raise ValueError(f"unknown SKU '{item.sku}'")
        if item.quantity > product.stock:
            raise ValueError(f"only {product.stock} units of {product.sku} in stock")
        lines.append({"sku": product.sku, "name": product.name, "quantity": item.quantity, "unit_price": product.price})
    subtotal = round(sum(line["quantity"] * line["unit_price"] for line in lines), 2)
    free = catalog.free_shipping_over is not None and subtotal >= catalog.free_shipping_over
    return lines, subtotal, 0.0 if free else catalog.shipping_flat


@register_tool("search_products", risk="read", description="Search the product catalog.")
def _search_products(ctx: ToolContext) -> BaseTool:
    catalog = load_catalog(ctx.agent_dir)

    def search_products(query: str) -> str:
        """Search products by name, category or feature. Returns SKU, price and stock. Never quote prices from memory."""
        found = search(catalog, query)
        if not found:
            return "No products found."
        lines = []
        for p in found:
            stock = f"in stock: {p.stock}" if p.stock else "OUT OF STOCK"
            lines.append(f"- {p.sku}: {p.name}, {p.price:.2f} {catalog.currency}, {stock}. {p.description}")
        return "\n".join(lines)

    return StructuredTool.from_function(search_products)


@register_tool("get_order_status", risk="read", description="Look up an order by id and e-mail.")
def _get_order_status(ctx: ToolContext) -> BaseTool:
    catalog = load_catalog(ctx.agent_dir)

    def get_order_status(order_id: str, email: str) -> str:
        """Get an order's status, items and total. Requires the order id and the e-mail used on the order."""
        try:
            order = _store(ctx).find(order_id, _email(email))
        except ValueError as exc:
            return f"error: {exc}"
        if order is None:
            return "error: no order with this id for this e-mail."
        items = ", ".join(f"{line['quantity']}x {line['name']}" for line in order["items"])
        tracking = f" Tracking: {order['tracking_code']}." if order.get("tracking_code") else ""
        total = f"{order['total']:.2f} {catalog.currency}"
        return f"Order {order['id']}: status {order['status']}. Items: {items}. Total {total}.{tracking}"

    return StructuredTool.from_function(get_order_status)


@register_tool("create_order", risk="write", description="Place an order (needs approval).")
def _create_order(ctx: ToolContext) -> BaseTool:
    catalog = load_catalog(ctx.agent_dir)

    def create_order(items: list[OrderItem], customer_name: str, email: str, shipping_address: str) -> str:
        """Place an order. Before calling, show the customer the items, quantities, total and address and get a yes.
        Payment is handled by a payment link sent by e-mail after the order is placed."""
        try:
            lines, subtotal, shipping = quote(catalog, items)
            address = _email(email)
        except ValueError as exc:
            return f"error: {exc}"
        if not customer_name.strip() or len(shipping_address.strip()) < 10:
            return "error: customer_name and a full shipping_address are required"
        order = {
            "id": "ORD-" + uuid.uuid4().hex[:6].upper(),
            "status": "placed",
            "customer_name": customer_name.strip()[:100],
            "email": address,
            "shipping_address": shipping_address.strip()[:300],
            "items": lines,
            "subtotal": subtotal,
            "shipping": shipping,
            "total": round(subtotal + shipping, 2),
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        _store(ctx).add(order)
        return (
            f"Order {order['id']} placed. Total {order['total']:.2f} {catalog.currency} "
            f"(shipping {shipping:.2f}). A payment link will be sent to {address}."
        )

    return StructuredTool.from_function(create_order)


@register_tool("cancel_order", risk="write", description="Cancel an order that has not shipped (needs approval).")
def _cancel_order(ctx: ToolContext) -> BaseTool:
    def cancel_order(order_id: str, email: str) -> str:
        """Cancel an order that has not shipped yet. Requires the order id and e-mail. Confirm with the customer first.
        Shipped orders cannot be cancelled: explain the returns policy instead."""
        store = _store(ctx)
        try:
            order = store.find(order_id, _email(email))
        except ValueError as exc:
            return f"error: {exc}"
        if order is None:
            return "error: no order with this id for this e-mail."
        if order["status"] not in CANCELLABLE:
            return f"error: order {order['id']} is '{order['status']}' and can no longer be cancelled."
        store.set_status(order["id"], "cancelled")
        return f"Order {order['id']} cancelled. Any payment will be refunded to the original method."

    return StructuredTool.from_function(cancel_order)
