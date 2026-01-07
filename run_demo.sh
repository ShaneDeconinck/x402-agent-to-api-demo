#!/bin/bash

echo "=================================="
echo "x402 + Stablecoins Demo Setup"
echo "=================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -q -r requirements.txt

# Generate database if it doesn't exist
if [ ! -f "data/real_estate.db" ]; then
    echo "🏗️  Generating mock database..."
    python3 data/generate_database.py
else
    echo "✓ Database already exists"
fi

# Check for .env file
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found. Copy .env.example to .env and add your ANTHROPIC_API_KEY"
    cp .env.example .env
    echo "   Created .env file - please add your API key"
fi

echo ""
echo "=================================="
echo "✅ Setup Complete!"
echo "=================================="
echo ""
echo "To run the demo:"
echo ""
echo "1. Start the API:"
echo "   cd api && uvicorn main:app --reload"
echo ""
echo "2. In another terminal, run the agent:"
echo "   python3 agent/real_estate_agent.py"
echo ""
echo "3. Open the frontend demo:"
echo "   open frontend/index.html"
echo ""
echo "=================================="
