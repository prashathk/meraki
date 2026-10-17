import os,json
def dispatch(source_id):
    if not os.getenv('TASKS_QUEUE'):return
    from google.cloud import tasks_v2
    client=tasks_v2.CloudTasksClient();url=os.environ['WORKER_URL'].rstrip('/')+'/internal/extract'
    client.create_task(parent=os.environ['TASKS_QUEUE'],task={'http_request':{'http_method':tasks_v2.HttpMethod.POST,'url':url,'headers':{'Content-Type':'application/json'},'body':json.dumps({'source_id':source_id}).encode(),'oidc_token':{'service_account_email':os.environ['TASKS_SERVICE_ACCOUNT'],'audience':os.environ['WORKER_URL'].rstrip('/')}}})
