import os
import json
import random
import paho.mqtt.client as mqtt
import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

# --- CONFIGURAÇÃO DO FIREBASE (Suporte a Secret Files do Render) ---
firebase_disponivel = False
db = None

try:
    if not firebase_admin._apps:
        # Caminho oficial para segredos no Render
        cred_path = '/etc/secrets/firebase-credentials.json'
        
        # Fallback para desenvolvimento local
        if not os.path.exists(cred_path):
            cred_path = 'firebase-credentials.json'
            
        if os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            firebase_disponivel = True
            print(f"✅ Conexão estabelecida: {cred_path}")
        else:
            print("⚠️ Aviso: Credenciais não encontradas. Verifique os Secret Files.")
except Exception as e:
    print(f"❌ Erro Crítico Firebase: {e}")

# --- CONFIGURAÇÃO DO MQTT ---
BROKER = "broker.hivemq.com"
TOPICO = "telemetria/+/dados"

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        if firebase_disponivel:
            # Salva no Firestore com timestamp de servidor caso falte no payload
            if 'timestamp' not in payload:
                payload['timestamp'] = datetime.utcnow().isoformat()
            db.collection("telemetria").add(payload)
    except Exception as e:
        print(f"❌ Erro ao processar MQTT: {e}")

mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_message = on_message
mqtt_client.connect(BROKER, 1883, 60)
mqtt_client.subscribe(TOPICO)
mqtt_client.loop_start()

# --- ROTAS ---

@app.route('/')
def index():
    return send_from_directory('.', 'dashboard.html')

@app.route('/api/dados-recentes')
def dados_recentes():
    try:
        if not firebase_disponivel:
            return jsonify({"dados": []}), 500
            
        # Busca limitada para manter a performance estável
        docs = db.collection("telemetria")\
                 .order_by("timestamp", direction=firestore.Query.DESCENDING)\
                 .limit(10).get()
        
        lista = [doc.to_dict() for doc in docs if 'dados' in doc.to_dict()]
        return jsonify({"dados": lista})
    except Exception as e:
        return jsonify({"erro": str(e), "dados": []}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
