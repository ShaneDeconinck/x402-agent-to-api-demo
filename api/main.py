"""
Real Estate API with x402 Payment Required

Two-tier API demonstrating agent-accessible data assets:
- Tier 1: Listings ($0.01)
- Tier 2: AI Valuation ($0.10)

x402 spec: https://docs.cdp.coinbase.com/x402
"""
from fastapi import FastAPI, HTTPException, Header, Query, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
import sqlite3
import os
import json
import base64
from pydantic import BaseModel

from payment import get_payment_verifier, USDC_CONTRACT_ADDRESS
from valuation import calculate_valuation
from demo import router as demo_router

# Payment configuration
RECIPIENT_ADDRESS = os.environ.get("RECIPIENT_ADDRESS")
CHAIN_ID = 84532  # Base Sepolia
NETWORK = "base-sepolia"

app = FastAPI(
    title="Real Estate API (x402)",
    description="Agent-accessible real estate data with pay-per-query model",
    version="0.1.0"
)

# CORS for frontend demo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include demo router
app.include_router(demo_router)


class PaymentRequiredError(Exception):
    """Custom exception for 402 Payment Required"""
    def __init__(self, tier: int, error: str = None):
        self.tier = tier
        self.error = error


# Exception handler for 402 Payment Required
@app.exception_handler(PaymentRequiredError)
async def payment_required_handler(request, exc: PaymentRequiredError):
    """Return 402 with PAYMENT-REQUIRED header per x402 spec"""
    payment_required = get_x402_payment_required(exc.tier)
    if exc.error:
        payment_required["error"] = exc.error

    encoded = encode_payment_required(payment_required)

    return JSONResponse(
        status_code=402,
        content={"error": "Payment Required", "details": payment_required},
        headers={"X-PAYMENT-REQUIRED": encoded}
    )

# Payment verifier (verifies real USDC transactions on Base Sepolia)
payment_verifier = get_payment_verifier()

# Database path (relative to api directory)
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "real_estate.db")


# Models
class ListingQuery(BaseModel):
    neighborhood: Optional[str] = None
    property_type: Optional[str] = None
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    bedrooms: Optional[int] = None
    limit: int = 10


class PricingInfo(BaseModel):
    """API pricing information"""
    tier_1_price: float
    tier_1_description: str
    tier_2_price: float
    tier_2_description: str
    payment_method: str
    currency: str


# Helper functions
def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_x402_payment_required(tier: int) -> dict:
    """
    Generate x402 PaymentRequired object per spec.

    See: https://docs.cdp.coinbase.com/x402/core-concepts/how-it-works
    Spec: https://www.x402.org/
    """
    price_usd = payment_verifier.get_price(tier)
    amount_units = int(price_usd * 1_000_000)  # USDC has 6 decimals
    resource = "/api/v1/listings" if tier == 1 else "/api/v1/valuation"

    return {
        "x402Version": 1,
        "accepts": [
            {
                "scheme": "exact",
                "network": "base-sepolia",
                "maxAmountRequired": str(amount_units),
                "resource": resource,
                "description": f"Pay ${price_usd} USDC for Tier {tier} access",
                "mimeType": "application/json",
                "payTo": RECIPIENT_ADDRESS,
                "maxTimeoutSeconds": 300,
                "asset": USDC_CONTRACT_ADDRESS,
                "extra": {
                    "name": "USDC",
                    "version": "1"
                }
            }
        ]
    }


def encode_payment_required(payment_required: dict) -> str:
    """Base64 encode the PaymentRequired object for the header"""
    json_str = json.dumps(payment_required)
    return base64.b64encode(json_str.encode()).decode()


def verify_x402_payment(x_payment: Optional[str], tier: int) -> dict:
    """
    Verify and settle x402 payment from X-PAYMENT header.

    Per x402 spec using EIP-3009:
    - Client sends signed authorization in X-PAYMENT header (base64 JSON)
    - Server verifies and settles via transferWithAuthorization
    - Contract handles nonce/replay protection
    """
    if not x_payment:
        raise PaymentRequiredError(tier)

    # Verify and settle payment via EIP-3009 transferWithAuthorization
    verification = payment_verifier.verify_and_settle(x_payment, tier)

    if not verification["valid"]:
        raise PaymentRequiredError(tier, verification.get("error", "Payment verification failed"))

    return verification


