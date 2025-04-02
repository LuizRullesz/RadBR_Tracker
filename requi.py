import requests
import time
import logging
import json
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dataclasses import dataclass

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("requi.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuração
MAX_RETRY_API_FLASK = 3
MAX_RETRY_API_NODE = 3
TIMEOUT_SECONDS = 10
CIRCUIT_BREAKER_THRESHOLD = 5  # Número de falhas para ativar o circuit breaker
CIRCUIT_BREAKER_TIMEOUT = 300  # Tempo (em segundos) para o circuit breaker reset
CHECK_INTERVAL = 10  # Tempo entre verificações em segundos

# URL base da API
base_url = 'http://127.0.0.1:5000/api/character/name={}'
node_api_url = "http://localhost:8000/messagem"

# Lista de nomes para verificar
nomes = ['Zahir', 'Mancolino', 'Mais Do Mesmo', 'Cleef', 'Geoff', 'Radik']

# Dicionário para armazenar os nomes na whitelist e o tempo de expiração
whitelist = {}

# Configurando circuit breaker para APIs
@dataclass
class CircuitBreaker:
    service_name: str
    failure_count: int = 0
    last_failure_time: datetime = None
    is_open: bool = False
    threshold: int = CIRCUIT_BREAKER_THRESHOLD
    timeout: int = CIRCUIT_BREAKER_TIMEOUT

# Circuit breakers para as APIs
flask_circuit_breaker = CircuitBreaker("Flask API")
node_circuit_breaker = CircuitBreaker("Node API")

# Função para adicionar um nome à whitelist
def adicionar_whitelist(nome):
    whitelist[nome] = datetime.now() + timedelta(minutes=30)
    logger.info(f"{nome} adicionado à whitelist. Será ignorado por 30 minutos.")

# Configurar retry para requests
def requests_retry_session(retries=3, backoff_factor=0.3, status_forcelist=(500, 502, 503, 504)):
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

# Verificar estado do circuit breaker
def is_circuit_open(circuit_breaker):
    # Se o circuit breaker está aberto, verificar se já passou o tempo para reset
    if circuit_breaker.is_open:
        if circuit_breaker.last_failure_time and (datetime.now() - circuit_breaker.last_failure_time).total_seconds() > circuit_breaker.timeout:
            # Reset do circuit breaker depois do tempo de timeout
            circuit_breaker.is_open = False
            circuit_breaker.failure_count = 0
            logger.info(f"Circuit breaker para {circuit_breaker.service_name} foi resetado")
        else:
            # Ainda está no período de timeout
            logger.warning(f"Circuit breaker para {circuit_breaker.service_name} ainda está aberto. Saltando requisição.")
    return circuit_breaker.is_open

# Registrar falha no circuit breaker
def record_failure(circuit_breaker):
    circuit_breaker.failure_count += 1
    circuit_breaker.last_failure_time = datetime.now()
    
    # Verificar se atingiu o limite de falhas
    if circuit_breaker.failure_count >= circuit_breaker.threshold:
        circuit_breaker.is_open = True
        logger.error(f"Circuit breaker para {circuit_breaker.service_name} aberto após {circuit_breaker.failure_count} falhas.")

# Função para verificar status do personagem na API Flask
def check_character_status(nome):
    # Verificar circuit breaker
    if is_circuit_open(flask_circuit_breaker):
        return None
    
    url = base_url.format(nome)
    start_time = time.time()
    
    try:
        response = requests_retry_session(retries=MAX_RETRY_API_FLASK).get(url, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        
        # Registrar tempo de resposta para monitoramento
        elapsed_time = time.time() - start_time
        logger.info(f"Requisição para {nome} concluída em {elapsed_time:.2f} segundos")
        
        # Reset do circuit breaker após sucesso
        flask_circuit_breaker.failure_count = 0
        
        return response.json()
    except requests.exceptions.RequestException as e:
        elapsed_time = time.time() - start_time
        logger.error(f"Erro ao consultar API Flask para {nome}: {str(e)} após {elapsed_time:.2f} segundos")
        record_failure(flask_circuit_breaker)
        return None

# Função para enviar notificação para API Node
def send_notification(nome):
    # Verificar circuit breaker
    if is_circuit_open(node_circuit_breaker):
        return False
    
    data = {
        'number': '120363314303440566@g.us',
        'message': f"O personagem {nome} morreu ou deslogou"
    }
    
    start_time = time.time()
    try:
        response = requests_retry_session(retries=MAX_RETRY_API_NODE).post(
            node_api_url, 
            data=data,
            timeout=TIMEOUT_SECONDS
        )
        response.raise_for_status()
        
        # Registrar tempo de resposta para monitoramento
        elapsed_time = time.time() - start_time
        logger.info(f"Notificação enviada para {nome} em {elapsed_time:.2f} segundos")
        
        # Reset do circuit breaker após sucesso
        node_circuit_breaker.failure_count = 0
        
        return True
    except requests.exceptions.RequestException as e:
        elapsed_time = time.time() - start_time
        logger.error(f"Erro ao enviar notificação para {nome}: {str(e)} após {elapsed_time:.2f} segundos")
        record_failure(node_circuit_breaker)
        return False

# Heartbeat para monitoramento
def send_heartbeat():
    logger.info("Sistema de monitoramento ativo - Heartbeat")
    # Aqui você poderia implementar um envio para um sistema de monitoramento externo

# Verificar saúde da API Flask
def check_flask_api_health():
    try:
        response = requests.get('http://127.0.0.1:5000/health', timeout=5)
        if response.status_code == 200:
            return True
        return False
    except:
        return False

# Loop principal
def main():
    logger.info("Iniciando sistema de monitoramento de personagens")
    
    # Variáveis para estatísticas
    cycle_count = 0
    last_heartbeat = datetime.now()
    
    try:
        while True:
            cycle_count += 1
            cycle_start_time = time.time()
            
            # Enviar heartbeat a cada minuto
            if (datetime.now() - last_heartbeat).total_seconds() > 60:
                send_heartbeat()
                last_heartbeat = datetime.now()
            
            # Verificar saúde da API Flask periodicamente
            if cycle_count % 6 == 0:  # A cada 6 ciclos (aproximadamente 1 minuto)
                if not check_flask_api_health():
                    logger.warning("API Flask não está respondendo ao health check!")
            
            # Processar personagens
            for nome in nomes:
                # Verifica se o nome está na whitelist e se o tempo de espera acabou
                if nome in whitelist:
                    if datetime.now() < whitelist[nome]:
                        remaining_minutes = int((whitelist[nome] - datetime.now()).total_seconds() // 60)
                        logger.info(f"{nome} está na whitelist. Ignorando por mais {remaining_minutes} minutos.")
                        continue  # Pula para o próximo nome sem fazer a requisição
                    else:
                        del whitelist[nome]  # Remove o nome da whitelist se o tempo expirou
                        logger.info(f"{nome} removido da whitelist. Verificando status.")
                
                # Verifica o status do personagem
                data = check_character_status(nome)
                
                if data is None:
                    logger.warning(f"Não foi possível verificar o status de {nome}. Adicionando à whitelist.")
                    adicionar_whitelist(nome)
                    continue
                
                # Verifica se o campo "status" é "Online"
                if data.get('status') == 'Online':
                    logger.info(f"{nome}: Online")
                else:
                    logger.info(f"{nome}: Offline. Enviando notificação.")
                    if send_notification(nome):
                        adicionar_whitelist(nome)  # Adiciona à whitelist apenas se a notificação foi enviada com sucesso
                    else:
                        logger.error(f"Falha ao enviar notificação para {nome}. Tentando novamente no próximo ciclo.")
            
            # Calcular tempo do ciclo para ajustar o tempo de espera
            cycle_elapsed = time.time() - cycle_start_time
            sleep_time = max(0.1, CHECK_INTERVAL - cycle_elapsed)  # Garantir pelo menos 0.1 segundos
            
            logger.debug(f"Ciclo {cycle_count} completado em {cycle_elapsed:.2f} segundos. Aguardando {sleep_time:.2f} segundos.")
            time.sleep(sleep_time)
            
    except KeyboardInterrupt:
        logger.info("Sistema de monitoramento encerrado pelo usuário")
    except Exception as e:
        logger.critical(f"Erro crítico no sistema de monitoramento: {str(e)}", exc_info=True)
        # Reiniciar o script após um erro crítico
        time.sleep(5)
        main()  # Reinicia o loop principal

if __name__ == "__main__":
    main()
