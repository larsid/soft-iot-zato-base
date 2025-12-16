# -*- coding: utf-8 -*-

from zato.server.service import Service
import sqlite3
import os
from datetime import datetime, timedelta

DB_FILENAME = "/opt/zato/env/soft_iot_data.db"

class AggregateSensorData(Service):
    """
    Serviço que consolida dados brutos em médias horárias.
    Equivalente à lógica de agregação sugerida por 'LocalDataControllerImpl.java'.
    """
    name = 'soft-iot.aggregation.service'

    def handle(self):
        self.logger.info("INICIANDO AGREGAÇÃO DE DADOS...")
        
        conn = None
        try:
            if not os.path.exists(DB_FILENAME):
                return

            conn = sqlite3.connect(DB_FILENAME)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 1. Descobrir quais sensores têm dados
            cursor.execute("SELECT DISTINCT device_id, sensor_id FROM sensor_data")
            sensors = cursor.fetchall()

            for row in sensors:
                device_id = row['device_id']
                sensor_id = row['sensor_id']
                
                self._aggregate_sensor(cursor, device_id, sensor_id)
            
            conn.commit()
            self.logger.info("AGREGAÇÃO FINALIZADA.")

        except Exception as e:
            self.logger.error(f"Erro na agregação: {e}")
            if conn: conn.rollback()
        finally:
            if conn: conn.close()

    def _aggregate_sensor(self, cursor, device_id, sensor_id):
        # 2. Descobrir a última vez que agregamos dados para este sensor
        cursor.execute("""
            SELECT last_time FROM aggregation_registered_last_time_sensors 
            WHERE device_id = ? AND sensor_id = ?
        """, (device_id, sensor_id))
        
        last_run_row = cursor.fetchone()
        
        if last_run_row and last_run_row[0]:
            last_time = last_run_row[0]
        else:
            # Se nunca rodou, começa do início dos tempos
            last_time = "1970-01-01 00:00:00"
            # Cria o registro de controle se não existir
            if not last_run_row:
                cursor.execute("""
                    INSERT INTO aggregation_registered_last_time_sensors (device_id, sensor_id, last_time)
                    VALUES (?, ?, ?)
                """, (device_id, sensor_id, last_time))

        # 3. Buscar dados brutos (Status 0) mais novos que a última agregação
        # Agrupamos por Hora (strftime '%Y-%m-%d %H:00:00')
        # Calculamos a média do valor
        query = """
            SELECT 
                strftime('%Y-%m-%d %H:00:00', start_datetime) as bucket_hour,
                AVG(CAST(data_value AS FLOAT)) as avg_val,
                MAX(end_datetime) as last_entry_in_bucket
            FROM sensor_data
            WHERE device_id = ? 
              AND sensor_id = ? 
              AND aggregation_status = 0
              AND start_datetime > ?
              AND start_datetime < strftime('%Y-%m-%d %H:00:00', 'now') -- Ignora a hora atual (incompleta)
            GROUP BY bucket_hour
            ORDER BY bucket_hour ASC
        """
        
        cursor.execute(query, (device_id, sensor_id, last_time))
        aggregates = cursor.fetchall()
        
        if not aggregates:
            return

        self.logger.info(f"Agregando {len(aggregates)} horas para {device_id}/{sensor_id}")

        last_processed_time = last_time

        # 4. Inserir os dados agregados (Status 1)
        for agg in aggregates:
            bucket_hour = agg['bucket_hour']
            avg_value = round(agg['avg_val'], 2)
            last_entry = agg['last_entry_in_bucket']
            
            # Insere novo registro consolidado
            insert_sql = """
                INSERT INTO sensor_data 
                (sensor_id, device_id, data_value, start_datetime, end_datetime, aggregation_status)
                VALUES (?, ?, ?, ?, ?, 1)
            """
            # O timestamp do registro agregado será o início da hora
            cursor.execute(insert_sql, (sensor_id, device_id, str(avg_value), bucket_hour, bucket_hour))
            
            last_processed_time = last_entry

        # 5. Atualizar o ponteiro de controle
        cursor.execute("""
            UPDATE aggregation_registered_last_time_sensors
            SET last_time = ?
            WHERE device_id = ? AND sensor_id = ?
        """, (last_processed_time, device_id, sensor_id))