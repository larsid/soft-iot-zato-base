import os
from fogbed import FogbedExperiment, Container, setLogLevel
import time
import threading

def simular_tunel(nome_container="mn.device-1", tempo_espera=300, tempo_apagao=60):
    print(f"\n[SIMULADOR] ⏱️ Aguardando {tempo_espera}s para a rede estabilizar o handshake...")
    time.sleep(tempo_espera) # Dá tempo do Zato ligar e aprovar as conexões
    
    print(f"\n[SIMULADOR] 🚚 ALERTA: O {nome_container} entrou em uma área sem sinal (Túnel)!")
    print(f"[SIMULADOR] ✂️  Cortando a placa de rede virtual...")
    os.system(f"docker exec {nome_container} ip link set dev {nome_container.replace('mn.', '')}-eth0 down")
    
    print(f"[SIMULADOR] 📡 O dispositivo ficará offline por {tempo_apagao} segundos...")
    time.sleep(tempo_apagao)
    
    print(f"\n[SIMULADOR] ☀️ O {nome_container} saiu do túnel! Restaurando o sinal...")
    os.system(f"docker exec {nome_container} ip link set dev {nome_container.replace('mn.', '')}-eth0 up")
    print(f"[SIMULADOR] ✅ Sinal restaurado! Olhe o log do {nome_container} para ver a reconexão automática e a retomada do fluxo!")


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '../../'))

setLogLevel('info')

# ========================================================================
# 1. SETUP DE VARIÁVEIS E PORTAS (Traduzido do Bash)
# ========================================================================
NODE_ID = 1
HOST_ZATO_PORT = 11220 + NODE_ID
HOST_MQTT_PORT = 1880 + NODE_ID
HOST_MQTT_WS_PORT = 9000 + NODE_ID
HOST_ADMIN_PORT = 8180 + NODE_ID
HOST_ADMIN_PORT_SSL = 8181 + NODE_ID
HOST_SSH_PORT = 22020 + NODE_ID

container_name = f'zato-{NODE_ID}'

# ========================================================================
# 2. GERAÇÃO DO ARQUIVO ENV.INI (Traduzido dos 'echo' do Bash)
# ========================================================================
os.makedirs('config/auto-generated', exist_ok=True)
with open('config/auto-generated/env.ini', 'w') as f:
    f.write("[env]\n")
    f.write("My_API_Password_1=senha123\n") 
    f.write("My_API_Password_2=senha123\n")
    f.write("Zato_Project_Root=/opt/hot-deploy/myproject\n")

# ========================================================================
# 3. CONFIGURAÇÃO DA TOPOLOGIA FOGBED
# ========================================================================
exp = FogbedExperiment(metrics_enabled=True)
cloud = exp.add_virtual_instance('cloud')

zato_esb = Container(
    name=container_name,
    ip='10.0.0.10',
    user='root',
    privileged=True,
    dimage='rhianpablo11/esb-zato-soft-iot:v10',
    dcmd='/usr/local/bin/start_wrapper.sh',    
    environment={
        'Zato_Dashboard_Password': '123456',
        'ZATO_SSH_PASSWORD': '123456',
        'Zato_IDE_Password': '123456',
        'Zato_Log_Env_Details': 'true',
        'Zato_Build_Verbosity': '',
        'Zato_SAVE_DATA_ENABLED': 'True',
        'Zato_COLLECTION_TIME': '2',
        'Zato_PUBLISH_TIME': '6',
        'Zato_AGGREGATION_WINDOW_MINUTES': '10',
        'Zato_DATA_RETENTION_SECONDS': '1200',
        'Zato_TANGLE_API_IP': '10.0.0.10', 
        'Zato_TANGLE_API_PORT': '3001',
        'Zato_ZMQ_IP': '10.0.0.10',
        'Zato_ZMQ_PORT': '5556',
        'Zato_GATEWAY_REAL_IP': '10.0.0.14'
    },
    port_bindings={
        22: HOST_SSH_PORT,
        8183: HOST_ADMIN_PORT,
        8184: HOST_ADMIN_PORT_SSL,
        11223: HOST_ZATO_PORT,
        11225: 11225,
        3000: 3030,
        15672: 15672,
        1883: HOST_MQTT_PORT,
        9001: HOST_MQTT_WS_PORT
    }
)


