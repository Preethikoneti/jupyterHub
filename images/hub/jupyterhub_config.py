import yaml
import os
import sys

def get_config(key, default=None):
    """
    Find a config item of a given name & return it

    Parses everything as YAML, so lists and dicts are available too
    """
    path = os.path.join('/etc/jupyterhub/config', key)
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
            print(key, data)
            return data
    except FileNotFoundError:
        return default

c.JupyterHub.spawner_class = 'kubespawner.KubeSpawner'

# Connect to a proxy running in a different pod
c.JupyterHub.proxy_api_ip = os.environ['PROXY_API_SERVICE_HOST']
c.JupyterHub.proxy_api_port = int(os.environ['PROXY_API_SERVICE_PORT'])

# Check that the proxy has routes appropriately setup
# This isn't the best named setting :D
c.JupyterHub.last_activity_interval = 5

c.JupyterHub.ip = os.environ['PROXY_PUBLIC_SERVICE_HOST']
c.JupyterHub.port = int(os.environ['PROXY_PUBLIC_SERVICE_PORT'])

# the hub should listen on all interfaces, so the proxy can access it
c.JupyterHub.hub_ip = '0.0.0.0'

c.KubeSpawner.namespace = os.environ.get('POD_NAMESPACE', 'default')

# Sometimes disks take a while to attach, so let's keep a not-too-short timeout
c.KubeSpawner.start_timeout = 5 * 60

# Use env var for this, since we want hub to restart when this changes
c.KubeSpawner.singleuser_image_spec = os.environ['SINGLEUSER_IMAGE']

c.KubeSpawner.singleuser_extra_labels = get_config('singleuser.extra-labels', {})

# FIXME: Make this better? 
#c.KubeSpawner.singleuser_uid = 1000
#c.KubeSpawner.singleuser_fs_gid = 1000

c.KubeSpawner.singleuser_uid = 0
c.KubeSpawner.singleuser_fs_gid = 0

# Configure dynamically provisioning pvc
storage_type = get_config('singleuser.storage.type')
if storage_type == 'dynamic':
    c.KubeSpawner.pvc_name_template = 'claim-{username}'
    c.KubeSpawner.user_storage_class = get_config('singleuser.storage.class')
    c.KubeSpawner.user_storage_access_modes = ['ReadWriteOnce']
    c.KubeSpawner.user_storage_capacity = get_config('singleuser.storage.capacity')

    # Add volumes to singleuser pods
    c.KubeSpawner.volumes = [
        {
            'name': 'volume-{username}',
            'persistentVolumeClaim': {
                'claimName': 'claim-{username}'
            }
        }
    ]
    c.KubeSpawner.volume_mounts = [
        {
            'mountPath': get_config('singleuser.storage.home_mount_path'),
            'name': 'volume-{username}'
        }
    ]
elif storage_type == 'hostPath':
    c.KubeSpawner.volumes = [
        {
            'name': 'home',
            'hostPath': {
                'path': get_config('singleuser.storage.home_host_path_template')
            }
        }
    ]
    c.KubeSpawner.volume_mounts = [
        {
            'mountPath': get_config('singleuser.storage.home_mount_path'),
            'name': 'home'
        }
    ]

# Shared data mounts - used to mount shared data (across all
# students) from pre-prepared PVCs to students. PVCs are mounted under
# /data/shared/{name}.
# The env variable SHARED_DATA_MOUNTS is a string of the following form,
# generated by key/values in the helm chart:
# {mount_name_1}={pvc_name_1};{mount_name_2}={pvc_name_2};
#
# The variable uses this custom format rather than JSON because
# rendering JSON is a PITA from go templates.
shared_data_mounts_str = os.environ.get('SHARED_DATA_MOUNTS', None)
if shared_data_mounts_str:
    shared_data_mounts = dict([
        m.split('=') for m in shared_data_mounts_str.split(';')
        if m])
    for shareName, diskName in shared_data_mounts.items():
        c.KubeSpawner.volumes += [{
            'name': 'shared-data-{name}'.format(name=shareName),
            'persistentVolumeClaim': {
             'claimName': 'jupyterhub-raw-data',
             'readOnly' : True
            }

        }]
        c.KubeSpawner.volume_mounts += [{
            'mountPath': '/data/shared/{name}'.format(name=shareName),
            'name': 'shared-data-{name}'.format(name=shareName),
            'readOnly': True
        }]


c.KubeSpawner.volumes += [{
           'name': 'jupyterhub-shared-data',
           'persistentVolumeClaim': { 
	     'claimName': 'jupyterhub-shared-data',
             'readOnly' : False
	    }
            
        }]
