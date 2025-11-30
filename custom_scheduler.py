import os
import time
import logging
import threading
import schedule # pip install schedule
import requests
import yaml

# Configuração de Log
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [EXTERNAL_SCHEDULER] - %(levelname)s - %(message)s')
logger = logging.getLogger()

# Configurações
ZATO_PING_URL = "http://localhost:11223/zato/ping"
ENMASSE_FILE = "/opt/hot-deploy/enmasse/enmasse.yaml"
# Usuário/Senha do Zato (caso seus serviços precisem de auth, se não, pode remover o auth=...)
ZATO_USER = os.getenv("Zato_Dashboard_Password", "admin") 
ZATO_PASS = os.getenv("Zato_Dashboard_Password", "123456")

def wait_for_zato():
    """Loop que trava o script até o Zato responder ao Ping."""
    logger.info(f"Aguardando Zato iniciar em {ZATO_PING_URL}...")
    
    while True:
        try:
            # AUMENTAMOS O TIMEOUT PARA 10s (era 2)
            # O Zato pode estar lento no boot
            response = requests.get(ZATO_PING_URL, timeout=10)
            
            if response.status_code == 200:
                logger.info("Zato está ONLINE! Iniciando agendamento...")
                time.sleep(2) 
                return
        
        # AGORA CAPTURAMOS TODOS OS ERROS DE REQUEST (Conexão e Timeout)
        except requests.exceptions.RequestException:
            # Se der erro ou demorar, apenas ignoramos e tentamos de novo
            pass
        
        # Espera um pouco antes de tentar de novo
        time.sleep(5)

def perform_request(job_name, url):
    """Executa o GET na URL configurada."""
    logger.info(f"Executando Job: '{job_name}' -> GET {url}")
    try:
        # Faz o GET. Se precisar de auth básica, descomente o auth=
        response = requests.get(url, timeout=10) #, auth=(ZATO_USER, ZATO_PASS))
        
        if response.status_code < 400:
            logger.info(f"Sucesso [{response.status_code}]: '{job_name}'")
        else:
            logger.error(f"Erro [{response.status_code}]: '{job_name}' - {response.text[:100]}")
    except Exception as e:
        logger.error(f"Falha na requisição de '{job_name}': {e}")

def load_and_schedule():
    if not os.path.exists(ENMASSE_FILE):
        logger.error(f"Arquivo {ENMASSE_FILE} não encontrado!")
        return

    with open(ENMASSE_FILE, 'r') as f:
        config = yaml.safe_load(f)

    # Lê apenas a nossa chave customizada
    jobs = config.get('external_scheduler', [])
    logger.info(f"Carregados {len(jobs)} jobs externos.")

    for job in jobs:
        name = job.get('name', 'Sem Nome')
        url = job.get('url')
        job_type = job.get('job_type')
        
        if not url:
            logger.warning(f"Job '{name}' ignorado: Sem URL configurada.")
            continue

        if job_type == 'one_time':
            delay = int(job.get('initial_delay', 5))
            logger.info(f"Agendado (Único): '{name}' para daqui a {delay}s")
            # Usa threading.Timer para não bloquear o loop principal
            threading.Timer(delay, perform_request, args=[name, url]).start()

        elif job_type == 'interval_based':
            interval = int(job.get('interval', 60))
            unit = job.get('unit', 'seconds')
            
            job_scheduler = schedule.every(interval)
            
            if unit == 'seconds':
                job_scheduler.seconds.do(perform_request, name, url)
            elif unit == 'minutes':
                job_scheduler.minutes.do(perform_request, name, url)
            elif unit == 'hours':
                job_scheduler.hours.do(perform_request, name, url)
                
            logger.info(f"Agendado (Recorrente): '{name}' a cada {interval} {unit}")

def main():
    wait_for_zato()
    load_and_schedule()
    
    logger.info("Scheduler ativo. Pressione Ctrl+C para parar.")
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()