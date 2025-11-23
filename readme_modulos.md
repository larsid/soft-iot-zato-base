

-----

### 1\. 📦 Soft-IoT Storage Worker (`soft_iot_storage.py`)

Este é o componente central que mantém a conexão persistente com o broker e gerencia o ciclo de vida dos dispositivos.


# Soft-IoT Storage Worker

O módulo **Storage Worker** é responsável por manter uma conexão ativa com o Broker MQTT, gerenciar o protocolo de *handshake* TATU (Connect/Connack) e persistir os dados recebidos no banco de dados local.

## 🚀 Funcionalidades
- **Conexão MQTT Persistente:** Executa em *background thread* independente do ciclo de vida HTTP do Zato.
- **Protocolo TATU:** Implementa o fluxo `CONNECT` -> `CONNACK` -> `FLOW`.
- **Persistência:** Salva dados de sensores (JSON) diretamente no SQLite.
- **Recuperação Automática:** Tenta reconectar ao broker em caso de falha.

## ⚙️ Configuração
Edite as variáveis no início do arquivo `soft_iot_storage.py` ou utilize variáveis de ambiente se adaptado:

| Variável | Descrição | Padrão |
| :--- | :--- | :--- |
| `BROKER_URL` | Endereço IP ou Hostname do Broker MQTT. | `localhost` (Mude para o IP do container/host) |
| `BROKER_PORT_TCP` | Porta TCP do Broker. | `1883` |
| `DB_FILENAME` | Caminho absoluto para o banco SQLite. | `/opt/zato/env/soft_iot_data.db` |

## 🛠️ Como Usar
1. Faça o deploy do arquivo `soft_iot_storage.py` na pasta `pickup`.
2. No Dashboard do Zato, vá em **Services** e encontre `soft-iot.storage.service`.
3. Execute o serviço **uma única vez** (via Invoker ou Scheduler "On Startup") para iniciar o loop MQTT.

## 📡 Tópicos MQTT Escutados
- `dev/CONNECTIONS`: Solicitações de conexão de novos dispositivos.
- `dev/#`: Dados de sensores (`FLOW DATA`) e respostas (`RES`).


-----

### 2\. 🗺️ Soft-IoT Mapping Devices (`soft_iot_mapping.py`)

Serviço responsável por centralizar a configuração dos dispositivos, permitindo que o sistema saiba como configurar cada sensor.


# Soft-IoT Mapping Devices

Este módulo atua como o "catálogo" do sistema, fornecendo metadados sobre os dispositivos permitidos e as configurações de coleta (tempo de coleta e publicação) para seus sensores.

## 🚀 Funcionalidades
- **Leitura de Configuração:** Carrega definições do arquivo `devices.json`.
- **API Interna:** Fornece dados para o *Storage Worker* configurar o comando `FLOW`.
- **API Externa:** Permite consultar dispositivos cadastrados via REST.

## 📂 Arquivo de Configuração (`devices.json`)
Deve estar localizado em `/opt/zato/env/qs-1/server1/pickup/devices.json`.

**Exemplo de Estrutura:**
```json
[
    {
        "id": "sensor1",
        "sensors": [
            {
                "id": "temperature",
                "type": "Thermometer",
                "collection_time": 4,
                "publishing_time": 8
            }
        ]
    }
]
```

## 🔌 Serviços Zato Disponíveis

| Serviço | Descrição | Payload Exemplo |
| :--- | :--- | :--- |
| `soft-iot.mapping.list-devices` | Retorna todos os dispositivos. | `{}` |
| `soft-iot.mapping.get-device` | Retorna detalhes de um dispositivo. | `{"device_id": "sensor1"}` |



---

### 3. 🔌 Soft-IoT Data API (`soft_iot_api.py`)

A interface de acesso aos dados. Substitui o antigo `LocalDataController` do Java, expondo os dados históricos e recentes via JSON.


# Soft-IoT Data API

Este módulo fornece endpoints REST para consulta de dados armazenados no SQLite. Suporta tanto dados brutos (*raw*) quanto dados agregados (médias horárias).

## 🚀 Funcionalidades
- **Último Valor:** Consulta rápida do estado atual de um sensor.
- **Histórico:** Consulta por período com paginação (limite).
- **Suporte a Agregação:** Filtra entre dados brutos (`status=0`) e agregados (`status=1`).

## ⚙️ Configuração
- **Banco de Dados:** Compartilha o mesmo arquivo `DB_FILENAME` definido no módulo de Storage.

## 🔌 Serviços Zato (Endpoints)

### 1. Obter Último Dado (`soft-iot.api.get-last-data`)
Retorna o registro mais recente.
* **Payload:**
  ```json
  {"device_id": "sensor1", "sensor_id": "temp"}
  ```

### 2\. Obter Histórico (`soft-iot.api.get-history`)

Retorna uma lista de registros ordenados por data.

  * **Payload:**
    ```json
    {
      "device_id": "sensor1",
      "sensor_id": "temp",
      "limit": 100,
      "aggregation_status": 0,  // 0 = Bruto, 1 = Agregado
      "start_date": "2023-01-01" // Opcional
    }
    ```

<!-- end list -->

---

### 4. 📉 Soft-IoT Aggregation Service (`soft_iot_aggregation.py`)

Serviço de manutenção que reduz o volume de dados transformando milhares de leituras em médias horárias.


# Soft-IoT Aggregation Service

Este serviço background processa dados brutos para gerar estatísticas consolidadas, otimizando o armazenamento e a performance de consultas de longo prazo.

## 🚀 Como Funciona
1. Identifica dados brutos (`aggregation_status = 0`) que ainda não foram processados.
2. Agrupa os dados por **Hora Fechada**.
3. Calcula a **Média** dos valores.
4. Insere um novo registro consolidado com `aggregation_status = 1`.
5. Atualiza o ponteiro de controle na tabela auxiliar.

## ⚠️ Regra de Negócio Importante
* **Hora Atual:** O serviço ignora propositalmente dados da hora corrente (ex: se são 14:30, ele só agrega até as 13:59) para evitar médias parciais incorretas.
* **Teste:** Para forçar a agregação imediata em dev, comente a linha `AND start_datetime < ...` no código SQL.

## ⏰ Agendamento (Scheduler)
Recomenda-se agendar este serviço no Zato Scheduler para rodar a cada **1 hora**.


-----

### 5\. 🧹 Soft-IoT Cleanup Service (`soft_iot_cleanup.py`)

O "coletor de lixo" do sistema. Garante a saúde do disco rígido removendo dados obsoletos.


# Soft-IoT Cleanup Service

Serviço responsável por aplicar a Política de Retenção de Dados (*Data Retention Policy*), deletando registros brutos antigos do banco de dados.

## 🚀 Funcionalidades
- Remove registros com `aggregation_status = 0` (Brutos).
- Mantém registros agregados (Status 1) preservados.
- Executa `VACUUM` no SQLite para recuperar espaço em disco.

## ⚙️ Configuração (Variáveis de Ambiente)
O comportamento é controlado pela variável `DATA_RETENTION_SECONDS` passada ao container ou definida no sistema.

| Variável | Valor Padrão | Uso Recomendado |
| :--- | :--- | :--- |
| `DATA_RETENTION_SECONDS` | `60` (1 minuto) | **Dev/Testes:** Limpeza agressiva para não lotar com lixo de teste. |
| | `86400` (24 horas) | **Produção:** Mantém 1 dia de dados brutos de alta resolução. |

## ⏰ Agendamento (Scheduler)
Recomenda-se agendar este serviço no Zato Scheduler para rodar a cada **24 horas** (ou conforme a necessidade de liberar espaço).
