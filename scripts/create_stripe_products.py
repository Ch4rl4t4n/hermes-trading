#!/usr/bin/env python3
"""Vytvorí Stripe produkty a ceny pre Hermes tiery (EUR)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import stripe

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

products = [
    {
        "name": "Hermes Pro",
        "description": "10 agentov, 15 alertov, Telegram bot, plný leaderboard",
        "tier": "pro",
        "prices": [
            {"amount": 1900, "interval": "month", "nickname": "Pro Monthly"},
            {"amount": 18240, "interval": "year", "nickname": "Pro Yearly"},
        ],
    },
    {
        "name": "Hermes Elite",
        "description": "Unlimited agenti, API prístup, custom watcher",
        "tier": "elite",
        "prices": [
            {"amount": 4900, "interval": "month", "nickname": "Elite Monthly"},
            {"amount": 47040, "interval": "year", "nickname": "Elite Yearly"},
        ],
    },
]

for p in products:
    product = stripe.Product.create(
        name=p["name"],
        description=p["description"],
        metadata={"tier": p["tier"]},
    )
    for price in p["prices"]:
        sp = stripe.Price.create(
            product=product.id,
            unit_amount=price["amount"],
            currency="eur",
            recurring={"interval": price["interval"]},
            nickname=price["nickname"],
            metadata={"tier": p["tier"]},
        )
        print(f"{price['nickname']}: {sp.id}")

print("\nUlož tieto Price ID do .env ako:")
print("STRIPE_PRICE_PRO_MONTHLY=price_...")
print("STRIPE_PRICE_PRO_YEARLY=price_...")
print("STRIPE_PRICE_ELITE_MONTHLY=price_...")
print("STRIPE_PRICE_ELITE_YEARLY=price_...")
