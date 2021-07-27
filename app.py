import requests
import json
import yaml
from datetime import datetime
import time
from yaml.loader import SafeLoader
import argparse
import logging
import sys
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

parser = argparse.ArgumentParser(description='Process graylog manage')
parser.add_argument('--config', dest='graylog_config', help='path to graylog yaml config', nargs=1, metavar=("FILE"))
parser.add_argument('--all', dest='all', help='trigger all arguments', action="store_true")
parser.add_argument('--create_update_inputs', dest='create_update_inputs', help='for work with inputs', action="store_true")
parser.add_argument('--create_update_users', dest='create_update_users', help='for work with users', action="store_true")
parser.add_argument('--create_update_streams', dest='create_update_streams', help='for work with streams', action="store_true")
parser.add_argument('--create_update_indexes', dest='create_update_indexes', help='for work with es indexes', action="store_true")
args = parser.parse_args()

def getInput():
    response = requests.get(
            f'{gl_url}/api/system/inputs',
            headers=headers,
            auth=auth,

    )
    response = response.json()
    gl_ex_input = {}
    for gl_input in response['inputs']:
        gl_ex_input[gl_input['title']] = [gl_input['id'], gl_input['attributes']['port']]
    return gl_ex_input

def createInput(gl_ex_inputs):
    for gl_input in data['inputs']:
        title = {gl_input['title']}
        if title.difference(gl_ex_inputs):
            gl_input_data = {
                'title': gl_input['title'],
                'type': gl_input['type'],
                'global': gl_input['global'],
                'configuration': {
                    'bind_address': gl_input['configuration']['bind_address'],
                    'port': gl_input['configuration']['port'],
                    'decompress_size_limit': gl_input['configuration']['decompress_size_limit'],
                    'number_worker_threads': gl_input['configuration']['number_worker_threads'],
                    'override_source': gl_input['configuration']['override_source'],
                    'recv_buffer_size': gl_input['configuration']['recv_buffer_size'],
                },
                'node': gl_input['node'],
            }

            response = requests.post(
                f'{gl_url}/api/system/inputs',
                headers=headers,
                auth=auth,
                json=gl_input_data

            )
            response = response.json()
            input_id = response['id']
            logging.info(f'Input {title} was created with id: {input_id}')
            logging.info(f'Waiting 10s for starting input')
            time.sleep(10)
            setStaticFields(input_id, gl_input['static_fields']['key'], gl_input['static_fields']['value'])

def checkInput(gl_ex_inputs):
    for gl_input in gl_ex_inputs:
        input_id = gl_ex_inputs[gl_input][0]
        response = requests.get(
                f'{gl_url}/api/system/inputstates/{input_id}',
                headers=headers,
                auth=auth,
            )

        message = response.json()
        if response.status_code == 404:
            if message['type'] == 'ApiError':
                logging.info(f'{input_id} not running, trying restart')
                restartInput(input_id)

def restartInput(input_id):
    response = requests.put(
        f'{gl_url}/api/system/inputstates/{input_id}',
        headers=headers,
        auth=auth,
    )
    
def setStaticFields(input_id, static_field_key, static_field_value):
    data = {
        'key': static_field_key,
        'value': static_field_value
    }
    response = requests.post(
        f'{gl_url}/api/system/inputs/{input_id}/staticfields',
        headers=headers,
        auth=auth,
        json=data
    )
    logging.info(f'Add static field for {input_id}')

def userCreate():
    for user in data['users']:
        username = user['username']
        gl_user_data = {
            'username': username,
            'password': user['password'],
            'email': user['email'],
            'first_name': user['first_name'],
            'last_name': user['last_name'],
            'roles': ["Reader"],
            'permissions': [
                f'users:tokenlist:{username}',
                f'users:tokencreate:{username}',
                f'users:passwordchange:{username}',
                f'users:tokenremove:{username}',
                f'users:edit:{username}',
                'metrics:read',
                'messagecount:read',
                'journal:read',
                'messages:analyze',
                'fieldnames:read',
                'messages:read',
                'indexercluster:read',
                'system:read',
                'jvmstats:read',
                'inputs:read',
                'buffers:read',
                'clusterconfigentry:read',
                'decorators:read',
                'throughput:read'
            ],
        }
        response = requests.post(
            f'{gl_url}/api/users',
            headers=headers,
            auth=auth,
            json=gl_user_data
        )
        if response.status_code != 400:
            logging.info(f'User {username} was created')
        else:
            logging.info(f'User {username} already exist')

