import os
import json
import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import paho.mqtt.client as mqtt

app = Flask(__name__)
CORS(app)

firebase_disponivel = False
db = None

# TENTATIVA DE CONEXÃO MULTI-CAMINHO
try:
    if not firebase_admin._apps:
        # Lista de locais onde o Render pode ter escondido seu arquivo
        paths = [
            '/etc/secrets/firebase-credentials.json',
            os.path.join(os.getcwd(), 'firebase-credentials.json'),
            'firebase-credentials.json',
            '../firebase-credentials.json'
        ]
        
        cred = None
        for p in paths:
            if os.path.exists(p):
                print(f"🔎 Arquivo encontrado em: {p}")
                cred = credentials.Certificate(p)
                break
        
        if cred:
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            firebase_disponivel = True
            print("✅ FIREBASE CONECTADO COM SUCESSO!")
        else:
            print("❌ NENHUM ARQUIVO DE CHAVE ENCONTRADO NO SERVIDOR!")
except Exception as e:
    print(f"💥 Erro ao carregar Firebase: {e}")

# --- CONFIGURAÇÃO MQTT ---
def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        if firebase_disponivel:
            db.collection("telemetria").add(payload)
            print("📥 Dado salvo no banco!")
    except: pass

mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_message = on_message
mqtt_client.connect("broker.hivemq.com", 1883, 60)
mqtt_client.subscribe("telemetria/+/dados")
mqtt_client.loop_start()

@app.route('/')
def index(): return send_from_directory('.', 'dashboard.html')

@app.route('/api/dados-recentes')
def dados_recentes():
    if not firebase_disponivel:
        return jsonify({"erro": "Firebase ainda offline no servidor", "dados": []}), 500
    try:
        docs = db.collection("telemetria").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(15).get()
        lista = [doc.to_dict() for doc in docs]
        return jsonify({"dados": lista})
    except Exception as e:
        return jsonify({"erro": str(e), "dados": []}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
