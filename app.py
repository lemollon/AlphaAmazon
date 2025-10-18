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
                # Extract price data - Use Keepa's pre-parsed data
                current_price = None
                price_history = []
                
                # Keepa Python library provides parsed data in 'data' with '_time' suffix
                # Prices are already converted to dollars
                if 'data' in product:
                    # Try to get NEW price (marketplace new price)
                    if 'NEW' in product['data'] and 'NEW_time' in product['data']:
                        prices = product['data']['NEW']
                        times = product['data']['NEW_time']
                        
                        if prices is not None and len(prices) > 0:
                            # Filter out None and -0.01 (out of stock indicators)
                            valid_prices = [p for p in prices if p is not None and p > 0]
                            if valid_prices:
                                current_price = valid_prices[-1]
                                price_history = valid_prices
                
                # Calculate stats
                low_90 = min(price_history) if price_history else None
                high_90 = max(price_history) if price_history else None
                avg_30 = sum(price_history[-30:]) / len(price_history[-30:]) if len(price_history) >= 30 else current_price
                
                # Get sales rank
                sales_rank = product.get('salesRank', 999999)
                if isinstance(sales_rank, list) and len(sales_rank) > 0:
                    sales_rank = sales_rank[-1] if sales_rank[-1] > 0 else 999999
                
                # Estimate monthly sales based on rank
                est_sales_per_day = 0
                velocity_category = 'unknown'
                velocity_explanation = ''
                
                if sales_rank < 1000:
                    est_sales = 1500
                    est_sales_per_day = 50
                    velocity_category = 'lightning'
                    velocity_explanation = 'LIGHTNING FAST - Sells multiple times per day. Will sell within hours.'
                elif sales_rank < 5000:
                    est_sales = 800
                    est_sales_per_day = 27
                    velocity_category = 'very_fast'
                    velocity_explanation = 'VERY FAST - Sells almost daily. Will sell within 1-3 days.'
                elif sales_rank < 20000:
                    est_sales = 300
                    est_sales_per_day = 10
                    velocity_category = 'fast'
                    velocity_explanation = 'FAST - Sells several times per week. Will sell within a week.'
                elif sales_rank < 50000:
                    est_sales = 100
                    est_sales_per_day = 3
                    velocity_category = 'moderate'
                    velocity_explanation = 'MODERATE - Sells a few times per week. May take 1-2 weeks to sell.'
                elif sales_rank < 100000:
                    est_sales = 30
                    est_sales_per_day = 1
                    velocity_category = 'slow'
                    velocity_explanation = 'SLOW - Sells about once per month. May take 30+ days to sell.'
                else:
                    est_sales = 10
                    est_sales_per_day = 0.3
                    velocity_category = 'very_slow'
                    velocity_explanation = 'VERY SLOW - Rarely sells. May take months to sell. High risk.'
                
                # Get seller count
                seller_count = 0
                if 'offers' in product and product['offers']:
                    seller_count = len(product['offers'])
                
                # Check if Amazon is out of stock
                amazon_oos = False
                if 'data' in product and 'AMAZON' in product['data']:
                    amazon_prices = product['data']['AMAZON']
                    if amazon_prices is not None and hasattr(amazon_prices, '__len__') and len(amazon_prices) > 0:
                        amazon_price_values = [amazon_prices[i] for i in range(1, len(amazon_prices), 2)]
                        last_amazon_price = amazon_price_values[-1] if amazon_price_values else -1
                        amazon_oos = last_amazon_price == -1 or last_amazon_price is None
                    else:
                        amazon_oos = True
                else:
                    amazon_oos = True
                
                # Determine price trend
                trend = 'stable'
                if len(price_history) >= 10:
                    recent_avg = sum(price_history[-5:]) / 5
                    older_avg = sum(price_history[-10:-5]) / 5
                    if recent_avg > older_avg * 1.05:
                        trend = 'rising'
                    elif recent_avg < older_avg * 0.95:
                        trend = 'falling'
                
                # Calculate profit and ROI
                profit = None
                roi_percent = None
                break_even_price = None
                buy_cost = 30
                
                if current_price:
                    amazon_fee = current_price * 0.15
                    fba_fee = 3.99
                    shipping = 2.00
                    total_fees = amazon_fee + fba_fee + shipping
                    profit = current_price - buy_cost - total_fees
                    
                    if buy_cost > 0:
                        roi_percent = (profit / buy_cost) * 100
                    
                    break_even_price = (buy_cost + fba_fee + shipping) / 0.85
                
                # Price vs Average Analysis
                price_vs_avg_percent = None
                price_vs_avg_signal = 'neutral'
                price_vs_avg_text = ''
                
                if current_price and avg_30:
                    price_vs_avg_percent = ((current_price - avg_30) / avg_30) * 100
                    
                    if price_vs_avg_percent <= -10:
                        price_vs_avg_signal = 'excellent'
                        price_vs_avg_text = f'{abs(price_vs_avg_percent):.1f}% below average - EXCELLENT BUY'
                    elif price_vs_avg_percent <= -5:
                        price_vs_avg_signal = 'good'
                        price_vs_avg_text = f'{abs(price_vs_avg_percent):.1f}% below average - GOOD BUY'
                    elif price_vs_avg_percent <= 5:
                        price_vs_avg_signal = 'neutral'
                        price_vs_avg_text = 'Near average price'
                    elif price_vs_avg_percent <= 10:
                        price_vs_avg_signal = 'caution'
                        price_vs_avg_text = f'{price_vs_avg_percent:.1f}% above average - WAIT'
                    else:
                        price_vs_avg_signal = 'bad'
                        price_vs_avg_text = f'{price_vs_avg_percent:.1f}% above average - AVOID'
                
                # Competition Analysis
                competition_level = 'unknown'
                competition_warning = ''
                
                if seller_count > 0:
                    if seller_count >= 50:
                        competition_level = 'very_high'
                        competition_warning = 'VERY HIGH COMPETITION - Avoid (price war likely)'
                    elif seller_count >= 20:
                        competition_level = 'high'
                        competition_warning = 'HIGH COMPETITION - Risky (many sellers competing)'
                    elif seller_count >= 10:
                        competition_level = 'moderate'
                        competition_warning = 'MODERATE COMPETITION - Acceptable'
                    elif seller_count >= 5:
                        competition_level = 'low'
                        competition_warning = 'LOW COMPETITION - Good opportunity'
                    else:
                        competition_level = 'very_low'
                        competition_warning = 'VERY LOW COMPETITION - Excellent opportunity'
                
                # Risk Score Calculation (0-10)
                risk_score = 0
                risk_factors = []
                
                # Factor 1: Sales Velocity
                if sales_rank > 100000:
                    risk_score += 3
                    risk_factors.append('Very slow sales')
                elif sales_rank > 50000:
                    risk_score += 2
                    risk_factors.append('Slow sales')
                elif sales_rank > 20000:
                    risk_score += 1
                    risk_factors.append('Moderate sales')
                
                # Factor 2: Competition
                if seller_count >= 50:
                    risk_score += 3
                    risk_factors.append('Very high competition')
                elif seller_count >= 20:
                    risk_score += 2
                    risk_factors.append('High competition')
                elif seller_count >= 10:
                    risk_score += 1
                    risk_factors.append('Moderate competition')
                
                # Factor 3: Price Stability
                if low_90 and high_90 and low_90 > 0:
                    price_range = high_90 - low_90
                    volatility_percent = (price_range / low_90) * 100
                    if volatility_percent > 50:
                        risk_score += 2
                        risk_factors.append('Highly volatile pricing')
                    elif volatility_percent > 25:
                        risk_score += 1
                        risk_factors.append('Somewhat volatile pricing')
                
                # Factor 4: Profitability
                if profit is not None:
                    if profit < 0:
                        risk_score += 2
                        risk_factors.append('Negative profit margin')
                    elif profit < 5:
                        risk_score += 1
                        risk_factors.append('Low profit margin')
                
                # Determine risk level
                if risk_score <= 2:
                    risk_level = 'LOW RISK'
                    risk_color = 'green'
                    risk_recommendation = '✅ Good opportunity'
                elif risk_score <= 4:
                    risk_level = 'MODERATE RISK'
                    risk_color = 'yellow'
                    risk_recommendation = '⚠️ Acceptable with caution'
                elif risk_score <= 6:
                    risk_level = 'HIGH RISK'
                    risk_color = 'orange'
                    risk_recommendation = '⚠️ Proceed carefully'
                else:
                    risk_level = 'VERY HIGH RISK'
                    risk_color = 'red'
                    risk_recommendation = '🔴 Avoid or minimize investment'
                
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
                    'est_sales_per_day': est_sales_per_day,
                    'velocity_category': velocity_category,
                    'velocity_explanation': velocity_explanation,
                    'seller_count': seller_count,
                    'profit': profit,
                    'roi_percent': roi_percent,
                    'break_even_price': break_even_price,
                    'price_vs_avg_percent': price_vs_avg_percent,
                    'price_vs_avg_signal': price_vs_avg_signal,
                    'price_vs_avg_text': price_vs_avg_text,
                    'competition_level': competition_level,
                    'competition_warning': competition_warning,
                    'risk_score': risk_score,
                    'risk_level': risk_level,
                    'risk_color': risk_color,
                    'risk_recommendation': risk_recommendation,
                    'risk_factors': risk_factors,
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
            'seller_count', 'profit', 'roi_percent', 'break_even_price',
            'risk_score', 'risk_level', 'amazon_oos', 'trend', 'processed_date'
        ]
        df = df[[col for col in column_order if col in df.columns]]
        
        # Rename columns for Excel
        df.columns = [
            'Title', 'UPC', 'ASIN', 'Current Price', '30-Day Avg',
            '90-Day Low', '90-Day High', 'Sales Rank', 'Est Sales/Month',
            'Sellers', 'Profit (@$30 cost)', 'ROI %', 'Break-Even Price',
            'Risk Score', 'Risk Level', 'Amazon OOS', 'Trend', 'Processed Date'
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
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
