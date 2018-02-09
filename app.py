import json
import logging
import traceback
import requests
import datetime
import apiai
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify
from intercom.client import Client

from alexa import Alexa

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

app = Flask(__name__)

# intercom config
INTERCOM_ACCESS_TOKEN = 'intercom_access_token'
INTERCOM_BOT_USER_ID = 1268655  # currently set to WWStay Engineering user id
INTERCOM_ASSIGNEE_USER_ID = 1268678  # currently set to Avinash Kondeti user id

# api.ai config
APIAI_TOKEN = 'apiai_token'
APIAI_FALLBACK_INTENTS = ['fallback', 'hotel.book - fallback - yes']

# other config
CREATE_REQUEST_ENDPOINT = "https://test.wwstay.com/app/booking/onlinerequest/add"


def clean_message(message_raw):
    """
    convert intercom html message into text
    """
    soup = BeautifulSoup(message_raw, "html.parser")
    # remove all script and style elements
    for script in soup(["script", "style"]):
        script.extract()

    # get text
    text = soup.get_text()
    return text


def send_apiai_message(message, session_id):
    """
    send message to api.ai and get response
    """
    ai = apiai.ApiAI(APIAI_TOKEN)
    ai_request = ai.text_request()
    ai_request.session_id = session_id
    ai_request.query = message
    ai_response_raw = ai_request.getresponse().read()
    logging.info(ai_response_raw)
    ai_response = json.loads(ai_response_raw)
    return ai_response


def get_apiai_reply_message(ai_response):
    """
    parse api.ai response and get reply message
    """
    reply_message = str(ai_response['result']['fulfillment']['speech'])
    return reply_message


def parse_intercom_message(data):
    """
    parse intercom response and get user message
    """
    if data.get('topic', '') == 'conversation.user.created':
        message_raw = data['data']['item']['conversation_message']['body']
    else:
        message_raw = data['data']['item']['conversation_parts']['conversation_parts'][0]['body']
    message = clean_message(message_raw)
    logger.info(message)
    return message


def parse_intercom_conversation_id(data):
    """
    parse intercom response and get conversation id
    """
    return data['data']['item']['id']


def has_intercom_conversation_assignee(data):
    """
    check whether conversation has assignee and not assigned to bot
    """
    assignee_id = data['data']['item']['assignee']['id']
    return True if assignee_id and (assignee_id != str(INTERCOM_BOT_USER_ID)) else False


def get_intercom_client():
    return Client(personal_access_token=INTERCOM_ACCESS_TOKEN)


def send_intercom_message(message, conversation_id):
    """
    send message to intercom
    """
    intercom = get_intercom_client()
    intercom.conversations.reply(id=conversation_id, admin_id=INTERCOM_BOT_USER_ID,
                                 message_type='comment', body=message)


def assign_intercom_conversation(conversation_id):
    """
    assign conversation to team
    """
    intercom = get_intercom_client()
    intercom.conversations.assign(id=conversation_id,
                                  admin_id=INTERCOM_BOT_USER_ID,
                                  assignee_id=INTERCOM_ASSIGNEE_USER_ID)


def should_fallback(ai_response):
    """
    check whether conversation should fallback to team
    """
    try:
        intent_name = ai_response['result']['metadata']['intentName']
        if intent_name in APIAI_FALLBACK_INTENTS:
            return True
        if ai_response['result']['score'] < 0.4:
            return True
    except:
        return False


def initial_delivery(data):
    """
    check whether intercom request is not duplicate.
    This is to not process same message again.
    """
    return (data['delivery_attempts'] == 1)


def conversation_complete(ai_response):
    """
    check whether conversation with api.ai is complete.
    """
    return (not ai_response['result']['actionIncomplete'])


def is_hotel_booking_action(ai_response):
    """
    check whether action is hotel booking.
    """
    return (ai_response['result']['action'] == 'hotel.book')


def create_request(ai_response):
    """
    create pa request using api.ai data.
    """
    parameters = ai_response['result']['parameters']
    checkout_date = parameters['deadline'].get('checkout_date')
    if not checkout_date:
        d1 = datetime.datetime.strptime(parameters['checkin-date'], "%y-%m-%d")
        d2 = d1 + datetime.timedelta(days=parameters['deadline'].get('nights'))
        checkout_date = datetime.datetime.strftime(d2, "%Y-%m-%d")

    payload = "guest_email="+parameters['email']+"&work_address="+parameters['location']['city']+"&check_in="+parameters['checkin-date']+"&check_out="+checkout_date+"&budget_range="+str(parameters['budget']['amount']) + " " + parameters['budget']['currency']

    headers = {
        'content-type': "application/x-www-form-urlencoded",
        'cache-control': "no-cache"
    }

    response = requests.request("POST", CREATE_REQUEST_ENDPOINT, data=payload, headers=headers)
    print response.text
    return response


@app.route("/", methods=['POST'])
def intercom_reply_webhook(event=None, context=None):
    """
    endpoint for intercom webhook which will be called whenever user sends a new message
    """
    try:
        logger.info('function invoked intercom_reply_webhook()')
        data = request.get_json()
        logger.info(data)

        if not initial_delivery(data):
            logger.info("Ignoring duplicate intercom ping")
            return "OK", 200

        if has_intercom_conversation_assignee(data):
            logger.info("Conversation has assignee")
            return "OK", 200

        message = parse_intercom_message(data)
        conversation_id = parse_intercom_conversation_id(data)
        ai_response = send_apiai_message(message, conversation_id)
        reply_message = get_apiai_reply_message(ai_response)

        if should_fallback(ai_response):
            send_intercom_message("Your request has been assigned to our agent. We will get back to you soon.", conversation_id)
            assign_intercom_conversation(conversation_id)
            logger.info("Assigned conversation to team")
            return "OK", 200

        if conversation_complete(ai_response):
            logger.info("Conversation complete.")
            send_intercom_message(reply_message, conversation_id)
            assign_intercom_conversation(conversation_id)
            logger.info("Sent reply message: " + reply_message)
            return "OK", 200

        send_intercom_message(reply_message, conversation_id)
        logger.info("Sent reply message: " + reply_message)
        return "OK", 200

    except Exception, e:
        traceback.print_exc()
        return "OK", 200


@app.route("/alexa/", methods=['POST'])
def alexa_reply_webhook(event=None, context=None):
    logger.info('function invoked alexa_reply_webhook()')
    data = request.get_json()
    logger.info(json.dumps(data))
    alx = Alexa()
    return_data = alx.handler(data)
    logger.info(return_data)
    return jsonify(return_data), 200
