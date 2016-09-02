from celery.utils import Queue, Exchange
from config.config import Configurator
from datetime import timedelta
from .app import CONFIG_PATH

CONFIG = Configurator(CONFIG_PATH)

BROKER_URL = CONFIG["CELERY_BROKER_URL"]
CELERY_BROKER_URL = CONFIG["CELERY_BROKER_URL"]
CELERY_RESULT_BACKEND = CONFIG["CELERY_RESULT_BACKEND"]

CELERY_ACKS_LATE = True

# CELERY_ACCEPT_CONTENT=['json']
# CELERY_TASK_SERIALIZER='json'
# CELERY_RESULT_SERIALIZER='json'

CELERY_QUEUES = (
    Queue('default', Exchange('default'), routing_key='default'),
    Queue('update_inventory_task', Exchange('update_inventory_task'), routing_key='update_inventory_task'),
    Queue('deposit_task', Exchange('deposit_task'), routing_key='deposit_task'),
    Queue('withdrawal_task', Exchange('withdrawal_task'), routing_key='withdrawal_task'),
    Queue('check_tradeoffer_task', Exchange('check_tradeoffer_task'), routing_key='check_tradeoffer_task'),
    # Queue('report_task', Exchange('report_task'), routing_key='report_task'),
)

CELERYBEAT_SCHEDULE = {
    'update-bot-inventories': {
        'task': 'update_inventories_task',
        'schedule': timedelta(minutes=1),
        'options': {'queue': 'update_inventories_task'},
        'args': ()
    }
}

CELERY_TIMEZONE = 'UTC'