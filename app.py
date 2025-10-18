"""
Keepa Batch Processor - Optimized for 20 Tokens/Minute Plan
Processes games efficiently with the €49/month API plan
For 2000 games: ~100 minutes total processing time
"""

import keepa
import pandas as pd
import time
from datetime import datetime, timedelta
import json
import os

# ============================================
# CONFIGURATION - OPTIMIZED FOR 20 TOKENS/MIN
# ============================================
KEEPA_API_KEY = 'YOUR_KEEPA_API_KEY_HERE'  # ⬅️ PASTE YOUR API KEY HERE
BATCH_SIZE = 20  # Process 20 games at a time (matches your token limit)
WAIT_MINUTES = 1  # Wait 1 minute between batches for tokens to regenerate
OUTPUT_FILE = 'game_arbitrage_results.xlsx'
PROGRESS_FILE = 'processing_progress.json'

# ============================================
# YOUR 13 UPCs FOR PROOF OF CONCEPT
# ============================================
UPCS_TO_PROCESS = [
    '083717203599',
    '045496598969',
    '045496590420',
    '045496596583',
    '045496598044',
    '045496592998',
    '045496596545',
    '045496597092',
    '810136672695',
    '047875882256',
    '710425578649',
    '710425570322',
    '887256110130'
]

def save_progress(batch_num, total_batches, completed_upcs):
    """Save progress to resume if script is interrupted"""
    progress = {
        'batch_num': batch_num,
        'total_batches': total_batches,
        'completed_upcs': completed_upcs,
        'last_updated': datetime.now().isoformat()
    }
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f)
    print(f"✓ Progress saved (Batch {batch_num}/{total_batches})")

def load_progress():
    """Load progress from previous run"""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    return None

