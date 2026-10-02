import os

bind='0.0.0.0:'+os.environ.get('PORT','8080')
# O banco e os lotes são compartilhados dentro de um único processo.
workers=1
worker_class='gthread'
threads=4
timeout=180
graceful_timeout=30
accesslog='-'
errorlog='-'
capture_output=True

def worker_exit(server,worker):
    aplicacao=getattr(worker,'wsgi',None)
    core=getattr(aplicacao,'extensions',{}).get('banco')
    if core:
        core.job['parar']=True
        core.ia.encerrar()
