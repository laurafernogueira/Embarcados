import os
import json
import random
import paho.mqtt.client as mqtt
import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime

# 1. Configuração do Flask
app = Flask(__name__)
CORS(app)

# Variáveis globais para monitoramento
mqtt_conectado = False
mensagens_recebidas = 0

# 2. Configuração do Firebase (AJUSTADO PARA RENDER)
try:
    if not firebase_admin._apps:
        # Tenta ler do caminho de Secret Files do Render, se não existir, usa o local
        cred_path = '/etc/secrets/firebase-credentials.json'
        if not os.path.exists(cred_path):
            cred_path = 'firebase-credentials.json'
            
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
    
    db = firestore.client()
    firebase_disponivel = True
    print("✅ Conectado ao Firebase com sucesso!")
except Exception as e:
    print(f"❌ Erro Firebase: {e}")
    firebase_disponivel = False

# 3. Configuração do MQTT
BROKER = "broker.hivemq.com"
PORT = 1883
TOPICO = "telemetria/+/dados" 

def on_connect(client, userdata, flags, rc, properties=None):
    global mqtt_conectado
    if rc == 0:
        mqtt_conectado = True
        client.subscribe(TOPICO)
        print(f"✅ MQTT Conectado! Ouvindo tópico: {TOPICO}")
    else:
        mqtt_conectado = False
        print(f"❌ Falha MQTT código: {rc}")

def on_message(client, userdata, msg):
    global mensagens_recebidas
    try:
        payload = json.loads(msg.payload.decode())
        
        # Garante timestamp para o gráfico
        if 'timestamp' not in payload:
            payload['timestamp'] = datetime.utcnow().isoformat()
        
        if firebase_disponivel:
            db.collection("telemetria").add(payload)
            mensagens_recebidas += 1
            print(f"📥 Dados salvos: {payload.get('motorista_id', 'Desconhecido')}")
            
    except Exception as e:
        print(f"❌ Erro ao processar mensagem: {e}")

# Cliente MQTT
client_id = f'render-backend-{random.randint(1000, 9999)}'
mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

try:
    mqtt_client.connect(BROKER, PORT, 60)
    mqtt_client.loop_start()
except Exception as e:
    print(f"⚠️ MQTT indisponível: {e}")

# --- ROTAS ---

@app.route('/')
def index():
    return send_from_directory('.', 'dashboard.html')

@app.route('/api/status')
def status():
    return jsonify({
        "status": "online",
        "mqtt_conectado": mqtt_conectado,
        "firebase_disponivel": firebase_disponivel,
        "mensagens_recebidas": mensagens_recebidas
    })

@app.route('/api/dados-recentes')
def dados_recentes():
    try:
        if not firebase_disponivel:
            return jsonify({"erro": "Firebase indisponível", "dados": []}), 500
            
        # Busca apenas os 10 mais recentes para não travar a memória do Render
        docs = db.collection("telemetria")\
                 .order_by("timestamp", direction=firestore.Query.DESCENDING)\
                 .limit(10)\
                 .get()
        
        lista = []
        for doc in docs:
            d = doc.to_dict()
            # Filtro para garantir que os dados essenciais para o gráfico existam
            if 'motorista_id' in d and 'dados' in d:
                lista.append(d)
                
        return jsonify({"total": len(lista), "dados": lista})
    except Exception as e:
        print(f"❌ Erro na consulta Firestore: {e}")
        return jsonify({"erro": str(e), "dados": []}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