def process_batch(api, batch_upcs, batch_num, total_batches):
    """
    Process a single batch of UPCs
    """
    print(f"\n{'='*60}")
    print(f"Processing Batch {batch_num}/{total_batches}")
    print(f"UPCs in this batch: {len(batch_upcs)}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    results = []
    errors = []
    
    try:
        # Query Keepa API
        print("→ Querying Keepa API...")
        products = api.query(
            batch_upcs,
            product_code_is_asin=False,
            history=True,
            stats=90,
            offers=20
        )
        
        # Process each product
        for idx, product in enumerate(products):
            upc = batch_upcs[idx]
            
            if not product:
                errors.append({
                    'upc': upc,
                    'error': 'Product not found'
                })
                print(f"  ✗ {upc}: Not found")
                continue
            
            try:
                # Extract price data
                current_price = None
                price_history = []
                
                if 'data' in product and 'NEW' in product['data']:
                    prices = product['data']['NEW']
                    if prices and len(prices) > 0:
                        current_price = prices[-1] / 100
                        price_history = [p/100 for p in prices if p is not None and p > 0]
                
                # Calculate stats
                low_90 = min(price_history) if price_history else None
                high_90 = max(price_history) if price_history else None
                avg_30 = sum(price_history[-30:]) / len(price_history[-30:]) if len(price_history) >= 30 else current_price
                
                # Get sales rank
                sales_rank = product.get('salesRank', 999999)
                if isinstance(sales_rank, list) and len(sales_rank) > 0:
                    sales_rank = sales_rank[-1] if sales_rank[-1] > 0 else 999999
                
                # Estimate monthly sales
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
                
                # Determine trend
                trend = 'stable'
                if len(price_history) >= 10:
                    recent_avg = sum(price_history[-5:]) / 5
                    older_avg = sum(price_history[-10:-5]) / 5
                    if recent_avg > older_avg * 1.05:
                        trend = 'rising'
                    elif recent_avg < older_avg * 0.95:
                        trend = 'falling'
                
                # Calculate profit
                if current_price:
                    buy_cost = 30
                    amazon_fee = current_price * 0.15
                    fba_fee = 3.99
                    shipping = 2.00
                    profit = current_price - buy_cost - amazon_fee - fba_fee - shipping
                else:
                    profit = None
                
                result = {
                    'UPC': upc,
                    'Title': product.get('title', 'Unknown'),
                    'ASIN': product.get('asin', ''),
                    'Current Price': current_price,
                    '30-Day Avg': avg_30,
                    '90-Day Low': low_90,
                    '90-Day High': high_90,
                    'Sales Rank': sales_rank,
                    'Est Sales/Month': est_sales,
                    'Sellers': seller_count,
                    'Profit (@$30 cost)': profit,
                    'Amazon OOS': amazon_oos,
                    'Trend': trend,
                    'Processed Date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                
                results.append(result)
                print(f"  ✓ {upc}: ${current_price} - {product.get('title', 'Unknown')[:40]}")
                
            except Exception as e:
                errors.append({
                    'upc': upc,
                    'error': str(e)
                })
                print(f"  ✗ {upc}: Error - {str(e)}")
        
        print(f"\n✓ Batch complete: {len(results)} successful, {len(errors)} errors")
        
    except Exception as e:
        print(f"\n✗ Batch failed: {str(e)}")
        for upc in batch_upcs:
            errors.append({
                'upc': upc,
                'error': f'Batch error: {str(e)}'
            })
    
    return results, errors

def main():
    """
    Main processing loop
    """
    print("\n" + "="*60)
    print("KEEPA BATCH PROCESSOR - PROOF OF CONCEPT")
    print("="*60)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Initialize API
    if KEEPA_API_KEY == 'YOUR_KEEPA_API_KEY_HERE':
        print("\n✗ ERROR: Please set your KEEPA_API_KEY in line 14!")
        return
    
    try:
        api = keepa.Keepa(KEEPA_API_KEY)
        print("✓ Connected to Keepa API")
    except Exception as e:
        print(f"✗ Failed to connect to Keepa API: {e}")
        return
    
    # Load UPCs
    upcs = UPCS_TO_PROCESS
    print(f"✓ Loaded {len(upcs)} UPCs to process")
    
    # Check for previous progress
    progress = load_progress()
    start_batch = 1
    all_results = []
    all_errors = []
    
    if progress:
        print(f"\n→ Found previous progress from {progress['last_updated']}")
        print(f"  Last completed batch: {progress['batch_num']}/{progress['total_batches']}")
        response = input("Resume from where you left off? (y/n): ")
        if response.lower() == 'y':
            start_batch = progress['batch_num'] + 1
            # Load existing results
            if os.path.exists(OUTPUT_FILE):
                existing_df = pd.read_excel(OUTPUT_FILE, sheet_name='Game Data')
                all_results = existing_df.to_dict('records')
                print(f"✓ Loaded {len(all_results)} existing results")
    
    # Split into batches
    total_batches = (len(upcs) + BATCH_SIZE - 1) // BATCH_SIZE
    
    print(f"\n{'='*60}")
    print(f"PROCESSING PLAN:")
    print(f"  Total UPCs: {len(upcs)}")
    print(f"  Batch size: {BATCH_SIZE}")
    print(f"  Total batches: {total_batches}")
    print(f"  Starting from batch: {start_batch}")
    print(f"  Estimated time: ~2 minutes (all in one batch!)")
    print(f"{'='*60}\n")
    
    # Process each batch
    for batch_num in range(start_batch, total_batches + 1):
        start_idx = (batch_num - 1) * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, len(upcs))
        batch_upcs = upcs[start_idx:end_idx]
        
        # Process batch
        results, errors = process_batch(api, batch_upcs, batch_num, total_batches)
        all_results.extend(results)
        all_errors.extend(errors)
        
        # Save progress
        save_progress(batch_num, total_batches, len(all_results))
        
        # Save results to Excel
        if all_results:
            df = pd.DataFrame(all_results)
            with pd.ExcelWriter(OUTPUT_FILE, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Game Data', index=False)
                if all_errors:
                    errors_df = pd.DataFrame(all_errors)
                    errors_df.to_excel(writer, sheet_name='Errors', index=False)
            print(f"✓ Results saved to {OUTPUT_FILE}")
        
        # Wait before next batch (unless it's the last batch)
        if batch_num < total_batches:
            next_batch_time = datetime.now() + timedelta(minutes=WAIT_MINUTES)
            print(f"\n⏳ Waiting {WAIT_MINUTES} minutes for tokens to regenerate...")
            print(f"   Next batch starts at: {next_batch_time.strftime('%H:%M:%S')}")
            print(f"   Press Ctrl+C to pause (progress is saved)")
            
            try:
                time.sleep(WAIT_MINUTES * 60)
            except KeyboardInterrupt:
                print("\n\n⏸ Processing paused by user")
                print(f"✓ Progress saved. Run script again to resume from Batch {batch_num + 1}")
                return
    
    # Final summary
    print("\n" + "="*60)
    print("PROCESSING COMPLETE!")
    print("="*60)
    print(f"Total processed: {len(all_results)}")
    print(f"Total errors: {len(all_errors)}")
    print(f"Success rate: {len(all_results) / len(upcs) * 100:.1f}%")
    print(f"Results saved to: {OUTPUT_FILE}")
    print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    # Clean up progress file
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)

if __name__ == '__main__':
    main()
