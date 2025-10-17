"""
Game Arbitrage Tracker - Flask Backend
Minimal web app for tracking video game prices via Keepa API
"""

from flask import Flask, render_template, request, jsonify, send_file
import keepa
import os
from datetime import datetime
import pandas as pd
from io import BytesIO

app = Flask(__name__)

# Get API key from environment variable (set in Render)
KEEPA_API_KEY = os.environ.get('KEEPA_API_KEY', '')

# Initialize Keepa API
api = None
if KEEPA_API_KEY:
    try:
        api = keepa.Keepa(KEEPA_API_KEY)
    except Exception as e:
        print(f"Error initializing Keepa API: {e}")

@app.route('/')
def index():
    """Serve the main page"""
    return render_template('index.html')

@app.route('/api/process', methods=['POST'])
def process_upcs():
    """Process UPCs and fetch data from Keepa"""
    
    if not api:
        return jsonify({'error': 'Keepa API not configured'}), 500
    
    data = request.json
    upcs = data.get('upcs', [])
    
    if not upcs:
        return jsonify({'error': 'No UPCs provided'}), 400
    
    # Limit to prevent abuse
    if len(upcs) > 2000:
        return jsonify({'error': 'Maximum 2000 UPCs allowed'}), 400
    
    results = []
    errors = []
    
    # Process in batches of 100
    batch_size = 100
    for i in range(0, len(upcs), batch_size):
        batch = upcs[i:i+batch_size]
        
        try:
            # Query Keepa API
            products = api.query(
                batch,
                product_code_is_asin=False,
                history=True,
                stats=90,  # 90 days of stats
                offers=20   # Get offer data
            )
            
            # Process each product
            for idx, product in enumerate(products):
                if not product:
                    errors.append({
                        'upc': batch[idx],
                        'error': 'Product not found'
                    })
                    continue
                
                try:
                    # Extract price data
                    current_price = None
                    price_history = []
                    
                    if 'data' in product and 'NEW' in product['data']:
                        prices = product['data']['NEW']
                        if prices and len(prices) > 0:
                            current_price = prices[-1] / 100  # Convert from cents
                            price_history = [p/100 for p in prices if p is not None and p > 0]
                    
                    # Calculate stats
                    low_90 = min(price_history) if price_history else None
                    high_90 = max(price_history) if price_history else None
                    avg_30 = sum(price_history[-30:]) / len(price_history[-30:]) if len(price_history) >= 30 else current_price
                    
                    # Get sales rank
                    sales_rank = product.get('salesRank', 999999)
                    if isinstance(sales_rank, list) and len(sales_rank) > 0:
                        sales_rank = sales_rank[-1] if sales_rank[-1] > 0 else 999999
                    
                    # Estimate monthly sales based on rank
                    if sales_rank < 1000:
                        est_sales = 1500
                    elif sales_rank < 5000:
                        est_sales = 800
                    elif sales_rank < 20000:
                        est_sales = 300
                    elif sales_rank < 50000:
                        est_sales = 100
                    elif sales_rank < 100000:
                        est_sales = 30
                    else:
                        est_sales = 10
                    
                    # Get seller count
                    seller_count = 0
                    if 'offers' in product and product['offers']:
                        seller_count = len(product['offers'])
                    
                    # Check if Amazon is in stock
                    amazon_oos = False
                    if 'data' in product and 'AMAZON' in product['data']:
                        amazon_prices = product['data']['AMAZON']
                        amazon_oos = not amazon_prices or amazon_prices[-1] == -1
                    
                    # Determine trend
                    trend = 'stable'
                    if len(price_history) >= 10:
                        recent_avg = sum(price_history[-5:]) / 5
                        older_avg = sum(price_history[-10:-5]) / 5
                        if recent_avg > older_avg * 1.05:
                            trend = 'rising'
                        elif recent_avg < older_avg * 0.95:
                            trend = 'falling'
                    
                    # Calculate profit (assuming $30 buy cost)
                    if current_price:
                        buy_cost = 30
                        amazon_fee = current_price * 0.15
                        fba_fee = 3.99
                        shipping = 2.00
                        profit = current_price - buy_cost - amazon_fee - fba_fee - shipping
                    else:
                        profit = None
                    
                    result = {
                        'upc': batch[idx],
                        'title': product.get('title', 'Unknown'),
                        'asin': product.get('asin', ''),
                        'current_price': current_price,
                        'avg_30': avg_30,
                        'low_90': low_90,
                        'high_90': high_90,
                        'sales_rank': sales_rank,
                        'est_sales_month': est_sales,
                        'seller_count': seller_count,
                        'amazon_oos': amazon_oos,
                        'trend': trend,
                        'profit': profit,
                        'price_history': price_history[-12:] if len(price_history) > 12 else price_history
                    }
                    
                    results.append(result)
                    
                except Exception as e:
                    errors.append({
                        'upc': batch[idx],
                        'error': str(e)
                    })
                    
        except Exception as e:
            # Batch failed
            for upc in batch:
                errors.append({
                    'upc': upc,
                    'error': f'Batch error: {str(e)}'
                })
    
    return jsonify({
        'results': results,
        'errors': errors,
        'total_processed': len(results),
        'total_errors': len(errors)
    })

@app.route('/api/download', methods=['POST'])
def download_excel():
    """Generate and download Excel file"""
    
    data = request.json
    results = data.get('results', [])
    
    if not results:
        return jsonify({'error': 'No data to export'}), 400
    
    # Create Excel file in memory
    output = BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Main data sheet
        df = pd.DataFrame(results)
        
        # Reorder columns
        columns = ['title', 'upc', 'asin', 'current_price', 'avg_30', 'low_90', 'high_90', 
                   'sales_rank', 'est_sales_month', 'seller_count', 'profit', 'amazon_oos', 'trend']
        df = df[[col for col in columns if col in df.columns]]
        
        # Rename for readability
        df.columns = ['Title', 'UPC', 'ASIN', 'Current Price', '30-Day Avg', '90-Day Low', 
                      '90-Day High', 'Sales Rank', 'Est Sales/Month', 'Sellers', 
                      'Profit (@$30 cost)', 'Amazon OOS', 'Trend']
        
        df.to_excel(writer, sheet_name='Game Data', index=False)
        
        # Price history sheet (if available)
        history_data = []
        for item in results:
            if 'price_history' in item and item['price_history']:
                for idx, price in enumerate(item['price_history']):
                    history_data.append({
                        'UPC': item['upc'],
                        'Title': item['title'],
                        'Price': price,
                        'Period': idx + 1
                    })
        
        if history_data:
            history_df = pd.DataFrame(history_data)
            history_df.to_excel(writer, sheet_name='Price History', index=False)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'game_arbitrage_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    )

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'api_configured': api is not None
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
