from http.server import BaseHTTPRequestHandler
import json
import os
import pandas as pd
from pathlib import Path
from urllib.parse import unquote, parse_qs, urlparse
import logging
from typing import Dict, List, Any, Optional
import traceback

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add import for PayinCalculator
from calculator import PayinCalculator

class PayinCalculatorHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.df = None
        self.initialize_data()
        super().__init__(*args, **kwargs)
    
    def initialize_data(self):
        """Load and clean the Excel data"""
        try:
            # Try different possible paths for the Excel file
            possible_paths = [
                Path(__file__).parent.parent / "Payin.xlsx",
                Path(__file__).parent / "Payin.xlsx",
                Path("Payin.xlsx"),
                Path("/tmp/Payin.xlsx")
            ]
            
            excel_path = None
            for path in possible_paths:
                if path.exists():
                    excel_path = path
                    break
            
            if excel_path is None:
                logger.error("Excel file 'Payin.xlsx' not found in any expected location")
                return
            
            logger.info(f"Loading Excel file from: {excel_path}")
            df = pd.read_excel(excel_path)
            
            # Clean column names
            df.columns = df.columns.str.strip()
            
            # Clean string columns
            string_columns = ['Lenders', 'Product', 'Region']
            for col in string_columns:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.strip()
            
            # Convert numeric columns
            numeric_columns = ['Lower Slab (In Cr.)', 'Higher Slab (In Cr.)']
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Remove rows with all NaN values
            df = df.dropna(how='all')
            
            self.df = df
            logger.info(f"Successfully loaded {len(df)} rows from Excel file")
            
        except Exception as e:
            logger.error(f"Error loading Excel file: {str(e)}")
            logger.error(traceback.format_exc())
            self.df = None
    
    def send_json_response(self, data: Any, status_code: int = 200):
        """Send JSON response with proper headers"""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()
        
        try:
            response_json = json.dumps(data, ensure_ascii=False, indent=2)
            self.wfile.write(response_json.encode('utf-8'))
        except Exception as e:
            logger.error(f"Error encoding JSON response: {str(e)}")
            error_response = json.dumps({"detail": "Internal server error"})
            self.wfile.write(error_response.encode('utf-8'))
    
    def send_error_response(self, message: str, status_code: int = 500):
        """Send error response"""
        self.send_json_response({"detail": message}, status_code)
    
    def do_OPTIONS(self):
        """Handle CORS preflight requests"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()
    
    def do_GET(self):
        """Handle GET requests"""
        try:
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            query_params = parse_qs(parsed_url.query)
            
            # Remove /api prefix if present
            if path.startswith('/api'):
                path = path[4:]
            
            if path == '/data/' or path == '/data':
                self.get_data()
            elif path.startswith('/products/'):
                lender = unquote(path.split('/')[2])
                self.get_products(lender)
            elif path.startswith('/regions/'):
                parts = path.split('/')
                if len(parts) >= 4:
                    lender = unquote(parts[2])
                    product = unquote(parts[3])
                    self.get_regions(lender, product)
                else:
                    self.send_error_response("Invalid regions endpoint format", 400)
            elif path == '/health' or path == '/health/':
                self.health_check()
            elif path == '/' or path == '':
                self.send_json_response({"message": "Payin Calculator API", "status": "running"})
            else:
                self.send_error_response("Endpoint not found", 404)
                
        except Exception as e:
            logger.error(f"Error in GET request: {str(e)}")
            logger.error(traceback.format_exc())
            self.send_error_response("Internal server error", 500)
    
    def do_POST(self):
        """Handle POST requests"""
        try:
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            
            # Remove /api prefix if present
            if path.startswith('/api'):
                path = path[4:]
            
            if path == '/calculate/' or path == '/calculate':
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length == 0:
                    self.send_error_response("No data provided", 400)
                    return
                
                post_data = self.rfile.read(content_length)
                try:
                    data = json.loads(post_data.decode('utf-8'))
                    self.calculate_payin(data)
                except json.JSONDecodeError as e:
                    self.send_error_response(f"Invalid JSON: {str(e)}", 400)
            else:
                self.send_error_response("Endpoint not found", 404)
                
        except Exception as e:
            logger.error(f"Error in POST request: {str(e)}")
            logger.error(traceback.format_exc())
            self.send_error_response("Internal server error", 500)
    
    def get_data(self):
        """Get all lenders, products, and regions"""
        if self.df is None:
            self.send_error_response("Excel data not loaded", 500)
            return
        
        try:
            lenders = sorted([x for x in self.df['Lenders'].dropna().unique() if str(x).strip() != ''])
            products = sorted([x for x in self.df['Product'].dropna().unique() if str(x).strip() != ''])
            regions = sorted([x for x in self.df['Region'].dropna().unique() if str(x).strip() != ''])
            
            response_data = {
                "status": "success",
                "data": {
                    "lenders": lenders,
                    "products": products,
                    "regions": regions
                }
            }
            
            self.send_json_response(response_data)
            
        except Exception as e:
            logger.error(f"Error in get_data: {str(e)}")
            self.send_error_response("Error retrieving data", 500)
    
    def get_products(self, lender: str):
        """Get products for a specific lender"""
        if self.df is None:
            self.send_error_response("Excel data not loaded", 500)
            return
        
        try:
            filtered_df = self.df[self.df['Lenders'].str.strip() == lender.strip()]
            
            if filtered_df.empty:
                self.send_json_response({
                    "status": "success",
                    "data": {
                        "lender": lender,
                        "products": []
                    }
                })
                return
            
            products = sorted([x for x in filtered_df['Product'].dropna().unique() if str(x).strip() != ''])
            
            response_data = {
                "status": "success",
                "data": {
                    "lender": lender,
                    "products": products
                }
            }
            
            self.send_json_response(response_data)
            
        except Exception as e:
            logger.error(f"Error in get_products: {str(e)}")
            self.send_error_response("Error retrieving products", 500)
    
    def get_regions(self, lender: str, product: str):
        """Get regions for a specific lender and product"""
        if self.df is None:
            self.send_error_response("Excel data not loaded", 500)
            return
        
        try:
            filtered_df = self.df[
                (self.df['Lenders'].str.strip() == lender.strip()) &
                (self.df['Product'].str.strip() == product.strip())
            ]
            
            if filtered_df.empty:
                self.send_json_response({
                    "status": "success",
                    "data": {
                        "lender": lender,
                        "product": product,
                        "regions": []
                    }
                })
                return
            
            regions = sorted([x for x in filtered_df['Region'].dropna().unique() if str(x).strip() != ''])
            
            response_data = {
                "status": "success",
                "data": {
                    "lender": lender,
                    "product": product,
                    "regions": regions
                }
            }
            
            self.send_json_response(response_data)
            
        except Exception as e:
            logger.error(f"Error in get_regions: {str(e)}")
            self.send_error_response("Error retrieving regions", 500)
    
    def calculate_payin(self, data: Dict[str, Any]):
        """Calculate payin amount based on the provided parameters"""
        if self.df is None:
            self.send_error_response("Excel data not loaded", 500)
            return
        
        try:
            # Extract parameters
            lender = data.get('lender', '').strip()
            product = data.get('product', '').strip()
            region = data.get('region', '').strip()
            amount = data.get('amount')
            
            # Validate required parameters
            if not all([lender, product, region]):
                self.send_error_response("Missing required parameters: lender, product, region", 400)
                return
            
            if amount is None:
                self.send_error_response("Missing required parameter: amount", 400)
                return
            
            try:
                amount = float(amount)
            except (ValueError, TypeError):
                self.send_error_response("Amount must be a valid number", 400)
                return
            
            # Filter data based on parameters
            filtered_df = self.df[
                (self.df['Lenders'].str.strip() == lender) &
                (self.df['Product'].str.strip() == product) &
                (self.df['Region'].str.strip() == region)
            ]
            
            if filtered_df.empty:
                self.send_error_response(
                    f"No data found for lender: {lender}, product: {product}, region: {region}", 
                    404
                )
                return
            
            # Find the appropriate slab
            payin_amount = None
            matched_row = None
            
            for _, row in filtered_df.iterrows():
                lower_slab = row.get('Lower Slab (In Cr.)', 0)
                higher_slab = row.get('Higher Slab (In Cr.)', float('inf'))
                
                # Handle NaN values
                if pd.isna(lower_slab):
                    lower_slab = 0
                if pd.isna(higher_slab):
                    higher_slab = float('inf')
                
                # Check if amount falls within this slab
                if lower_slab <= amount <= higher_slab:
                    # Calculate payin amount based on available columns
                    payin_columns = [col for col in row.index if 'payin' in col.lower() or 'amount' in col.lower()]
                    
                    if payin_columns:
                        payin_amount = row[payin_columns[0]]
                    else:
                        # If no specific payin column, look for percentage or rate columns
                        rate_columns = [col for col in row.index if any(keyword in col.lower() for keyword in ['rate', 'percentage', '%'])]
                        if rate_columns:
                            rate = row[rate_columns[0]]
                            if not pd.isna(rate):
                                payin_amount = amount * (rate / 100) if rate > 1 else amount * rate
                    
                    matched_row = row
                    break
            
            if payin_amount is None:
                self.send_error_response(
                    f"No matching slab found for amount {amount} Cr", 
                    404
                )
                return
            
            # Prepare response
            response_data = {
                "status": "success",
                "data": {
                    "lender": lender,
                    "product": product,
                    "region": region,
                    "input_amount": amount,
                    "payin_amount": float(payin_amount) if not pd.isna(payin_amount) else 0,
                    "slab_info": {
                        "lower_slab": float(matched_row['Lower Slab (In Cr.)']) if not pd.isna(matched_row['Lower Slab (In Cr.)']) else 0,
                        "higher_slab": float(matched_row['Higher Slab (In Cr.)']) if not pd.isna(matched_row['Higher Slab (In Cr.)']) else None
                    }
                }
            }
            
            self.send_json_response(response_data)
            
        except Exception as e:
            logger.error(f"Error in calculate_payin: {str(e)}")
            logger.error(traceback.format_exc())
            self.send_error_response("Error calculating payin amount", 500)
    
    def health_check(self):
        """Health check endpoint"""
        try:
            status = "healthy" if self.df is not None else "unhealthy"
            data_status = f"{len(self.df)} rows loaded" if self.df is not None else "No data loaded"
            
            response_data = {
                "status": status,
                "message": "Payin Calculator API",
                "data_status": data_status,
                "timestamp": pd.Timestamp.now().isoformat()
            }
            
            status_code = 200 if status == "healthy" else 503
            self.send_json_response(response_data, status_code)
            
        except Exception as e:
            logger.error(f"Error in health_check: {str(e)}")
            self.send_error_response("Health check failed", 500)

# Vercel handler function
def handler(request, response):
    """Main handler function for Vercel"""
    return PayinCalculatorHandler(request, response)

# For direct execution (development)
if __name__ == "__main__":
    from http.server import HTTPServer
    
    server = HTTPServer(('localhost', 8000), PayinCalculatorHandler)
    print("Server running on http://localhost:8000")
    server.serve_forever()
