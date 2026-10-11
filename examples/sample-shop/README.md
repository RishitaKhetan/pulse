# TechShop - Sample E-Commerce Store

A demo e-commerce website that integrates with Pulse Analytics to track user behavior through a shopping funnel.

## What It Does

TechShop simulates a real online store with a complete shopping flow:

1. **Browse** - Users view product catalog
2. **Add to Cart** - Users add items to their shopping cart
3. **Checkout** - Users enter shipping and payment info
4. **Purchase** - Users complete their purchase

Each action sends an event to Pulse Analytics, creating a natural funnel pattern.

## Events Tracked

| Event | Triggered When |
|-------|---|
| `page_view` | User lands on the store |
| `product_view` | User views a product |
| `add_to_cart` | User adds item to cart |
| `remove_from_cart` | User removes item from cart |
| `browse_continue` | User continues shopping from cart |
| `begin_checkout` | User starts the checkout process |
| `purchase` | User completes purchase |

## Expected Funnel

```
page_view
    ↓
product_view → add_to_cart (multiple times)
    ↓
begin_checkout
    ↓
purchase
```

## How to Use

### Step 1: Start Pulse

```bash
cd "C:\Users\Rishita Khetan\Documents\PROJECTS\pulse"
pulse start
```

Dashboard opens at `http://localhost:4747`

### Step 2: Open the Sample Shop

Open this file in a browser:
```
file:///C:/Users/Rishita%20Khetan/Documents/PROJECTS/pulse/examples/sample-shop/index.html
```

Or use a local server:
```bash
python -m http.server 8000
# Then visit http://localhost:8000/examples/sample-shop/
```

### Step 3: Test the Funnel

1. Browse products
2. Add 2-3 items to cart
3. Go to checkout
4. Complete purchase
5. Repeat with a new user (click "Start Shopping Again")

### Step 4: View Analytics

Go to `http://localhost:4747` and see:

- **Events** - All tracked events (product_view, add_to_cart, purchase, etc.)
- **Top Users** - Users who made purchases
- **Funnel Suggestions** - Auto-detected funnel: `page_view → product_view → add_to_cart → begin_checkout → purchase`

## Analyzing Your Data

### Expected Patterns

After running the sample shop a few times:

- **product_view → add_to_cart** - High conversion (most viewers add items)
- **add_to_cart → begin_checkout** - Medium conversion (some users abandon cart)
- **begin_checkout → purchase** - High conversion (most reach purchase)

### Using Pulse Dashboard

1. Go to **Funnels** tab
2. Click on auto-suggested funnels
3. Analyze where users drop off
4. In a real store, optimize these drop-off points

## Customization

Edit `index.html` to:

- Change product names/prices
- Add more products
- Track additional properties
- Change user flow

Any changes you make will automatically be reflected in Pulse Analytics.

## Tips

- Open multiple browser windows to simulate different users
- The user ID is auto-generated (e.g., "happy_tiger", "smart_eagle")
- Each user session creates a unique shopping journey
- Check Pulse dashboard in real-time to see events appearing

## Integration with Your App

Use the same Pulse SDK integration pattern from this demo in your own apps:

```javascript
// Initialize
Pulse.init();

// Track events
Pulse.track('my_event', user_id, { key: value });

// Flush before leaving
Pulse.flush();
```
