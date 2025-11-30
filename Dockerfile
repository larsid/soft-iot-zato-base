#IMAGEM BASE
FROM zatosource/zato-4.1

#VARIAVEIS DE AMBIENTE
ENV Zato_Log_Env_Details=True

#MAPEAMENTO DE PORTAS
EXPOSE 22 8183 11223 17010


#RODAR COMANDOS DENTRO DO CONTAINER
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Instalar bibliotecas Python para o seu scheduler e projetos
RUN /opt/zato/current/bin/pip install schedule requests pyyaml paho-mqtt

# O comando faz 3 coisas:
# a) Clona o repo para uma pasta temporária (/tmp/meu-pacote)
# b) Usa o pip do Zato para instalar a partir dessa pasta
# c) (Opcional) Remove a pasta clonada para economizar espaço
RUN git clone https://github.com/larsid/extended-tatu-wrapper.git /tmp/meu-pacote \
    && /opt/zato/current/bin/pip install /tmp/meu-pacote/python-version \
    && rm -rf /tmp/meu-pacote

#COPIA DE ARQUIVOS
COPY ./devices.json /home/ubuntu/mapping_archives/
COPY custom_scheduler.py /home/ubuntu/mapping_archives/
COPY start_wrapper.sh /usr/local/bin/start_wrapper.sh

# Dar permissão de execução no wrapper
RUN chmod +x /usr/local/bin/start_wrapper.sh

ENTRYPOINT ["/usr/local/bin/start_wrapper.sh"]