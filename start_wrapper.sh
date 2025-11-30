#!/bin/bash

# ==========================================================
# 1. INICIAR MOSQUITTO (NOVA ETAPA)
# ==========================================================
echo "[WRAPPER] Iniciando Mosquitto Broker..."

# Executa o broker apontando para a config que copiamos no Dockerfile.
# O '&' no final é ESSENCIAL para ele rodar em background e não travar o script.
/usr/sbin/mosquitto -c /etc/mosquitto/mosquitto.conf &

# Uma pequena pausa de segurança para garantir que a porta 1883 abra
# antes que os outros serviços tentem conectar.
sleep 2


# ==========================================================
# 2. INICIAR SCHEDULER (SEU CÓDIGO ORIGINAL)
# ==========================================================
# Inicia o nosso scheduler customizado em background
# O output vai para o log do docker (stdout)
echo "[WRAPPER] Iniciando Scheduler Externo..."
/opt/zato/current/bin/python /home/ubuntu/mapping_archives/custom_scheduler.py &


# ==========================================================
# 3. INICIAR ZATO (SEU CÓDIGO ORIGINAL)
# ==========================================================
# Inicia o processo original do Zato
# O "$@" garante que qualquer argumento passado no docker run seja respeitado
echo "[WRAPPER] Iniciando Zato..."
exec /entrypoint.sh "$@"