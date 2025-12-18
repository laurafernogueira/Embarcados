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

# --- CONEXÃO FIREBASE (CAMINHO ABSOLUTO RENDER) ---
try:
    if not firebase_admin._apps:
        # No Render, Secret Files são montados obrigatoriamente em /etc/secrets/
        cert_path = '/etc/secrets/firebase-credentials.json'
        
        # Se não encontrar no caminho do Render, tenta no diretório local (fallback)
        if not os.path.exists(cert_path):
            cert_path = os.path.join(os.getcwd(), 'firebase-credentials.json')

        if os.path.exists(cert_path):
            cred = credentials.Certificate(cert_path)
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            firebase_disponivel = True
            print(f"✅ Firebase conectado com sucesso usando: {cert_path}")
        else:
            print(f"❌ Erro: Arquivo não encontrado em {cert_path}")
except Exception as e:
    print(f"💥 Falha ao carregar credenciais: {e}")

# --- CONFIGURAÇÃO MQTT ---
def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        if firebase_disponivel:
            # O Firestore organiza por data se você usar o timestamp enviado pela Raspberry
            db.collection("telemetria").add(payload)
            print("📥 Dado da Raspberry salvo no Firebase!")
    except Exception as e:
        print(f"⚠️ Erro no processamento MQTT: {e}")

mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_message = on_message
mqtt_client.connect("broker.hivemq.com", 1883, 60)
mqtt_client.subscribe("telemetria/+/dados")
mqtt_client.loop_start()

@app.route('/')
def index():
    return send_from_directory('.', 'dashboard.html')

@app.route('/api/dados-recentes')
def dados_recentes():
    if not firebase_disponivel:
        return jsonify({"erro": "Firebase indisponivel no servidor Render", "dados": []}), 500
    try:
        # Busca os 15 mais recentes
        docs = db.collection("telemetria").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(15).get()
        lista = [doc.to_dict() for doc in docs]
        return jsonify({"dados": lista, "total": len(lista)})
    except Exception as e:
        return jsonify({"erro": str(e), "dados": []}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
