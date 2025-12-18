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

# --- CONFIGURAÇÃO DO FIREBASE (Ajustado para Secret Files do Render) ---
firebase_disponivel = False
db = None

try:
    if not firebase_admin._apps:
        # Tenta o caminho padrão de Secret Files do Render primeiro
        cred_path = '/etc/secrets/firebase-credentials.json'
        
        # Se não existir (teste local), tenta o arquivo na raiz
        if not os.path.exists(cred_path):
            cred_path = 'firebase-credentials.json'
            
        if os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            firebase_disponivel = True
            print(f"✅ Firebase conectado via: {cred_path}")
        else:
            print("❌ Arquivo de credenciais não encontrado.")
except Exception as e:
    print(f"❌ Erro crítico no Firebase: {e}")

# --- CONFIGURAÇÃO DO MQTT ---
BROKER = "broker.hivemq.com"
TOPICO = "telemetria/+/dados"

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        if firebase_disponivel:
            # Salva no Firestore
            db.collection("telemetria").add(payload)
            print(f"📥 Recebido e Salvo: {payload.get('motorista_id')}")
    except Exception as e:
        print(f"❌ Erro MQTT: {e}")

mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_message = on_message
mqtt_client.connect(BROKER, 1883, 60)
mqtt_client.subscribe(TOPICO)
mqtt_client.loop_start()

# --- ROTAS DA API ---

@app.route('/')
def index():
    return send_from_directory('.', 'dashboard.html')

@app.route('/api/dados-recentes')
def dados_recentes():
    try:
        if not firebase_disponivel:
            return jsonify({"erro": "Firebase off", "dados": []}), 500
            
        # Busca os 10 mais recentes para evitar timeout no Render
        docs = db.collection("telemetria")\
                 .order_by("timestamp", direction=firestore.Query.DESCENDING)\
                 .limit(10).get()
        
        lista = []
        for doc in docs:
            d = doc.to_dict()
            # Valida se os campos que o Dashboard precisa existem no documento
            if 'dados' in d and 'classificacao' in d:
                lista.append(d)
                
        return jsonify({"dados": lista})
    except Exception as e:
        return jsonify({"erro": str(e), "dados": []}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
