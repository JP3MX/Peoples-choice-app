"""Create the Squawk King IA Stripe product and monthly/annual prices.

Before running, configure the business address and tax registrations in the
Stripe Dashboard. This script never invents or overwrites business identity.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
import stripe

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

PRODUCT_KEY = "squawk_king_full"
PRICES = [
    {"lookup_key": "sk_full_monthly", "amount": 1900, "interval": "month"},
    {"lookup_key": "sk_full_annual", "amount": 19000, "interval": "year"},
]


def get_or_create_product():
    for product in stripe.Product.list(active=True).auto_paging_iter():
        if product.to_dict().get("metadata", {}).get("product_key") == PRODUCT_KEY:
            return product
    return stripe.Product.create(
        name="Squawk King IA",
        tax_code="txcd_10103001",
        metadata={"managed_by": "jp3aviation", "product_key": PRODUCT_KEY},
    )


def main():
    product = get_or_create_product()
    for desired in PRICES:
        prices = stripe.Price.list(
            lookup_keys=[desired["lookup_key"]], active=True, limit=1
        ).data
        matching = prices and prices[0].unit_amount == desired["amount"] and prices[0].currency == "usd"
        if prices and not matching:
            stripe.Price.modify(prices[0].id, active=False)
            prices = []
        if not prices:
            stripe.Price.create(
                product=product.id,
                unit_amount=desired["amount"],
                currency="usd",
                lookup_key=desired["lookup_key"],
                transfer_lookup_key=True,
                recurring={"interval": desired["interval"]},
            )
            print("created", desired["lookup_key"])
        else:
            print("exists", desired["lookup_key"])
    print("catalog ready")


if __name__ == "__main__":
    main()
