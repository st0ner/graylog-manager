import requests, json, socket, yaml, time, argparse, logging, sys, os
from datetime import datetime
from yaml.loader import SafeLoader
from jinja2 import Environment, FileSystemLoader
from fabric import Connection
from kubernetes import client, config
from dotenv import load_dotenv
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

parser = argparse.ArgumentParser(description='Process graylog manage')
parser.add_argument('--config', dest='graylog_config', help='path to graylog yaml config', nargs=1, metavar=("FILE"))
parser.add_argument('--all', dest='all', help='trigger all arguments', action="store_true")
parser.add_argument('--create_update_inputs', dest='create_update_inputs', help='for work with inputs', action="store_true")
parser.add_argument('--create_update_users', dest='create_update_users', help='for work with users', action="store_true")
parser.add_argument('--create_update_streams', dest='create_update_streams', help='for work with streams', action="store_true")
parser.add_argument('--create_update_indexes', dest='create_update_indexes', help='for work with es indexes', action="store_true")
parser.add_argument('--create_update_balancer', dest='create_update_balancer', help='for using external balancer', action="store_true")
parser.add_argument('--create_update_services', dest='create_update_services', help='for using k8s', action="store_true")
args = parser.parse_args()

load_dotenv()
graylog_url = os.getenv('graylog_url')
graylog_user = os.getenv('graylog_user')
graylog_password = os.getenv('graylog_password')
ssh_user = os.getenv('ssh_user')

def getInput():
    response = requests.get(
        f'{graylog_url}/api/system/inputs',
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
                f'{graylog_url}/api/system/inputs',
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
                f'{graylog_url}/api/system/inputstates/{input_id}',
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
        f'{graylog_url}/api/system/inputstates/{input_id}',
        headers=headers,
        auth=auth,
    )

def setStaticFields(input_id, static_field_key, static_field_value):
    data = {
        'key': static_field_key,
        'value': static_field_value
    }
    response = requests.post(
        f'{graylog_url}/api/system/inputs/{input_id}/staticfields',
        headers=headers,
        auth=auth,
        json=data
    )
    logging.info(f'Add static field for {input_id}')

def userCreate():
    if data['users']:
        for user in data['users']:
            username = user['username']
            graylog_user_data = {
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
                f'{graylog_url}/api/users',
                headers=headers,
                auth=auth,
                json=graylog_user_data
            )
            if response.status_code != 400:
                logging.info(f'User {username} was created')
            else:
                logging.info(f'User {username} already exist')

def getStreams():
    response = requests.get(
        f'{graylog_url}/api/streams',
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
                f'{graylog_url}/api/streams',
                headers=headers,
                auth=auth,
                json=gl_stream_data
            )

            response = response.json()
            stream_id = response['stream_id']
            logging.info(f'Stream was created: {stream_id}')

            response = requests.post(
                f'{graylog_url}/api/streams/{stream_id}/resume',
                headers=headers,
                auth=auth,
            )
            logging.info(f'Stream {stream_id} enabled')

def getIndexes():
    response = requests.get(
        f'{graylog_url}/api/system/indices/index_sets?skip=0&limit=0&stats=false',
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
                f'{graylog_url}/api/system/indices/index_sets',
                headers=headers,
                auth=auth,
                json=gl_index_data
            )
            if response.status_code != 400:
                logging.info(f'Index {title} was created')
            else:
                logging.info(f'Index {title} already exist')

def renderBalancer():
    balancer_host = data['global']['balancer_host']
    balancer_port = data['global']['balancer_port']
    for nodeport in data['inputs']:
        project_name = nodeport['title']
        nginx_port = nodeport['configuration']['nodeport']
        server_balancer = '\n\t'.join([str(f'server {worker}:{nginx_port};') for worker in data['global']['workers']])

        file_loader = FileSystemLoader('templates')
        env = Environment(loader=file_loader)

        balancer = env.get_template('balancer_udp.conf')
        balancer = balancer.render(
            project_name=project_name,
            project_port=nginx_port,
            server_balancer=server_balancer
        )

        c = Connection(host=balancer_host, user=ssh_user, port=balancer_port)
        c.sudo(f'echo "{balancer}" | sudo tee /etc/nginx/graylog/{project_name}.conf')
        try:
            c.sudo('nginx -t')
            c.sudo('nginx -s reload')
            logging.info('create config for nginx')
        except:
            logging.warning('nginx has syntax problem')

