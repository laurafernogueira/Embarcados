import os
import json
import paho.mqtt.client as mqtt
import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime

# 1. Configuração do Flask
app = Flask(__name__)
CORS(app)

# 2. Configuração do Firebase
# Certifique-se que o arquivo firebase-credentials.json está na raiz do GitHub
cred = credentials.Certificate("firebase-credentials.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# 3. Configuração do MQTT
BROKER = "broker.hivemq.com"
PORT = 1883
TOPICO = "telemetria/#" # Ouve todos os veículos

def on_connect(client, userdata, flags, rc, properties=None):
    print(f"Conectado ao Broker com código: {rc}")
    client.subscribe(TOPICO)

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        # Salva no Firebase
        db.collection("telemetria").add(payload)
        print(f"Dados salvos do veículo: {payload.get('veiculo_id')}")
    except Exception as e:
        print(f"Erro ao processar mensagem: {e}")

mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect(BROKER, PORT, 60)
mqtt_client.loop_start()

# --- ROTAS DA API ---

@app.route('/')
def index():
    # Serve o arquivo dashboard.html automaticamente
    return send_from_directory('.', 'dashboard.html')

@app.route('/api/status')
def status():
    return jsonify({"status": "online", "mqtt": "conectado", "firebase": "ok"})

@app.route('/api/dados-recentes')
def dados_recentes():
    try:
        docs = db.collection("telemetria").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(20).stream()
        lista_dados = [doc.to_dict() for doc in docs]
        return jsonify({"total": len(lista_dados), "dados": lista_dados})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
