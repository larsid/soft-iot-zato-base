


# Soft-IoT Zato ESB Migration

Este projeto é uma migração moderna dos módulos `local-storage` e `mapping-devices` da plataforma Soft-IoT (originalmente em Java/OSGi) para Python, rodando sobre o **Zato ESB**.

O sistema atua como um Gateway IoT que gerencia dispositivos via protocolo **TATU (Extended)**, armazena dados em banco local e fornece APIs de consulta.

---

## 🏗️ Arquitetura

* **Plataforma:** Zato ESB (Python) em Docker.
* **Protocolo IoT:** MQTT + TATU (Extended Wrapper).
* **Banco de Dados:** SQLite (Local).
* **Broker:** Mosquitto ou RabbitMQ (Externo).

### Fluxo de Dados
1.  **Dispositivo** conecta via MQTT.
2.  **Zato** autoriza (`CONNACK`) e envia configuração (`FLOW`).
3.  **Dispositivo** publica dados de sensores.
4.  **Zato** intercepta, processa e salva no **SQLite**.
5.  **Scheduler** roda tarefas de Agregação e Limpeza periodicamente.
6.  **Usuário/Dashboard** consulta dados via **API REST**.

---

## 🚀 Instalação e Deploy

### Pré-requisitos
* Docker e Docker Compose.
* Acesso ao container do Zato (usuário `zato`).

### 1. Estrutura de Arquivos
No diretório `pickup` do servidor Zato (`/opt/zato/env/qs-1/server1/pickup/`), você deve ter:

* `soft_iot_storage.py` - O "Worker" MQTT principal.
* `soft_iot_mapping.py` - Serviços de gestão de dispositivos.
* `soft_iot_api.py` - API REST para consulta de dados.
* `soft_iot_aggregation.py` - Serviço de agregação de dados (médias).
* `soft_iot_cleanup.py` - Serviço de limpeza de dados antigos.
* `devices.json` - Arquivo de configuração dos dispositivos.

### 2. Configuração (`devices.json`)
Defina os dispositivos permitidos e seus sensores:

```json
[
    {
        "id": "py_device_01",
        "sensors": [
            {
                "id": "temperatureSensor",
                "type": "Thermometer",
                "collection_time": 4,
                "publishing_time": 8
            }
        ]
    }
]
```

### 3\. Configuração do Código (`soft_iot_storage.py`)

Edite a variável `BROKER_URL` para apontar para o seu broker MQTT:

```python
BROKER_URL = "172.x.x.x" # IP do Broker acessível pelo container Zato
```

-----

## 🛠️ Serviços Disponíveis

### 📡 Core (MQTT)

  * **`soft-iot.storage.service`**
      * *Função:* Inicia a thread de conexão MQTT. Deve ser executado **uma vez** na inicialização (via Scheduler "On Startup" ou Invoker manual).
      * *Logs:* `server.log` mostrará "MQTT Conectado".

### 💾 Manutenção (Scheduler)

  * **`soft-iot.aggregation.service`**
      * *Função:* Calcula médias horárias dos dados brutos.
      * *Agendamento Sugerido:* A cada 1 hora.
  * **`soft-iot.cleanup.service`**
      * *Função:* Remove dados brutos antigos para economizar espaço.
      * *Config:* Variável de ambiente `DATA_RETENTION_SECONDS` (Padrão: 60s para dev, 86400 para prod).
      * *Agendamento Sugerido:* A cada 24 horas.

### 🔌 API (REST/Invoker)

  * **`soft-iot.mapping.list-devices`**
      * Retorna a lista de dispositivos cadastrados.
  * **`soft-iot.mapping.get-device`**
      * Payload: `{"device_id": "..."}`. Retorna detalhes de um dispositivo.
  * **`soft-iot.api.get-last-data`**
      * Payload: `{"device_id": "...", "sensor_id": "..."}`. Retorna a leitura mais recente.
  * **`soft-iot.api.get-history`**
      * Payload: `{"device_id": "...", "sensor_id": "...", "limit": 100, "aggregation_status": 0}`.
      * `aggregation_status`: 0 = Dados Brutos, 1 = Dados Agregados (Médias).

-----

## ✅ Funcionalidades Convertidas (De/Para)

| Funcionalidade Original (Java) | Status Zato (Python) | Observação |
| :--- | :--- | :--- |
| **Leitura de Config (.cfg)** | ✅ **devices.json** | Mais flexível e legível. |
| **Conexão MQTT** | ✅ **Paho Python** | Executa em background thread. |
| **Handshake TATU** | ✅ **Implementado** | Suporte a `CONNECT`, `CONNACK` e `FLOW`. |
| **Persistência (H2)** | ✅ **SQLite** | Arquivo `.db` persistente. |
| **Agregação de Dados** | ✅ **Aggregation Service** | Consolida dados históricos. |
| **Limpeza Automática** | ✅ **Cleanup Service** | Política de retenção configurável. |
| **API Java (OSGi)** | ✅ **API REST Zato** | Acessível via HTTP/JSON. |
| **Enriquecimento Semântico** | ❌ **Não Migrado** | Requer libs RDF (fora do escopo atual). |

-----

## 🧪 Como Testar

1.  Suba o Zato e o Broker MQTT.
2.  Inicie o serviço `soft-iot.storage.service` via Dashboard.
3.  Rode um dispositivo virtual (ex: Virtual-FoT-Device).
4.  Verifique se o Zato enviou o comando `FLOW` nos logs.
5.  Aguarde a chegada de dados.
6.  Consulte via API: `soft-iot.api.get-last-data`.

-----

**Desenvolvido com Zato ESB 🚀**
