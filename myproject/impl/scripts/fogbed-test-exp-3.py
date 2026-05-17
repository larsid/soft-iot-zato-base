import os
import time
import threading
from fogbed import FogbedExperiment, Container, setLogLevel

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '../../'))

setLogLevel('info')

# ========================================================================
# 1. SETUP DE VARIÁVEIS E PORTAS
# ========================================================================
NODE_ID = 1
HOST_ZATO_PORT = 11220 + NODE_ID
HOST_MQTT_PORT = 1880 + NODE_ID
HOST_MQTT_WS_PORT = 9000 + NODE_ID
HOST_ADMIN_PORT = 8180 + NODE_ID
HOST_ADMIN_PORT_SSL = 8181 + NODE_ID
HOST_SSH_PORT = 22020 + NODE_ID

container_name = f'zato-{NODE_ID}'

os.makedirs('config/auto-generated', exist_ok=True)
with open('config/auto-generated/env.ini', 'w') as f:
    f.write("[env]\n")
    f.write("My_API_Password_1=senha123\n") 
    f.write("My_API_Password_2=senha123\n")
    f.write("Zato_Project_Root=/opt/hot-deploy/myproject\n")

# ========================================================================
# 2. CONFIGURAÇÃO DA TOPOLOGIA COM MÚLTIPLAS BORDAS 
# ========================================================================
exp = FogbedExperiment(metrics_enabled=True)

# Cria a Nuvem e DUAS Antenas de Borda
cloud = exp.add_virtual_instance('cloud')
antena_a = exp.add_virtual_instance('antena_a')
antena_b = exp.add_virtual_instance('antena_b')

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
        22: HOST_SSH_PORT, 8183: HOST_ADMIN_PORT, 8184: HOST_ADMIN_PORT_SSL,
        11223: HOST_ZATO_PORT, 11225: 11225, 3000: 3030,
        15672: 15672, 1883: HOST_MQTT_PORT, 9001: HOST_MQTT_WS_PORT
    }
)

# Cria o container do dispositivo
dev = Container(
    name='device-1',
    ip='10.0.0.11', 
    dimage='virtual-fot-device-python:v2',
    dcmd='python main.py', 
    environment={
        'DEVICE_ID': 'py_device_01',
        'BROKER_IP': '10.0.0.10', 
        'PORT': 1883,
        'USERNAME': 'karaf',
        'PASSWORD': 'karaf',
        'BIND_IP': '10.0.0.11', 
        'CONNECTION_TIMEOUT': 0
    }
)

# Distribui os recursos fisicamente nos Switches (s1, s2, s3)
exp.add_docker(zato_esb, cloud)
exp.add_docker(dev, antena_a)  # <-- Dispositivo nasce conectado APENAS na Antena A

exp.add_link(antena_a, cloud)
exp.add_link(antena_b, cloud)

# ========================================================================
# 3. O SIMULADOR DE MOBILIDADE (HANDOFF)
# ========================================================================
def simular_handoff():
    print("\n[HANDOFF] ⏱️ Aguardando 300s para a rede estabilizar e o fluxo iniciar...")
    time.sleep(300)
    
    
    net = getattr(exp, '_net', getattr(exp, 'net', None))
    
    device_node = net.get('device-1')
    switch_a = net.get('s2') # Switch da antena_a
    switch_b = net.get('s3') # Switch da antena_b
    
    print("\n[HANDOFF] 🚗 O dispositivo começou a se mover e está saindo do alcance da Antena A...")
    net.delLinkBetween(device_node, switch_a)
    print("[HANDOFF] ✂️  Conexão física rompida! O dispositivo está no ponto cego (sem sinal).")
    
    time.sleep(10) 
    
    print("\n[HANDOFF] 📡 O dispositivo entrou na área da Antena B! Conectando...")
    # Cria o novo link na Antena B
    net.addLink(device_node, switch_b)
    
    
    os.system("docker exec mn.device-1 ip addr add 10.0.0.11/8 dev device-1-eth0")
    os.system("docker exec mn.device-1 ip link set dev device-1-eth0 up")
    
    print("[HANDOFF] ✅ Handoff concluído com sucesso! O tráfego agora flui pela Antena B.")

# ========================================================================
# 4. EXECUÇÃO
# ========================================================================
try:
    print(f"Iniciando topologia e o container {container_name}...")
    exp.start()
    
    print("Criando diretórios isolados dentro do container...")
    zato_esb.cmd('mkdir -p /opt/hot-deploy/myproject /opt/hot-deploy/enmasse /opt/hot-deploy/python-reqs /home/ubuntu/mapping_archives/devices_config/')

    print("Criando snapshot dos arquivos locais (docker cp)...")
    real_docker_name = f"mn.{container_name}"

    os.system(f"docker cp {PROJECT_ROOT}/. {real_docker_name}:/opt/hot-deploy/myproject/")
    os.system(f"docker cp {PROJECT_ROOT}/config/enmasse/enmasse.yaml {real_docker_name}:/opt/hot-deploy/enmasse/enmasse.yaml")
    os.system(f"docker cp {PROJECT_ROOT}/config/auto-generated/env.ini {real_docker_name}:/opt/hot-deploy/enmasse/env.ini")
    os.system(f"docker cp {PROJECT_ROOT}/config/python-reqs/requirements.txt {real_docker_name}:/opt/hot-deploy/python-reqs/requirements.txt")
    os.system(f"docker cp {PROJECT_ROOT}/impl/src/archives/. {real_docker_name}:/home/ubuntu/mapping_archives/devices_config/")
    os.system(f"docker exec {real_docker_name} rm -f /opt/hot-deploy/myproject/impl/scripts/fogbed-test-exp.py")
    
    print("✅ Container configurado e arquivos copiados!")
    print(f"O Dashboard Admin está rodando em http://localhost:{HOST_ADMIN_PORT}")
    
    # Dispara a simulação de mobilidade em segundo plano
    threading.Thread(target=simular_handoff, daemon=True).start()
    
    input("\nPressione ENTER para encerrar o Fogbed e destruir a rede...\n")
    
except Exception as ex: 
    print(f"Erro: {ex}")
finally:
    exp.stop()