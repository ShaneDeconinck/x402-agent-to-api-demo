"""
Generate mock real estate database - San Francisco
This represents the incumbent's proprietary data asset
"""
import sqlite3
import random
from datetime import datetime, timedelta

# SF neighborhoods (weighted for realistic distribution)
NEIGHBORHOODS = [
    "Mission", "Mission", "Mission", "Mission",  # 20% - hot market
    "SOMA", "SOMA", "SOMA",  # 15% - tech hub
    "Marina", "Marina", "Marina",  # 15% - upscale
    "Castro", "Castro",  # 10%
    "Hayes Valley", "Hayes Valley",  # 10%
    "Noe Valley", "Noe Valley",  # 10%
    "Pacific Heights",  # 5% - luxury
    "Sunset", "Sunset",  # 10%
    "Richmond",  # 5%
]

# Property types (apartments dominate in SF)
PROPERTY_TYPES = [
    "condo", "condo", "condo", "condo", "condo",  # 50%
    "apartment", "apartment", "apartment",  # 30%
    "house",  # 10%
    "loft",  # 10%
]

# SF street names
STREETS = [
    "Valencia St", "Mission St", "Folsom St", "Howard St",
    "Market St", "Divisadero St", "Fillmore St", "Castro St",
    "Hayes St", "24th St", "18th St", "Guerrero St",
    "Dolores St", "Church St", "Sanchez St", "Noe St",
    "Union St", "Chestnut St", "Lombard St", "Green St",
]

def generate_listings(num_listings=300):
    """Generate realistic SF real estate listings"""
    listings = []

    for i in range(num_listings):
        neighborhood = random.choice(NEIGHBORHOODS)
        property_type = random.choice(PROPERTY_TYPES)

        # SF pricing (notoriously expensive)
        base_price = {
            "apartment": 850000,
            "condo": 1100000,
            "house": 1800000,
            "loft": 950000
        }[property_type]

        # Neighborhood multipliers
        neighborhood_multiplier = {
            "Pacific Heights": 1.8,
            "Marina": 1.4,
            "Noe Valley": 1.35,
            "Castro": 1.25,
            "Hayes Valley": 1.3,
            "Mission": 1.15,
            "SOMA": 1.1,
            "Sunset": 0.85,
            "Richmond": 0.8,
        }[neighborhood]

        price = int(base_price * neighborhood_multiplier * random.uniform(0.85, 1.25))

        # Bedrooms based on type
        bedrooms = {
            "apartment": random.choice([0, 1, 1, 2, 2]),
            "condo": random.choice([1, 2, 2, 3]),
            "house": random.choice([3, 3, 4, 4, 5]),
            "loft": random.choice([0, 1, 1, 2])
        }[property_type]

        # Square feet (SF units are small!)
        sqft = {
            "apartment": random.randint(450, 900),
            "condo": random.randint(700, 1400),
            "house": random.randint(1400, 2800),
            "loft": random.randint(800, 1500)
        }[property_type]

        # Days on market
        days_on_market = random.randint(1, 90)
        listed_date = (datetime.now() - timedelta(days=days_on_market)).strftime("%Y-%m-%d")

        # Address
        street = random.choice(STREETS)
        address = f"{random.randint(100, 3999)} {street}"

        listing = {
            "id": i + 1,
            "address": address,
            "neighborhood": neighborhood,
            "property_type": property_type,
            "bedrooms": bedrooms,
            "sqm": int(sqft * 0.093),  # Convert to sqm for international
            "sqft": sqft,
            "price": price,
            "listed_date": listed_date,
            "days_on_market": days_on_market,
            "description": f"Beautiful {property_type} in {neighborhood}, San Francisco"
        }

        listings.append(listing)

    return listings

def create_database():
    """Create SQLite database with listings"""
    import os
    db_path = os.path.join(os.path.dirname(__file__), 'real_estate.db')

    # Remove old database
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create listings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY,
            address TEXT NOT NULL,
            neighborhood TEXT NOT NULL,
            property_type TEXT NOT NULL,
            bedrooms INTEGER NOT NULL,
            sqm INTEGER NOT NULL,
            sqft INTEGER NOT NULL,
            price INTEGER NOT NULL,
            listed_date TEXT NOT NULL,
            days_on_market INTEGER NOT NULL,
            description TEXT
        )
    ''')

    # Generate and insert listings
    listings = generate_listings(300)

    for listing in listings:
        cursor.execute('''
            INSERT INTO listings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            listing['id'],
            listing['address'],
            listing['neighborhood'],
            listing['property_type'],
            listing['bedrooms'],
            listing['sqm'],
            listing['sqft'],
            listing['price'],
            listing['listed_date'],
            listing['days_on_market'],
            listing['description']
        ))

    conn.commit()
    conn.close()

    print(f"Generated {len(listings)} SF listings")
    print(f"Neighborhoods: {', '.join(set(l['neighborhood'] for l in listings))}")
    print(f"Price range: ${min(l['price'] for l in listings):,} - ${max(l['price'] for l in listings):,}")

if __name__ == "__main__":
    create_database()
