import string
import random
import requests
import time


def generate_code(size=4, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


def report(service_url, report_url, status, error, token, data=None):
    if not data:
        data = {}

    data["status"] = status
    data["error"] = error
    data["token"] = token

    service_tries = 5
    report_tries = 5
    response_service = requests.post(service_url, data=data)
    response_report = requests.post(report_url, data=data)

    while response_service.status_code > 200 and service_tries > 0:
        response_service = requests.post(service_url, data=data)
        service_tries -= 1
        time.sleep(1)

    while response_report.status_code > 200 and report_tries > 0:
        response_report = requests.post(report_url, data=data)
        report_tries -= 1
        time.sleep(1)

    return response_service.status_code <= 200 and response_report.status_code <= 200


def report_inventory(service_url, bot_username, token, data=None):
    if not data:
        data = {}

    data["bot"] = bot_username
    data["token"] = token

    requests.post(service_url, data=data)