#!/bin/bash
# Playto KYC - Quick Setup Script
set -e

echo "🚀 Setting up Playto KYC..."

# Create and activate virtualenv
python3 -m venv venv
source venv/bin/activate

# Install deps
pip install -r requirements.txt

# Run migrations
python manage.py makemigrations users kyc notifications
python manage.py migrate

# Create demo users
python manage.py shell -c "
from users.models import User

# Merchant
if not User.objects.filter(email='merchant@demo.com').exists():
    u = User.objects.create_user(email='merchant@demo.com', password='demo1234', full_name='Ravi Kumar', role='merchant')
    print(f'Created merchant: {u.email}')

# Reviewer
if not User.objects.filter(email='reviewer@demo.com').exists():
    u = User.objects.create_user(email='reviewer@demo.com', password='demo1234', full_name='Priya Sharma', role='reviewer', is_staff=True)
    print(f'Created reviewer: {u.email}')

print('Demo users ready!')
"

echo ""
echo "✅ Setup complete!"
echo ""
echo "Run the server:  python manage.py runserver"
echo ""
echo "Demo accounts:"
echo "  Merchant:  merchant@demo.com / demo1234"
echo "  Reviewer:  reviewer@demo.com / demo1234"
echo ""
echo "Open frontend/index.html in your browser"
echo "API base: http://localhost:8000/api/"