# Endpoints

@app.get("/")
async def root():
    """API information and discovery"""
    return {
        "name": "Real Estate API",
        "description": "Agent-accessible real estate data with x402 payment",
        "version": "0.1.0",
        "x402": {
            "version": 1,
            "docs": "https://docs.cdp.coinbase.com/x402"
        },
        "tiers": {
            "tier_1": {
                "endpoint": "/api/v1/listings",
                "description": "Query real estate listings",
                "price_usd": 0.01,
                "payment_required": True
            },
            "tier_2": {
                "endpoint": "/api/v1/valuation",
                "description": "Proprietary property valuation",
                "price_usd": 0.10,
                "payment_required": True
            }
        },
        "payment": {
            "network": "base-sepolia",
            "asset": "USDC",
            "header": "X-PAYMENT",
            "response_header": "X-PAYMENT-REQUIRED"
        },
        "docs": "/docs"
    }


@app.get("/pricing")
async def get_pricing() -> PricingInfo:
    """Get API pricing information"""
    return PricingInfo(
        tier_1_price=0.01,
        tier_1_description="Query listings by neighborhood",
        tier_2_price=0.10,
        tier_2_description="AI-powered property valuation",
        payment_method="USDC on Base Sepolia (x402)",
        currency="USD"
    )


@app.get("/api/v1/listings")
async def get_listings(
    neighborhood: Optional[str] = None,
    property_type: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    bedrooms: Optional[int] = None,
    limit: int = Query(10, le=20),  # Max 20 results (prevents bulk extraction)
    x_payment: Optional[str] = Header(None, alias="X-PAYMENT")
):
    """
    TIER 1: Query real estate listings ($0.01 per query)

    Requires x402 payment in X-PAYMENT header

    Query parameters prevent bulk extraction:
    - Must specify search criteria
    - Maximum 20 results per query
    - Cannot dump entire database
    """
    # Verify payment
    payment = verify_x402_payment(x_payment, tier=1)

    # Build query
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM listings WHERE 1=1"
    params = []

    if neighborhood:
        query += " AND neighborhood = ?"
        params.append(neighborhood)

    if property_type:
        query += " AND property_type = ?"
        params.append(property_type)

    if min_price:
        query += " AND price >= ?"
        params.append(min_price)

    if max_price:
        query += " AND price <= ?"
        params.append(max_price)

    if bedrooms is not None:
        query += " AND bedrooms = ?"
        params.append(bedrooms)

    query += f" LIMIT {limit}"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    listings = [dict(row) for row in rows]
    conn.close()

    return {
        "tier": 1,
        "price_paid_usd": payment["amount_usd"],
        "query": {
            "neighborhood": neighborhood,
            "property_type": property_type,
            "min_price": min_price,
            "max_price": max_price,
            "bedrooms": bedrooms
        },
        "result_count": len(listings),
        "listings": listings,
        "note": "Data queries are scoped to prevent bulk extraction. Multiple specific queries required to access full dataset."
    }


@app.get("/api/v1/valuation")
async def get_valuation(
    address: str,
    x_payment: Optional[str] = Header(None, alias="X-PAYMENT")
):
    """
    TIER 2: Property valuation ($0.10 per query)

    Requires x402 payment in X-PAYMENT header

    Returns proprietary valuation based on:
    - Comparable sales analysis
    - Market demand signals
    - Neighborhood trends
    - Confidence scoring

    This endpoint sells INSIGHTS, not raw data.
    The algorithm is the intellectual property.
    """
    # Verify payment
    payment = verify_x402_payment(x_payment, tier=2)

    # Calculate valuation
    valuation = calculate_valuation(address, DB_PATH)

    if not valuation:
        raise HTTPException(
            status_code=404,
            detail=f"Property not found: {address}"
        )

    return {
        "tier": 2,
        "price_paid_usd": payment["amount_usd"],
        "valuation": valuation,
        "note": "Valuation uses proprietary algorithm. The IP is in the calculation, not the data."
    }


@app.get("/health")
async def health_check():
    """Health check endpoint (no payment required)"""
    return {"status": "healthy", "payment_required": False}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
