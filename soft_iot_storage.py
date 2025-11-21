# -*- coding: utf-8 -*-

# Zato
from zato.server.service import Service

# Standard library
import threading
import sqlite3
import json
import time
import os
import logging
from datetime import datetime

# Third-party
import paho.mqtt.client as mqtt

# Extended TATU Wrapper (certifique-se que está instalado via pip)
try:
    from extended_tatu_wrapper.utils import tatu_wrapper
    from extended_tatu_wrapper.enums import ExtendedTATUMethods
except ImportError:
    # Fallback ou log de erro critico se a lib não estiver presente
    logging.error("CRITICAL: extended_tatu_wrapper not found. Please install it via pip.")
    tatu_wrapper = None

# --- Configurações Hardcoded (como solicitado) ---
BROKER_URL = "172.22.96.236" # Ou o nome do container do broker, ex: "mosquitto"
BROKER_PORT_TCP = 1883
BROKER_PORT_WS = 9001
DB_FILENAME = "/opt/zato/env/soft_iot_data.db" # Caminho persistente dentro do container Zato
DEFAULT_COLLECTION_TIME = 10
DEFAULT_PUBLISHING_TIME = 30

# --- Controlador Singleton do MQTT e Banco de Dados ---

class LocalStorageController:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(LocalStorageController, cls).__new__(cls)
                    cls._instance.is_running = False
                    cls._instance.client = None
        return cls._instance

    def start(self, logger):
        """Inicia o loop MQTT se ainda não estiver rodando."""
        if self.is_running:
            return

        self.logger = logger
        self.logger.info("Iniciando Soft-IoT Local Storage Controller...")
        
        # 1. Inicializar Banco de Dados
        self.init_db()

        # 2. Configurar e Conectar MQTT
        self.connect_mqtt()
        
        self.is_running = True

    def init_db(self):
        """Cria as tabelas SQLite se não existirem."""
        try:
            with sqlite3.connect(DB_FILENAME) as conn:
                cursor = conn.cursor()
                
                # Tabela principal de dados
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS sensor_data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        sensor_id TEXT,
                        device_id TEXT,
                        data_value TEXT,
                        start_datetime TIMESTAMP,
                        end_datetime TIMESTAMP,
                        aggregation_status INTEGER DEFAULT 0
                    )
                ''')
                
                # Tabelas auxiliares (mantidas do original Java para compatibilidade futura)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS semantic_registered_last_time_sensors (
                        sensor_id TEXT,
                        device_id TEXT,
                        last_time TIMESTAMP
                    )
                ''')
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS aggregation_registered_last_time_sensors (
                        sensor_id TEXT,
                        device_id TEXT,
                        last_time TIMESTAMP
                    )
                ''')
                conn.commit()
            self.logger.info(f"Banco de dados SQLite inicializado em {DB_FILENAME}")
        except Exception as e:
            self.logger.error(f"Erro ao inicializar banco de dados: {e}")

    def connect_mqtt(self):
        """Configura o cliente MQTT Paho."""
        client_id = f"SoftIoT_Storage_{int(time.time())}"
        self.client = mqtt.Client(client_id=client_id)
        
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

        try:
            self.logger.info(f"Conectando ao broker MQTT {BROKER_URL}:{BROKER_PORT_TCP}...")
            self.client.connect(BROKER_URL, BROKER_PORT_TCP, 60)
            self.client.loop_start() # Executa em uma thread separada gerenciada pela lib
        except Exception as e:
            self.logger.error(f"Falha ao conectar no MQTT: {e}")

    def on_connect(self, client, userdata, flags, rc):
        self.logger.info(f"MQTT Conectado com código: {rc}")
        # Subscreve nos tópicos necessários
        topics = [
            ("CONNECTED", 1),
            ("dev/#", 1) # Captura dev/+/RES, dev/+/FLOW, etc.
        ]
        client.subscribe(topics)
        self.logger.info(f"Inscrito nos tópicos: {topics}")

    def on_disconnect(self, client, userdata, rc):
        self.logger.warning("MQTT Desconectado. O Paho tentará reconectar automaticamente se loop_start foi usado.")

    def on_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            # self.logger.info(f"Mensagem recebida em {topic}: {payload}")

            if tatu_wrapper is None:
                return

            # Lógica copiada e adaptada do Java
            if tatu_wrapper.is_tatu_response(payload):
                self.handle_tatu_response(payload)
            
            elif topic == "CONNECTED":
                self.handle_device_connected(payload)

        except Exception as e:
            self.logger.error(f"Erro ao processar mensagem MQTT: {e}", exc_info=True)

    def handle_tatu_response(self, message_content):
        """Processa respostas TATU (GET ou FLOW) e salva no banco."""
        try:
            device_id = tatu_wrapper.get_device_id_by_tatu_answer(message_content)
            sensor_id = tatu_wrapper.get_sensor_id_by_tatu_answer(message_content)
            
            # Parsing manual dos dados pois o wrapper Python fornecido é mais simples que o Java
            data_list = self.parse_tatu_body_to_data(message_content)
            
            if data_list:
                self.logger.info(f"Armazenando {len(data_list)} registros para Dev: {device_id}, Sensor: {sensor_id}")
                self.store_sensor_data(device_id, sensor_id, data_list)
            else:
                self.logger.warning("Resposta TATU válida mas sem dados extraíveis.")

        except Exception as e:
            self.logger.error(f"Erro ao processar resposta TATU: {e}")

    def parse_tatu_body_to_data(self, json_str):
        """
        Reimplementação da lógica Java 'TATUWrapper.parseTATUAnswerToListSensorData'.
        O wrapper python fornecido não tem esse helper, então criamos aqui.
        """
        data_points = []
        try:
            obj = json.loads(json_str)
            body = obj.get("BODY", {})
            # O timestamp do cabeçalho serve como base
            header_ts = int(obj.get("HEADER", {}).get("TIMESTAMP", time.time()*1000))
            
            for key, value in body.items():
                if key == "FLOW": continue # Ignora metadados de fluxo
                
                # O valor pode ser um único valor ou uma lista (FLOW)
                # Ex: "temperature": 25.5 ou "temperature": [25.5, 26.0, ...]
                
                values = value if isinstance(value, list) else [value]
                
                # Se for lista, precisamos inferir o tempo. 
                # Na implementação Java original, isso é complexo e depende da collection_time.
                # Aqui, para simplificar a conversão, usaremos o timestamp do header 
                # para o último dado e retrocederemos (ou usaremos o mesmo para todos se for GET).
                
                # Assumindo comportamento padrão do TATU:
                # Se GET, é valor instantâneo.
                # Se FLOW, são valores históricos.
                
                method = obj.get("METHOD")
                
                if method == "GET":
                    data_points.append({
                        "value": str(values[0]),
                        "timestamp": datetime.fromtimestamp(header_ts / 1000.0)
                    })
                else:
                    # Lógica simplificada para FLOW: 
                    # Se tivermos collection_time no BODY->FLOW, usamos. Senão, default.
                    flow_info = body.get("FLOW", {})
                    collect_ms = flow_info.get("collect", DEFAULT_COLLECTION_TIME * 1000) 
                    if collect_ms < 100: collect_ms = DEFAULT_COLLECTION_TIME * 1000 # Sanity check

                    # Itera reverso para calcular timestamps
                    current_ts = header_ts
                    for v in reversed(values):
                        data_points.append({
                            "value": str(v),
                            "timestamp": datetime.fromtimestamp(current_ts / 1000.0)
                        })
                        current_ts -= collect_ms
                    
                    data_points.reverse() # Volta para ordem cronológica

        except Exception as e:
            self.logger.error(f"Erro no parsing JSON do TATU: {e}")
        
        return data_points

    def store_sensor_data(self, device_id, sensor_id, data_list):
        """Insere dados no SQLite."""
        try:
            with sqlite3.connect(DB_FILENAME) as conn:
                cursor = conn.cursor()
                sql = '''
                    INSERT INTO sensor_data (sensor_id, device_id, data_value, start_datetime, end_datetime)
                    VALUES (?, ?, ?, ?, ?)
                '''
                # Prepara batch
                batch = []
                for item in data_list:
                    # No modelo Java, start e end parecem ser o mesmo para dados atômicos
                    batch.append((
                        sensor_id, 
                        device_id, 
                        item['value'], 
                        item['timestamp'], 
                        item['timestamp']
                    ))
                
                cursor.executemany(sql, batch)
                conn.commit()
        except Exception as e:
            self.logger.error(f"Erro SQL ao inserir dados: {e}")

    def handle_device_connected(self, device_id):
        """Envia requisição de FLOW quando um dispositivo conecta (lógica do Java)."""
        self.logger.info(f"Dispositivo conectado detectado: {device_id}")
        
        # No código Java, ele busca no 'fotDevices' para saber quais sensores o device tem.
        # Como estamos desacoplados, vamos enviar um comando genérico de INFO ou assumir sensores padrão.
        # Melhoria: Assumir que o dispositivo deve reportar seus sensores ou enviar um comando INFO.
        
        # Enviando comando padrão para coleta de temperatura como exemplo (ou adaptável)
        # Para ser fiel ao Java: 'sendFlowRequest'
        
        # Como não temos o 'Controller fotDevices' (Java) que mapeia o device,
        # não sabemos quais sensores ele tem.
        # SOLUÇÃO: Enviar um GET INFO para descobrir (não estava no Java original, mas é necessário aqui)
        # OU, apenas logar que não é possível enviar FLOW sem o mapeamento.
        
        self.logger.warning(f"Device {device_id} conectado. O Mapeamento de dispositivos ainda não foi migrado, então o comando FLOW automático foi ignorado.")
        
        # Exemplo de como enviar se soubéssemos o sensor (ex: 'temp'):
        # flow_req = tatu_wrapper.build_tatu_flow_value_message("temp", DEFAULT_COLLECTION_TIME, DEFAULT_PUBLISHING_TIME)
        # self.client.publish(f"{tatu_wrapper.TOPIC_BASE}{device_id}", flow_req)


# --- Serviço Zato ---

class SoftIoTStorageService(Service):
    """
    Serviço Zato responsável por inicializar o controlador de armazenamento local.
    Este serviço deve ser configurado no Zato Scheduler para rodar 'On Startup'.
    """
    name = 'soft-iot.storage.service'

    def handle(self):
        # Usa o logger nativo do Zato
        controller = LocalStorageController()
        
        # Verifica se já está rodando (Singleton)
        if not controller.is_running:
            self.logger.info("Inicializando o controlador Soft-IoT Storage...")
            controller.start(self.logger)
        else:
            self.logger.info("Controlador Soft-IoT Storage já está rodando.")