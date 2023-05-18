import multiprocessing

bind = "<IP>:<PORT>"
workers = 4
worker_class = "gevent"
worker_connections = 1000
timeout = 3600
certfile = "<localPath>(certificate.pem"
keyfile = "<localPath>/private_key.pem"
