@app.route('/')
def index():
    return send_from_directory('.', 'dashboard.html')
import os
import json
import random
import paho.mqtt.client as mqtt
import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

# 1. Configuração do Flask
app = Flask(__name__)
CORS(app)

# Variáveis globais para monitoramento no Dashboard
mqtt_conectado = False
mensagens_recebidas = 0

# 2. Configuração do Firebase
try:
    if not firebase_admin._apps:
        # O arquivo firebase-credentials.json deve estar na raiz do seu GitHub
        cred = credentials.Certificate("firebase-credentials.json")
        firebase_admin.initialize_app(cred)
    db = firestore.client()
    firebase_disponivel = True
except Exception as e:
    print(f"Erro ao conectar no Firebase: {e}")
    firebase_disponivel = False

# 3. Configuração do MQTT
BROKER = "broker.hivemq.com"
PORT = 1883
TOPICO = "telemetria/#"

def on_connect(client, userdata, flags, rc, properties=None):
    global mqtt_conectado
    if rc == 0:
        mqtt_conectado = True
        client.subscribe(TOPICO)
        print("✅ Backend conectado ao Broker MQTT e inscrito no tópico.")
    else:
        print(f"❌ Falha na conexão MQTT. Código: {rc}")
        mqtt_conectado = False

def on_message(client, userdata, msg):
    global mensagens_recebidas
    try:
        payload = json.loads(msg.payload.decode())
        # Salva o dado no Firestore dentro da coleção 'telemetria'
        db.collection("telemetria").add(payload)
        mensagens_recebidas += 1
        print(f"📥 Dado recebido e salvo: {payload.get('veiculo_id')}")
    except Exception as e:
        print(f"Erro ao processar mensagem MQTT: {e}")

# Criar cliente MQTT com ID aleatório para evitar conflitos no Render
client_id = f'render-backend-{random.randint(1000, 9999)}'
mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

# Inicia o loop MQTT em uma thread separada para não travar o Flask
try:
    mqtt_client.connect(BROKER, PORT, 60)
    mqtt_client.loop_start()
except Exception as e:
    print(f"⚠️ Erro ao iniciar MQTT: {e}. O site continuará rodando.")

# 4. Rotas do Servidor
@app.route('/')
def index():
    """Serve a página principal do Dashboard"""
    return send_from_directory('.', 'dashboard.html')

@app.route('/api/status')
def status():
    """Rota para verificar se o motor do sistema está ok"""
    return jsonify({
        "status": "online",
        "mqtt_conectado": mqtt_conectado,
        "firebase_disponivel": firebase_disponivel,
        "mensagens_recebidas": mensagens_recebidas
    })

@app.route('/api/dados-recentes')
def dados_recentes():
    """Busca os últimos 10 registros do Firebase para o gráfico"""
    try:
        if not firebase_disponivel:
            return jsonify({"erro": "Firebase indisponível"}), 500
            
        docs = db.collection("telemetria").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(10).stream()
        lista_dados = [doc.to_dict() for doc in docs]
        return jsonify({"total": len(lista_dados), "dados": lista_dados})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

# 5. Inicialização do Servidor (Configuração de Porta para o Render)
if __name__ == "__main__":
    # O Render fornece a porta dinamicamente via variável de ambiente PORT
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
