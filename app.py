"""
BACKEND NA NUVEM
Recebe dados via MQTT → Salva no Firebase → Serve API para Seguradoras

Deploy: Heroku, AWS EC2, DigitalOcean, Google Cloud Run
"""

import paho.mqtt.client as mqtt
import json
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from flask_cors import CORS
from threading import Thread
import time

# Firebase
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_DISPONIVEL = True
except:
    FIREBASE_DISPONIVEL = False

app = Flask(__name__)
CORS(app)


# =====================================================
# 1. MQTT SUBSCRIBER (Recebe dados do Raspberry Pi)
# =====================================================

class MQTTSubscriber:
    """Recebe dados via MQTT e salva no Firebase"""
    
    def __init__(self, broker="broker.hivemq.com", port=1883):
        self.broker = broker
        self.port = port
        self.client = mqtt.Client("backend_nuvem")
        self.conectado = False
        self.mensagens_recebidas = 0
        
        # Firebase
        self.db = None
        self.inicializar_firebase()
        
        # Callbacks MQTT
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
    
    def inicializar_firebase(self):
        """Inicializa Firebase"""
        if not FIREBASE_DISPONIVEL:
            print("⚠ Firebase não disponível")
            return
        
        try:
            # Verificar se já inicializado
            if not firebase_admin._apps:
                cred = credentials.Certificate('firebase-credentials.json')
                firebase_admin.initialize_app(cred)
            
            self.db = firestore.client()
            print("✅ Firebase inicializado")
            
        except Exception as e:
            print(f"❌ Erro ao inicializar Firebase: {e}")
    
    def on_connect(self, client, userdata, flags, rc):
        """Callback quando conecta ao broker"""
        if rc == 0:
            self.conectado = True
            print(f"✅ MQTT conectado ao broker: {self.broker}")
            
            # Subscrever aos tópicos
            self.client.subscribe("telemetria/+/dados", qos=1)
            print("📡 Subscrito a: telemetria/+/dados")
            
        else:
            print(f"❌ MQTT falha na conexão. Código: {rc}")
    
    def on_disconnect(self, client, userdata, rc):
        """Callback quando desconecta"""
        self.conectado = False
        print(f"⚠ MQTT desconectado. Código: {rc}")
        
        # Tentar reconectar
        if rc != 0:
            print("🔄 Tentando reconectar...")
            time.sleep(5)
            try:
                self.conectar()
            except:
                pass
    
    def on_message(self, client, userdata, msg):
        """Callback quando recebe mensagem"""
        try:
            self.mensagens_recebidas += 1
            
            # Parsear payload
            payload = json.loads(msg.payload.decode())
            
            # Extrair informações
            veiculo_id = payload.get('veiculo_id', 'desconhecido')
            timestamp = payload.get('timestamp', datetime.now().isoformat())
            classificacao = payload.get('classificacao', {}).get('classificacao', 'desconhecido')
            
            # Log
            print(f"📨 [{datetime.now().strftime('%H:%M:%S')}] "
                  f"Recebido de {veiculo_id} | "
                  f"Classe: {classificacao.upper()}")
            
            # Salvar no Firebase
            if self.db:
                self.salvar_firebase(payload)
            
        except Exception as e:
            print(f"❌ Erro ao processar mensagem: {e}")
    
    def salvar_firebase(self, payload):
        """Salva dados no Firebase"""
        try:
            # Gerar ID único
            doc_id = f"{payload.get('veiculo_id')}_{int(time.time() * 1000)}"
            
            # Salvar na coleção 'telemetria'
            doc_ref = self.db.collection('telemetria').document(doc_id)
            doc_ref.set({
                'veiculo_id': payload.get('veiculo_id'),
                'motorista_id': payload.get('motorista_id'),
                'timestamp': payload.get('timestamp'),
                'dados_obd': payload.get('dados_obd', {}),
                'classificacao': payload.get('classificacao', {}),
                'processado_local': payload.get('processado_local', False),
                'recebido_em': datetime.now().isoformat()
            })
            
            # Atualizar estatísticas do veículo
            self.atualizar_estatisticas_veiculo(payload)
            
        except Exception as e:
            print(f"❌ Erro ao salvar no Firebase: {e}")
    
    def atualizar_estatisticas_veiculo(self, payload):
        """Atualiza estatísticas agregadas do veículo"""
        try:
            veiculo_id = payload.get('veiculo_id')
            classificacao = payload.get('classificacao', {}).get('classificacao', 'desconhecido')
            
            # Referência do documento de estatísticas
            stats_ref = self.db.collection('estatisticas_veiculos').document(veiculo_id)
            
            # Obter estatísticas atuais
            stats_doc = stats_ref.get()
            
            if stats_doc.exists:
                stats = stats_doc.to_dict()
            else:
                stats = {
                    'total_leituras': 0,
                    'seguro': 0,
                    'moderado': 0,
                    'arriscado': 0,
                    'primeira_leitura': datetime.now().isoformat(),
                    'ultima_leitura': datetime.now().isoformat()
                }
            
            # Atualizar contadores
            stats['total_leituras'] += 1
            if classificacao in ['seguro', 'moderado', 'arriscado']:
                stats[classificacao] = stats.get(classificacao, 0) + 1
            stats['ultima_leitura'] = datetime.now().isoformat()
            
            # Calcular percentuais
            total = stats['total_leituras']
            stats['percentual_seguro'] = (stats.get('seguro', 0) / total) * 100
            stats['percentual_moderado'] = (stats.get('moderado', 0) / total) * 100
            stats['percentual_arriscado'] = (stats.get('arriscado', 0) / total) * 100
            
            # Classificação geral
            if stats['percentual_arriscado'] > 30:
                stats['classificacao_geral'] = 'arriscado'
            elif stats['percentual_moderado'] > 50:
                stats['classificacao_geral'] = 'moderado'
            else:
                stats['classificacao_geral'] = 'seguro'
            
            # Salvar
            stats_ref.set(stats)
            
        except Exception as e:
            print(f"❌ Erro ao atualizar estatísticas: {e}")
    
    def conectar(self):
        """Conecta ao broker MQTT"""
        print(f"🔌 Conectando ao MQTT broker...")
        print(f"   Broker: {self.broker}:{self.port}")
        
        try:
            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()  # Thread separada
            
            # Aguardar conexão
            timeout = 10
            while not self.conectado and timeout > 0:
                time.sleep(0.5)
                timeout -= 0.5
            
            return self.conectado
            
        except Exception as e:
            print(f"❌ Erro ao conectar MQTT: {e}")
            return False
    
    def desconectar(self):
        """Desconecta"""
        self.client.loop_stop()
        self.client.disconnect()
        print("🔌 MQTT desconectado")


