"""Idempotent Stripe catalog setup for Squawk King IA subscription tiers.
Run: python setup_stripe.py
"""
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")
import stripe

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

# Digital SaaS subscriptions. Tax code: SaaS.
CATALOG = [
    {
        "emergent_product_id": "sk_basic",
        "name": "Squawk King — Basic",
        "tax_code": "txcd_10103001",
        "prices": [{"lookup_key": "sk_basic_monthly", "amount": 1900, "currency": "usd", "interval": "month"}],
    },
    {
        "emergent_product_id": "sk_pro",
        "name": "Squawk King — Pro",
        "tax_code": "txcd_10103001",
        "prices": [{"lookup_key": "sk_pro_monthly", "amount": 3900, "currency": "usd", "interval": "month"}],
    },
    {
        "emergent_product_id": "sk_unlimited",
        "name": "Squawk King — Unlimited",
        "tax_code": "txcd_10103001",
        "prices": [{"lookup_key": "sk_unlimited_monthly", "amount": 7900, "currency": "usd", "interval": "month"}],
    },
]


def ensure_tax_settings():
    s = stripe.tax.Settings.retrieve()
    if s.head_office and getattr(s.head_office, "address", None):
        return
    stripe.tax.Settings.modify(
        head_office={"address": {"country": "US", "line1": "1 Hangar Row",
                                 "city": "Wichita", "state": "KS", "postal_code": "67209"}},
        defaults={"tax_behavior": "exclusive"},
    )


def get_or_create_product(entry):
    for p in stripe.Product.list(active=True).auto_paging_iter():
        if p.to_dict().get("metadata", {}).get("emergent_product_id") == entry["emergent_product_id"]:
            return p
    return stripe.Product.create(
        name=entry["name"], tax_code=entry.get("tax_code"),
        metadata={"managed_by": "emergent", "emergent_product_id": entry["emergent_product_id"]},
    )


def main():
    try:
        ensure_tax_settings()
    except Exception as e:
        print("tax settings:", e)
    for entry in CATALOG:
        product = get_or_create_product(entry)
        for p in entry["prices"]:
            existing = stripe.Price.list(lookup_keys=[p["lookup_key"]], active=True, limit=1).data
            if existing and (existing[0].unit_amount != p["amount"] or existing[0].currency != p["currency"]):
                stripe.Price.modify(existing[0].id, active=False)
                existing = []
            if not existing:
                kwargs = dict(product=product.id, unit_amount=p["amount"], currency=p["currency"],
                              lookup_key=p["lookup_key"], transfer_lookup_key=True,
                              recurring={"interval": p["interval"]})
                stripe.Price.create(**kwargs)
                print("created price", p["lookup_key"])
            else:
                print("exists", p["lookup_key"])
    print("catalog ready")


if __name__ == "__main__":
    main()