c.KubeSpawner.volume_mounts += [{
            'mountPath': '/data/shared/nfs',
            'name': 'jupyterhub-shared-data',
            'readOnly': False
        }]

# Gives spawned containers access to the API of the hub
c.KubeSpawner.hub_connect_ip = os.environ['HUB_SERVICE_HOST']
c.KubeSpawner.hub_connect_port = int(os.environ['HUB_SERVICE_PORT'])

c.KubeSpawner.mem_limit = get_config('singleuser.memory.limit')
c.KubeSpawner.mem_guarantee = get_config('singleuser.memory.guarantee')
c.KubeSpawner.cpu_limit = get_config('singleuser.cpu.limit')
c.KubeSpawner.cpu_guarantee = get_config('singleuser.cpu.guarantee')



c.JupyterHub.extra_log_file = '/var/log/jupyterhublog'
c.JupyterHub.log_level = 'DEBUG'
# Allow switching authenticators easily
auth_type = get_config('auth.type')

if auth_type == 'google':
    c.JupyterHub.authenticator_class = 'oauthenticator.GoogleOAuthenticator'
    c.GoogleOAuthenticator.client_id = get_config('auth.google.client-id')
    c.GoogleOAuthenticator.client_secret = get_config('auth.google.client-secret')
    c.GoogleOAuthenticator.oauth_callback_url = get_config('auth.google.callback-url')
    c.GoogleOAuthenticator.hosted_domain = get_config('auth.google.hosted-domain')
    c.GoogleOAuthenticator.login_service = get_config('auth.google.login-service')
    email_domain = get_config('auth.google.hosted-domain')
elif auth_type == 'hmac':
    c.JupyterHub.authenticator_class = 'hmacauthenticator.HMACAuthenticator'
    c.HMACAuthenticator.secret_key = bytes.fromhex(get_config('auth.hmac.secret-key'))
    email_domain = 'local'
elif auth_type == 'dummy':
    c.JupyterHub.authenticator_class = 'dummyauthenticator.DummyAuthenticator'
    email_domain = 'local'
elif auth_type == 'tmp':
    c.JupyterHub.authenticator_class = 'tmpauthenticator.TmpAuthenticator'
    email_domain = 'local'
elif auth_type == 'github':
    c.JupyterHub.authenticator_class = 'oauthenticator.GitHubOAuthenticator'
    c.GitHubOAuthenticator.client_secret = get_config('auth.github.client-secret')
    c.GitHubOAuthenticator.client_id = get_config('auth.github.client-id')
    email_domain = 'local'
elif auth_type == 'sap':
    c.JupyterHub.authenticator_class = 'oauthenticator.generic.GenericOAuthenticator'
    c.GenericOAuthenticator.client_secret = get_config('auth.sap.client-secret')
    c.GenericOAuthenticator.client_id = get_config('auth.sap.client-id')
    email_domain = 'local'



def generate_user_email(spawner):
    """
    Used as the EMAIL environment variable
    """
    return '{username}@{domain}'.format(
        username=spawner.user.name, domain=email_domain
    )

def generate_user_name(spawner):
    """
    Used as GIT_AUTHOR_NAME and GIT_COMMITTER_NAME environment variables
    """
    return spawner.user.name

c.KubeSpawner.environment = {
    'EMAIL': generate_user_email,
    # git requires these committer attributes
    'GIT_AUTHOR_NAME': generate_user_name,
    'GIT_COMMITTER_NAME': generate_user_name
}

# Setup STATSD
if 'STATSD_SERVICE_HOST' in os.environ:
    c.JupyterHub.statsd_host = os.environ['STATSD_SERVICE_HOST']
    c.JupyterHub.statsd_port = int(os.environ['STATSD_SERVICE_PORT'])

# Enable admins to access user servers
c.JupyterHub.admin_access = get_config('admin.access')

#c.Authenticator.admin_users = get_config('admin.users', [])
c.Authenticator.admin_users = ['i033085', 'i820620']

cull_token = get_config('cull.token', None)
if cull_token:
    c.JupyterHub.api_tokens = {
        cull_token: 'cull'
    }
    if 'cull' not in c.Authenticator.admin_users:
        c.Authenticator.admin_users.append('cull')

c.JupyterHub.base_url = get_config('hub.base_url')

c.JupyterHub.db_url = get_config('hub.db_url')

cmd = get_config('singleuser.cmd', None)
if cmd:
    c.Spawner.cmd = cmd
