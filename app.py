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

# --- CONFIGURAÇÃO DO FIREBASE ---
firebase_disponivel = False
db = None

def inicializar_firebase():
    global firebase_disponivel, db
    try:
        if not firebase_admin._apps:
            # Lista de caminhos possíveis para o arquivo no Render
            caminhos_tentativa = [
                '/etc/secrets/firebase-credentials.json',
                os.path.join(os.getcwd(), 'firebase-credentials.json'),
                'firebase-credentials.json'
            ]
            
            caminho_final = None
            for caminho in caminhos_tentativa:
                if os.path.exists(caminho):
                    caminho_final = caminho
                    break
            
            if caminho_final:
                cred = credentials.Certificate(caminho_final)
                firebase_admin.initialize_app(cred)
                db = firestore.client()
                firebase_disponivel = True
                print(f"✅ Firebase conectado com sucesso via: {caminho_final}")
            else:
                print("❌ ERRO: Arquivo firebase-credentials.json não encontrado. Verifique os Secret Files no Render.")
    except Exception as e:
        print(f"❌ Falha crítica ao iniciar Firebase: {e}")

inicializar_firebase()

# --- CONFIGURAÇÃO DO MQTT ---
BROKER = "broker.hivemq.com"
TOPICO = "telemetria/+/dados"

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        if firebase_disponivel:
            # Garante que o timestamp exista para o gráfico do dashboard
            if 'timestamp' not in payload:
                payload['timestamp'] = datetime.utcnow().isoformat()
            
            # Salva na coleção telemetria
            db.collection("telemetria").add(payload)
            print(f"📥 Dados salvos no Firebase: {payload.get('motorista_id', 'Motorista Desconhecido')}")
    except Exception as e:
        print(f"❌ Erro ao processar mensagem MQTT: {e}")

mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_message = on_message

try:
    mqtt_client.connect(BROKER, 1883, 60)
    mqtt_client.subscribe(TOPICO)
    mqtt_client.loop_start()
    print(f"📡 MQTT conectado e ouvindo: {TOPICO}")
except Exception as e:
    print(f"⚠️ Erro ao conectar no MQTT: {e}")

# --- ROTAS ---

@app.route('/')
def index():
    return send_from_directory('.', 'dashboard.html')

@app.route('/api/dados-recentes')
def dados_recentes():
    if not firebase_disponivel:
        return jsonify({
            "dados": [], 
            "erro": "Firebase indisponivel. Verifique o arquivo de credenciais no Render.",
            "status": "config_error"
        }), 500
    
    try:
        # Busca os 15 documentos mais recentes
        docs = db.collection("telemetria")\
                 .order_by("timestamp", direction=firestore.Query.DESCENDING)\
                 .limit(15).get()
        
        lista = []
        for doc in docs:
            d = doc.to_dict()
            # Só adiciona à lista se tiver a estrutura de dados esperada
            if 'dados' in d and 'classificacao' in d:
                lista.append(d)
        
        return jsonify({"dados": lista, "total": len(lista)})
    except Exception as e:
        print(f"❌ Erro na consulta Firestore: {e}")
        return jsonify({"erro": str(e), "dados": []}), 500

if __name__ == "__main__":
    # O Render exige que usemos a variável de ambiente PORT
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
