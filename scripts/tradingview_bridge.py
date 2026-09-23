"""
TradingView Webhook Bridge v3.0.0
"""
import os
import json
import logging
from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'alert_config.json')
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logging.error(f"Error loading config: {e}")
        return {}

config = load_config()
webhook_secret = config.get('tradingview', {}).get('webhook_secret') or os.environ.get('TRADINGVIEW_WEBHOOK_SECRET')
allowed_ips = config.get('tradingview', {}).get('allowed_ips')

if not webhook_secret:
    logging.warning("No webhook secret configured. Accepting all requests.")

@app.route('/webhook', methods=['POST'])
def webhook():
    # IP Whitelist check
    if allowed_ips:
        client_ip = request.remote_addr
        if client_ip not in allowed_ips:
            logging.warning(f"Blocked request from IP: {client_ip}")
            return jsonify({'error': 'Forbidden'}), 403

    # Secret check
    if webhook_secret:
        header_secret = request.headers.get('X-Webhook-Secret')
        json_data = request.get_json(silent=True) or {}
        body_secret = json_data.get('secret')
        
        if header_secret != webhook_secret and body_secret != webhook_secret:
            return jsonify({'error': 'Forbidden'}), 403

    # Payload validation
    json_data = request.get_json(silent=True)
    if not json_data:
        return jsonify({'error': 'Malformed payload'}), 400

    ticker = json_data.get('ticker') or json_data.get('symbol')
    action = json_data.get('action') or json_data.get('direction')

    if not ticker or not action:
        return jsonify({'error': 'Missing required fields: ticker/symbol and action/direction'}), 400
    if not isinstance(ticker, str) or not isinstance(action, str):
        return jsonify({'error': 'ticker and action must be strings'}), 400

    # Process signal here...
    logging.info(f"Received valid signal: {action} on {ticker}")
    return jsonify({'status': 'success'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