def renderService():
    gl_namespace = data['global']['namespace']
    kube_config = data['global']['k8s_config_path']
    config.load_kube_config(kube_config)

    for nodeport in data['inputs']:
        project_name = nodeport['title']
        nginx_port = nodeport['configuration']['nodeport']
        port = nodeport['configuration']['port']

        api_instance = client.CoreV1Api()
        k8s_services = api_instance.list_namespaced_service(watch=False, namespace=gl_namespace)

        for service_name in k8s_services.items:
            if service_name.metadata.name == project_name:
                create_serive = False
                logging.info(f'Service {project_name} is existed, skip')
            else:
                create_serive = True
                logging.info(f'Service {project_name} is not existed')

        if create_serive:
            service = client.V1Service()
            service.api_version = 'v1'
            service.kind = 'Service'
            service.metadata = client.V1ObjectMeta(name=project_name)

            spec = client.V1ServiceSpec()
            spec.type = 'NodePort'
            spec.selector = {'app.kubernetes.io/instance': 'graylog', 'app.kubernetes.io/name': 'graylog'}
            spec.ports = [client.V1ServicePort(protocol='UDP', port=port, target_port=port, node_port=nginx_port)]
            service.spec = spec

            api_instance.create_namespaced_service(namespace=gl_namespace, body=service)
            logging.info(f'Service {project_name} is created')

def renderNetworkPolicy():
    status = data['global']['network_policy']
    if status:
        logging.info('Creating network policy was enabled')
        logging.info('Proccessing...')

        gl_namespace = data['global']['namespace']
        balancer_ip = fromHostGetIp(data['global']['balancer_host'])
        kube_config = data['global']['k8s_config_path']

        list_ports = []
        for nodePort in data['inputs']:
            list_ports.append(nodePort['configuration']['nodeport'])

        list_ports = '\n        '.join([str(f'- port: {nodePort}') for nodePort in list_ports])

        file_loader = FileSystemLoader('templates')
        env = Environment(loader=file_loader)

        network_policy = env.get_template('network_policy.yaml')
        network_policy = network_policy.render(
            policy_name=gl_namespace,
            gl_namespace=gl_namespace,
            balancer_ip=f'{balancer_ip}/32',
            list_ports=list_ports
        )

        if not os.path.exists('tmp/'):
            os.mkdir('tmp/')
            logging.info('Created tmp dir')

        f = open('tmp/network_policy.yaml', 'w')
        f.write(network_policy)
        f.close()
        logging.info('Rendered network policy')

        os.system(f'kubectl --kubeconfig={kube_config} apply -f tmp/network_policy.yaml')
        logging.info('Network policy was configured')
    else:
        logging.info('Creating network policy was disabled')

def fromHostGetIp(hostname):
    return socket.gethostbyname(hostname)

if args.graylog_config:
    logging.info(f'Render config from {args.graylog_config[0]}')

    with open(args.graylog_config[0]) as f:
        data = yaml.load(f, Loader=SafeLoader)

        headers = {
            'X-Requested-By': 'cli',
            'Content-Type': 'application/json'
        }

        auth=(graylog_user, graylog_password)

        if args.create_update_indexes or args.all:
            logging.info(f'Proccess for creating indexes was started')
            gl_ex_indexes = getIndexes()
            indexCreate(gl_ex_indexes)

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

        if args.create_update_balancer or args.all:
            logging.info(f'Proccess for creating config on balancer')
            renderBalancer()

        if args.create_update_services or args.all:
            logging.info(f'Proccess for creating service on k8s')
            renderService()
            renderNetworkPolicy()