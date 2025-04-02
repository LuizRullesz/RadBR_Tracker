from flask import Flask, Response, request
import json
import os
import requests
from bs4 import BeautifulSoup
import logging
import time
from functools import lru_cache
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configurar retry para requests
def requests_retry_session(
    retries=3,
    backoff_factor=0.3,
    status_forcelist=(500, 502, 503, 504),
    session=None,
):
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def check_is_on(character_name):
    url = f"https://site.radbr.com/index.php?subtopic=characters&name={character_name}&servidor=8"
    try:
        start_time = time.time()
        response = requests_retry_session().get(url, timeout=10)
        elapsed_time = time.time() - start_time
        logger.info(f"Requisição para {url} concluída em {elapsed_time:.2f} segundos")

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            character_name_tag = soup.find('td', string='Nome:')
            if character_name_tag:
                test = character_name_tag.find_next('a')
                if test:
                    img_tag = test.find('img', src='images/on.gif')
                    if img_tag:
                        return "Online"
            return "Offline"
        else:
            logger.warning(f"Resposta não-200 para {character_name}: {response.status_code}")
            return "Offline"
    except Exception as e:
        logger.error(f"Erro ao verificar status de {character_name}: {str(e)}")
        return "Offline"

@app.route('/api/character/name=<character_name>', methods=['GET'])
def get_character_info(character_name):
    start_time = time.time()
    logger.info(f"Recebida requisição para personagem: {character_name}")
    
    url = f"https://site.radbr.com/index.php?subtopic=characters&name={character_name}&servidor=8"
    try:
        response = requests_retry_session().get(url, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')

            character_level = soup.find('td', string='Level:')
            if character_level:
                character_level = character_level.find_next('td').text.strip()
            else:
                logger.warning(f"Personagem não encontrado: {character_name}")
                return Response(json.dumps({'error': 'Personagem não encontrado'}, ensure_ascii=False), 
                               status=404, mimetype='application/json')
                
            character_reset = soup.find('td', string='Reset:')
            if character_reset:
                character_reset = character_reset.find_next('td').text.strip()
            else:
                logger.warning(f"Dados incompletos para personagem: {character_name}")
                return Response(json.dumps({'error': 'Personagem não encontrado'}, ensure_ascii=False), 
                               status=404, mimetype='application/json')

            character_info = {
                'name': character_name,
                'level': character_level,
                'reset': character_reset,
                'status': check_is_on(character_name)
            }
            
            elapsed_time = time.time() - start_time
            logger.info(f"Processamento para {character_name} concluído em {elapsed_time:.2f} segundos")
            
            return Response(json.dumps(character_info), mimetype='application/json')
        else:
            logger.error(f"Erro ao buscar dados para {character_name}: Status {response.status_code}")
            return Response(json.dumps({'error': 'Personagem não encontrado'}, ensure_ascii=False), 
                           status=404, mimetype='application/json')
    except Exception as e:
        logger.error(f"Exceção ao processar requisição para {character_name}: {str(e)}")
        return Response(json.dumps({'error': f'Erro ao processar requisição: {str(e)}'}, ensure_ascii=False), 
                       status=500, mimetype='application/json')

@app.route('/health', methods=['GET'])
def health_check():
    return Response(json.dumps({'status': 'ok'}), mimetype='application/json')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Iniciando servidor na porta {port}")
    app.run(debug=True, host='0.0.0.0', port=port)