# =====================================================
# 2. API REST PARA SEGURADORAS
# =====================================================

mqtt_sub = None

def inicializar_mqtt():
    """Inicializa subscriber MQTT em thread separada"""
    global mqtt_sub
    
    mqtt_sub = MQTTSubscriber(
        broker="broker.hivemq.com",  # Mesmo broker do Raspberry Pi
        port=1883
    )
    
    if mqtt_sub.conectar():
        print("✅ Backend pronto para receber dados via MQTT")
    else:
        print("⚠ Backend iniciando sem MQTT (apenas API)")


# Inicializar MQTT em thread separada
Thread(target=inicializar_mqtt, daemon=True).start()


@app.route('/api/status', methods=['GET'])
def status():
    """Status do backend"""
    return jsonify({
        'status': 'online',
        'mqtt_conectado': mqtt_sub.conectado if mqtt_sub else False,
        'mensagens_recebidas': mqtt_sub.mensagens_recebidas if mqtt_sub else 0,
        'firebase_disponivel': FIREBASE_DISPONIVEL,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/dados-recentes', methods=['GET'])
def dados_recentes():
    """Obtém dados recentes do Firebase"""
    if not mqtt_sub or not mqtt_sub.db:
        return jsonify({'erro': 'Firebase não disponível'}), 503
    
    try:
        limite = request.args.get('limite', 100, type=int)
        veiculo_id = request.args.get('veiculo_id', None)
        
        # Query
        query = mqtt_sub.db.collection('telemetria') \
            .order_by('timestamp', direction=firestore.Query.DESCENDING) \
            .limit(limite)
        
        if veiculo_id:
            query = query.where('veiculo_id', '==', veiculo_id)
        
        docs = query.stream()
        
        dados = []
        for doc in docs:
            dados.append(doc.to_dict())
        
        return jsonify({
            'sucesso': True,
            'total': len(dados),
            'dados': dados
        })
        
    except Exception as e:
        return jsonify({'erro': str(e)}), 500


@app.route('/api/veiculo/<veiculo_id>/estatisticas', methods=['GET'])
def estatisticas_veiculo(veiculo_id):
    """Estatísticas de um veículo específico"""
    if not mqtt_sub or not mqtt_sub.db:
        return jsonify({'erro': 'Firebase não disponível'}), 503
    
    try:
        doc_ref = mqtt_sub.db.collection('estatisticas_veiculos').document(veiculo_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return jsonify({'erro': 'Veículo não encontrado'}), 404
        
        return jsonify({
            'sucesso': True,
            'veiculo_id': veiculo_id,
            'estatisticas': doc.to_dict()
        })
        
    except Exception as e:
        return jsonify({'erro': str(e)}), 500


@app.route('/api/veiculos', methods=['GET'])
def listar_veiculos():
    """Lista todos os veículos monitorados"""
    if not mqtt_sub or not mqtt_sub.db:
        return jsonify({'erro': 'Firebase não disponível'}), 503
    
    try:
        docs = mqtt_sub.db.collection('estatisticas_veiculos').stream()
        
        veiculos = []
        for doc in docs:
            data = doc.to_dict()
            data['veiculo_id'] = doc.id
            veiculos.append(data)
        
        return jsonify({
            'sucesso': True,
            'total': len(veiculos),
            'veiculos': veiculos
        })
        
    except Exception as e:
        return jsonify({'erro': str(e)}), 500


@app.route('/api/dashboard/resumo', methods=['GET'])
def dashboard_resumo():
    """Resumo geral para dashboard"""
    if not mqtt_sub or not mqtt_sub.db:
        return jsonify({'erro': 'Firebase não disponível'}), 503
    
    try:
        # Obter estatísticas de todos os veículos
        docs = mqtt_sub.db.collection('estatisticas_veiculos').stream()
        
        total_leituras = 0
        total_seguro = 0
        total_moderado = 0
        total_arriscado = 0
        
        for doc in docs:
            data = doc.to_dict()
            total_leituras += data.get('total_leituras', 0)
            total_seguro += data.get('seguro', 0)
            total_moderado += data.get('moderado', 0)
            total_arriscado += data.get('arriscado', 0)
        
        return jsonify({
            'sucesso': True,
            'resumo': {
                'total_pontos_analisados': total_leituras,
                'distribuicao': {
                    'seguro': total_seguro,
                    'moderado': total_moderado,
                    'arriscado': total_arriscado,
                    'percentual_seguro': (total_seguro / total_leituras * 100) if total_leituras > 0 else 0,
                    'percentual_moderado': (total_moderado / total_leituras * 100) if total_leituras > 0 else 0,
                    'percentual_arriscado': (total_arriscado / total_leituras * 100) if total_leituras > 0 else 0
                },
                'ultima_atualizacao': datetime.now().isoformat()
            }
        })
        
    except Exception as e:
        return jsonify({'erro': str(e)}), 500


@app.route('/api/alertas', methods=['GET'])
def alertas():
    """Alertas de comportamento arriscado"""
    if not mqtt_sub or not mqtt_sub.db:
        return jsonify({'erro': 'Firebase não disponível'}), 503
    
    try:
        # Buscar últimas leituras arriscadas
        docs = mqtt_sub.db.collection('telemetria') \
            .where('classificacao.classificacao', '==', 'arriscado') \
            .order_by('timestamp', direction=firestore.Query.DESCENDING) \
            .limit(50) \
            .stream()
        
        alertas_lista = []
        for doc in docs:
            data = doc.to_dict()
            alertas_lista.append({
                'veiculo_id': data.get('veiculo_id'),
                'motorista_id': data.get('motorista_id'),
                'timestamp': data.get('timestamp'),
                'velocidade': data.get('dados_obd', {}).get('velocidade'),
                'tipo': 'comportamento_arriscado'
            })
        
        return jsonify({
            'sucesso': True,
            'total_alertas': len(alertas_lista),
            'alertas': alertas_lista
        })
        
    except Exception as e:
        return jsonify({'erro': str(e)}), 500


# =====================================================
# 3. EXECUTAR
# =====================================================

if __name__ == '__main__':
    print("=" * 60)
    print("  BACKEND NUVEM - MQTT + FIREBASE + API")
    print("=" * 60)
    print("\n🌐 Aguardando dados do Raspberry Pi via MQTT...")
    print("🔥 Salvando no Firebase...")
    print("📊 Servindo API para seguradoras...")
    print("\nEndpoints:")
    print("  GET  /api/status")
    print("  GET  /api/dados-recentes")
    print("  GET  /api/veiculo/<id>/estatisticas")
    print("  GET  /api/veiculos")
    print("  GET  /api/dashboard/resumo")
    print("  GET  /api/alertas")
    print("\nIniciando servidor na porta 8000...\n")
    
    app.run(host='0.0.0.0', port=8000, debug=False)
