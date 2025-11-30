#!/bin/bash

# Inicia o nosso scheduler customizado em background
# O output vai para o log do docker (stdout)
echo "[WRAPPER] Iniciando Scheduler Externo..."
/opt/zato/current/bin/python /home/ubuntu/mapping_archives/custom_scheduler.py &

# Inicia o processo original do Zato
# O "$@" garante que qualquer argumento passado no docker run seja respeitado
echo "[WRAPPER] Iniciando Zato..."
exec /entrypoint.sh "$@"