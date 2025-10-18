"""
Flask Backend for Game Arbitrage Tracker
Connects your HTML frontend to the Keepa API
Optimized for Render deployment
"""

from flask import Flask, render_template, request, jsonify, send_file
import keepa
import pandas as pd
from datetime import datetime
import io
import os

app = Flask(__name__)

# Get Keepa API key from environment variable (set in Render dashboard)
KEEPA_API_KEY = os.environ.get('KEEPA_API_KEY', 'YOUR_KEEPA_API_KEY_HERE')

@app.route('/')
def index():
    """Serve the main HTML page"""
    return render_template('index.html')

@app.route('/api/process', methods=['POST'])
def process_upcs():
    """
    Process UPCs and return game data from Keepa
    """
    try:
        data = request.get_json()
        upcs = data.get('upcs', [])
        
        if not upcs:
            return jsonify({'error': 'No UPCs provided'}), 400
        
        # Limit to prevent timeout (process max 100 at once on free tier)
        if len(upcs) > 100:
            return jsonify({
                'error': f'Too many UPCs ({len(upcs)}). Please process in batches of 100 or less.'
            }), 400
        
        # Initialize Keepa API
        if KEEPA_API_KEY == 'YOUR_KEEPA_API_KEY_HERE':
            return jsonify({'error': 'Keepa API key not configured'}), 500
        
        api = keepa.Keepa(KEEPA_API_KEY)
        
        # Query Keepa API
        products = api.query(
            upcs,
            product_code_is_asin=False,
            history=True,
            stats=90,
            offers=20
        )
        
        # Process results
        results = []
        errors = []
        
        for idx, product in enumerate(products):
            upc = upcs[idx]
            
            if not product:
                errors.append({
                    'upc': upc,
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
                        current_price = prices[-1] / 100 if prices[-1] > 0 else None
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
                
                # Check if Amazon is out of stock
                amazon_oos = False
                if 'data' in product and 'AMAZON' in product['data']:
                    amazon_prices = product['data']['AMAZON']
                    amazon_oos = not amazon_prices or amazon_prices[-1] == -1
                
                # Determine price trend
                trend = 'stable'
                if len(price_history) >= 10:
                    recent_avg = sum(price_history[-5:]) / 5
                    older_avg = sum(price_history[-10:-5]) / 5
                    if recent_avg > older_avg * 1.05:
                        trend = 'rising'
                    elif recent_avg < older_avg * 0.95:
                        trend = 'falling'
                
                # Calculate profit (assuming $30 buy cost)
                profit = None
                if current_price:
                    buy_cost = 30
                    amazon_fee = current_price * 0.15
                    fba_fee = 3.99
                    shipping = 2.00
                    profit = current_price - buy_cost - amazon_fee - fba_fee - shipping
                
                result = {
                    'upc': upc,
                    'title': product.get('title', 'Unknown'),
                    'asin': product.get('asin', ''),
                    'current_price': current_price,
                    'avg_30': avg_30,
                    'low_90': low_90,
                    'high_90': high_90,
                    'sales_rank': sales_rank,
                    'est_sales_month': est_sales,
                    'seller_count': seller_count,
                    'profit': profit,
                    'amazon_oos': amazon_oos,
                    'trend': trend,
                    'processed_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                
                results.append(result)
                
            except Exception as e:
                errors.append({
                    'upc': upc,
                    'error': str(e)
                })
        
        return jsonify({
            'results': results,
            'errors': errors,
            'summary': {
                'total': len(upcs),
                'successful': len(results),
                'errors': len(errors)
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def download_excel():
    """
    Generate and download Excel file with results
    """
    try:
        data = request.get_json()
        results = data.get('results', [])
        
        if not results:
            return jsonify({'error': 'No results to download'}), 400
        
        # Create DataFrame
        df = pd.DataFrame(results)
        
        # Reorder columns for better readability
        column_order = [
            'title', 'upc', 'asin', 'current_price', 'avg_30', 
            'low_90', 'high_90', 'sales_rank', 'est_sales_month',
            'seller_count', 'profit', 'amazon_oos', 'trend', 'processed_date'
        ]
        df = df[[col for col in column_order if col in df.columns]]
        
        # Rename columns for Excel
        df.columns = [
            'Title', 'UPC', 'ASIN', 'Current Price', '30-Day Avg',
            '90-Day Low', '90-Day High', 'Sales Rank', 'Est Sales/Month',
            'Sellers', 'Profit (@$30 cost)', 'Amazon OOS', 'Trend', 'Processed Date'
        ]
        
        # Create Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Game Data', index=False)
        output.seek(0)
        
        # Generate filename with timestamp
        filename = f'game_arbitrage_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    """Health check endpoint for Render"""
    return jsonify({'status': 'healthy'}), 200

if __name__ == '__main__':
    # Use PORT from environment (Render sets this automatically)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