# 1. Cria a camada de Borda
edge = exp.add_virtual_instance('edge')

# ========================================================================
# INSTANCIANDO MÚLTIPLOS DISPOSITIVOS COM UM LOOP FOR
# ========================================================================
NUM_DEVICES = 5
devices = []

print(f"Criando {NUM_DEVICES} dispositivos virtuais...")

# 2. Configuração do FoT Device
for i in range(1, NUM_DEVICES + 1):
    # Calculo do IP dinâmico (começando do 10.0.0.11)
    ip_suffix = 10 + i 
    device_ip = f'10.0.0.{ip_suffix}'
    device_name = f'device-{i}'
    device_id = f'py_device_{i:02d}' # Formata para py_device_01, py_device_02...

    # Cria o container do dispositivo
    dev = Container(
        name=device_name,
        ip=device_ip, 
        dimage='virtual-fot-device-python:v2',
        dcmd='python main.py', 
        environment={
            'DEVICE_ID': device_id,
            'BROKER_IP': '10.0.0.10', 
            'PORT': 1883,
            'USERNAME': 'karaf',
            'PASSWORD': 'karaf',
            'BIND_IP': device_ip, # O IP específico dele
            'CONNECTION_TIMEOUT': 0
        }
    )
    
    # Adiciona o dispositivo criado à instância da Borda (edge)
    exp.add_docker(dev, edge)
    devices.append(dev)


exp.add_docker(zato_esb, cloud)
exp.add_link(edge, cloud)

try:
    print(f"Iniciando topologia e o container {container_name}...")
    exp.start()

    # ====================================================================
    # 4. EXECUTANDO MKDIR E DOCKER CP DEPOIS QUE O CONTAINER SOBE
    # ====================================================================

    print("Criando diretórios isolados dentro do container...")
    zato_esb.cmd('mkdir -p /opt/hot-deploy/myproject /opt/hot-deploy/enmasse /opt/hot-deploy/python-reqs /home/ubuntu/mapping_archives/devices_config/')

    print("Criando snapshot dos arquivos locais (docker cp)...")
    real_docker_name = f"mn.{container_name}"

    os.system(f"docker cp {PROJECT_ROOT}/. {real_docker_name}:/opt/hot-deploy/myproject/")
    os.system(f"docker cp {PROJECT_ROOT}/config/enmasse/enmasse.yaml {real_docker_name}:/opt/hot-deploy/enmasse/enmasse.yaml")
    os.system(f"docker cp {PROJECT_ROOT}/config/auto-generated/env.ini {real_docker_name}:/opt/hot-deploy/enmasse/env.ini")
    os.system(f"docker cp {PROJECT_ROOT}/config/python-reqs/requirements.txt {real_docker_name}:/opt/hot-deploy/python-reqs/requirements.txt")
    os.system(f"docker cp {PROJECT_ROOT}/impl/src/archives/. {real_docker_name}:/home/ubuntu/mapping_archives/devices_config/")
    os.system(f"docker exec {real_docker_name} rm -f /opt/hot-deploy/myproject/impl/scripts/fogbed-test.py")
    print("✅ Container configurado e arquivos copiados!")
    print(f"O Dashboard Admin está rodando em http://localhost:{HOST_ADMIN_PORT}")
    
    threading.Thread(target=simular_tunel, daemon=True).start()


    input("\nPressione ENTER para encerrar o Fogbed e destruir a rede...\n")
    
except Exception as ex: 
    print(f"Erro: {ex}")
finally:
    exp.stop()