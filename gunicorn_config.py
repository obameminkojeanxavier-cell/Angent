import multiprocessing
import os

# Server socket
bind = "127.0.0.1:8000"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 100
timeout = 30
keepalive = 2

# Process naming
proc_name = "datahub"

# Server mechanics
daemon = False
pidfile = "/tmp/datahub.pid"
user = None
group = None
tmp_upload_dir = None

# Logging
accesslog = "/var/log/gunicorn/datahub-access.log"
errorlog = "/var/log/gunicorn/datahub-error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "datahub"

# SSL (if needed)
# keyfile = "/path/to/keyfile"
# certfile = "/path/to/certfile"