def getStreams():
    response = requests.get(
        f'{gl_url}/api/streams',
        headers=headers,
        auth=auth,
    )
    
    response = response.json()
    gl_ex_streams = []
    for stream in response['streams']:
        gl_ex_streams.append(stream['title'])
    return set(gl_ex_streams)

def createStreams(gl_ex_streams):
    for stream in data['streams']:
        title = {stream['title']}
        if title.difference(gl_ex_streams):
            gl_stream_data = {
                'title': stream['title'],
                'description': stream['description'],
                'remove_matches_from_default_stream': stream['remove_matches_from_default_stream'],
                'matching_type': stream['matching_type'],
                'index_set_id': stream['index_set_id'],
                'rules': [
                    {
                        'field': stream['rules']['field'],
                        'inverted': stream['rules']['inverted'],
                        'value': stream['rules']['value'],
                        'description': '',
                        'type': 1
                    }
                ]
            }
            response = requests.post(
                f'{gl_url}/api/streams',
                headers=headers,
                auth=auth,
                json=gl_stream_data
            )
            
            response = response.json()
            stream_id = response['stream_id']
            logging.info(f'Stream was created: {stream_id}')

            response = requests.post(
                f'{gl_url}/api/streams/{stream_id}/resume',
                headers=headers,
                auth=auth,
            )
            logging.info(f'Stream {stream_id} enabled')

def getIndexes():
    response = requests.get(
        f'{gl_url}/api/system/indices/index_sets?skip=0&limit=0&stats=false',
        headers=headers,
        auth=auth,
    )
    index_sets = response.json()['index_sets']
    gl_ex_indexes = {}
    for index in index_sets:
        gl_ex_indexes[index['id']] = index['title']
    return gl_ex_indexes

def indexCreate(gl_ex_indexes):
    for index in data['indexes']:
        title = {index['title']}
        if title.difference(gl_ex_indexes):
            gl_index_data = {
                'title': index['title'],
                'id': index['id'],
                'description': index['description'],
                'index_prefix': index['index_prefix'],
                'shards': index['shards'],
                'replicas': index['replicas'],
                'rotation_strategy_class': index['rotation_strategy_class'],
                'rotation_strategy': {
                    'type': index['rotation_strategy']['type'],
                    'rotation_period': index['rotation_strategy']['rotation_period'],
                },
                'retention_strategy_class': index['retention_strategy_class'],
                'retention_strategy': {
                    'type': index['retention_strategy']['type'],
                    'max_number_of_indices': index['retention_strategy']['max_number_of_indices'],
                },
                'creation_date': datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                'index_analyzer': index['index_analyzer'],
                'index_optimization_max_num_segments': index['index_optimization_max_num_segments'],
                'index_optimization_disabled': index['index_optimization_disabled'],
                'field_type_refresh_interval': index['field_type_refresh_interval'],
                'index_template_type': index['index_template_type'],
                'writable': index['writable'],
                'default': index['default']
            }

            response = requests.post(
                f'{gl_url}/api/system/indices/index_sets',
                headers=headers,
                auth=auth,
                json=gl_index_data
            )
            if response.status_code != 400:
                logging.info(f'Index {title} was created')
            else:
                logging.info(f'Index {title} already exist')

if args.graylog_config:
    logging.info(f'Render config from {args.graylog_config[0]}')
    try:
        with open(args.graylog_config[0]) as f:
            data = yaml.load(f, Loader=SafeLoader)

            headers = {
                'X-Requested-By': 'cli',
                'Content-Type': 'application/json'
            }

            gl_url = data['graylog']['url']
            gl_user = data['graylog']['user']
            gl_pass = data['graylog']['password']
            auth=(gl_user, gl_pass)
            
            if args.create_update_inputs or args.all:
                logging.info(f'Proccess for creating inputs was started')
                gl_ex_inputs = getInput()
                createInput(gl_ex_inputs)
                checkInput(gl_ex_inputs)
            
            if args.create_update_streams or args.all:
                logging.info(f'Proccess for creating streams was started')
                gl_ex_streams = getStreams()
                createStreams(gl_ex_streams)
            
            if args.create_update_users or args.all:
                logging.info(f'Proccess for creating users was started')
                userCreate()
            
            if args.create_update_indexes or args.all:
                logging.info(f'Proccess for creating indexes was started')
                gl_ex_indexes = getIndexes()
                indexCreate(gl_ex_indexes)
    except TypeError:
        logging.info(f'Config {args.graylog_config[0]} is not valid')