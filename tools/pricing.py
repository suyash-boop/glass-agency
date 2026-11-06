#!/usr/bin/env python3
"""Deterministic pricing for Glass Agency agents.

Agents never do money math in their heads. They call this script so every
quote, change request and invoice is reproducible from the rate card.

Usage:
  python tools/pricing.py items
  python tools/pricing.py quote   --items landing_page,menu_or_catalog,whatsapp_button [--days 3] [--view client|internal]
  python tools/pricing.py invoice --client "Crumb & Co" --items landing_page,... [--change blog] [--days 3] [--number 1]

Item ids may repeat (extra_section,extra_section) or take a count (extra_section:2).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

CARD_PATH = Path(__file__).with_name("rate-card.json")


def load_card() -> dict:
    return json.loads(CARD_PATH.read_text(encoding="utf-8"))


def parse_items(spec: str, card: dict) -> list[tuple[str, int]]:
    out: dict[str, int] = {}
    for raw in filter(None, (s.strip() for s in spec.split(","))):
        key, _, count = raw.partition(":")
        if key not in card["items"]:
            sys.exit(f"Unknown item '{key}'. Run `python tools/pricing.py items` to list valid ids.")
        out[key] = out.get(key, 0) + (int(count) if count else 1)
    return list(out.items())


def price_lines(items: list[tuple[str, int]], card: dict, days: int | None) -> dict:
    rate = card["hourly_cost"] / (1 - card["target_margin"])  # client-facing hourly rate
    rush = days is not None and days < card["rush_threshold_days"]
    mult = card["rush_multiplier"] if rush else 1.0
    lines = []
    for key, qty in items:
        item = card["items"][key]
        hours = item["hours"] * qty
        price = math.ceil(hours * rate * mult)
        cost = hours * card["hourly_cost"]
        lines.append({"id": key, "label": item["label"], "qty": qty, "hours": hours, "price": price, "cost": cost})
    subtotal = sum(l["price"] for l in lines)
    tax = round(subtotal * card["tax_rate"], 2)
    cost = sum(l["cost"] for l in lines)
    return {
        "lines": lines,
        "rush": rush,
        "subtotal": subtotal,
        "tax": tax,
        "total": subtotal + tax,
        "hours": sum(l["hours"] for l in lines),
        "cost": cost,
        "margin": (subtotal - cost) / subtotal if subtotal else 0,
    }


def money(card: dict, v: float) -> str:
    return f"{card['currency']} {v:,.2f}"


def render_quote(q: dict, card: dict, view: str) -> str:
    rows = ["| Item | Qty | Price |", "|---|---:|---:|"]
    if view == "internal":
        rows = ["| Item | Qty | Hours | Cost | Price |", "|---|---:|---:|---:|---:|"]
    for l in q["lines"]:
        if view == "internal":
            rows.append(f"| {l['label']} | {l['qty']} | {l['hours']:g} | {money(card, l['cost'])} | {money(card, l['price'])} |")
        else:
            rows.append(f"| {l['label']} | {l['qty']} | {money(card, l['price'])} |")
    out = "\n".join(rows)
    if q["rush"]:
        out += f"\n\nRush delivery (< {card['rush_threshold_days']} days): x{card['rush_multiplier']} applied."
    out += f"\n\n**Total: {money(card, q['total'])}**"
    if view == "internal":
        out += (f"\n\nInternal: {q['hours']:g} h, cost {money(card, q['cost'])}, "
                f"margin {q['margin']:.0%} (target {card['target_margin']:.0%}).")
    return out


def render_invoice(args, card: dict) -> str:
    base = price_lines(parse_items(args.items, card), card, args.days)
    change = price_lines(parse_items(args.change, card), card, args.days) if args.change else None
    today = dt.date.today()
    total = base["total"] + (change["total"] if change else 0)
    lines = [
        f"# Invoice GA-{today:%Y%m}-{args.number:03d}",
        "",
        f"**From:** {card['studio']}  ",
        f"**To:** {args.client}  ",
        f"**Date:** {today.isoformat()}  ",
        f"**Due:** {(today + dt.timedelta(days=14)).isoformat()}",
        "",
        "## Agreed scope",
        render_quote(base, card, "client"),
    ]
    if change:
        lines += ["", "## Approved change requests", render_quote(change, card, "client")]
    lines += ["", f"## Amount due: {money(card, total)}", "", "Thank you for working with us."]
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("items")
    q = sub.add_parser("quote")
    q.add_argument("--items", required=True)
    q.add_argument("--days", type=int)
    q.add_argument("--view", choices=["client", "internal"], default="client")
    inv = sub.add_parser("invoice")
    inv.add_argument("--client", required=True)
    inv.add_argument("--items", required=True)
    inv.add_argument("--change", default="")
    inv.add_argument("--days", type=int)
    inv.add_argument("--number", type=int, default=1)
    args = p.parse_args()
    card = load_card()

    if args.cmd == "items":
        for k, v in card["items"].items():
            print(f"{k:16} {v['hours']:>4g} h  {v['label']}")
    elif args.cmd == "quote":
        print(render_quote(price_lines(parse_items(args.items, card), card, args.days), card, args.view))
    else:
        print(render_invoice(args, card))


if __name__ == "__main__":
    main()
