import json
import logging
import traceback
import requests
import datetime
import dialogflow
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify
from intercom.client import Client

from alexa import Alexa

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

app = Flask(__name__)

# intercom config
# Dev
INTERCOM_ACCESS_TOKEN = 'dG9rOjUwNTEzMjVhXzA2NmNfNDlhM19hZmE3X2ZmYzEwY2MwYWViMToxOjA='
INTERCOM_BOT_USER_ID = 1268655  # currently set to WWStay Engineering user id
INTERCOM_ASSIGNEE_USER_ID = 1268678  # currently set to Avinash Kondeti user id
# Production
# INTERCOM_ACCESS_TOKEN = 'dG9rOjk2N2JmZjA5X2NkYmFfNGE5Ml9iNDE1XzllNjMyZTFlYzg2MjoxOjA='
# INTERCOM_BOT_USER_ID = 1391697  # currently set to Yantra user id
# INTERCOM_ASSIGNEE_USER_ID = 1268679  # currently set to Sheeba's user id

# dialogflow config
# Dev
DIALOGFLOW_PROJECT_NAME = 'hotel-booking-test'

# Production
# DIALOGFLOW_PROJECT_NAME = 'hotel-booking-1-e944b'

DIALOGFLOW_FALLBACK_INTENTS = ['fallback', 'hotel.book - fallback - yes']

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


def send_dialogflow_message(message, session_id):
    """
    send message to dialogflow and get response
    """
    c = dialogflow.SessionsClient()
    s = c.session_path(DIALOGFLOW_PROJECT_NAME, session_id)
    t = dialogflow.types.TextInput(text=message, language_code='en-US')
    q = dialogflow.types.QueryInput(text=t)
    r = c.detect_intent(session=s, query_input=q)
    print r
    return r


def get_dialogflow_reply_message(ai_response):
    """
    parse dialogflow response and get reply message
    """
    reply_message = str(ai_response.query_result.fulfillment_text)
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
        intent_name = ai_response.query_result.intent.display_name
        if intent_name in DIALOGFLOW_FALLBACK_INTENTS:
            return True
        if ai_response.query_result.intent_detection_confidence < 0.4:
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
    check whether conversation with dialogflow is complete.
    """
    return ai_response.query_result.all_required_params_present


def is_hotel_booking_action(ai_response):
    """
    check whether action is hotel booking.
    """
    return (ai_response.query_result.action == 'hotel.book')


def is_welcome_action(ai_response):
    """
    check whether action is welcome.
    """
    return (ai_response.query_result.action == 'welcome' or ai_response.query_result.intent.display_name == 'welcome')


def create_request(ai_response):
    """
    create pa request using dialogflow data.
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
        logger.info(json.dumps(data))

        if not initial_delivery(data):
            logger.info("Ignoring duplicate intercom ping")
            return "OK", 200

        if has_intercom_conversation_assignee(data):
            logger.info("Conversation has assignee")
            return "OK", 200

        message = parse_intercom_message(data)
        conversation_id = parse_intercom_conversation_id(data)
        ai_response = send_dialogflow_message(message, conversation_id)
        reply_message = get_dialogflow_reply_message(ai_response)

        if should_fallback(ai_response):
            send_intercom_message("Your request has been assigned to our agent. We will get back to you soon.", conversation_id)
            assign_intercom_conversation(conversation_id)
            logger.info("Assigned conversation to team")
            return "OK", 200

        if conversation_complete(ai_response) and is_hotel_booking_action(ai_response):
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
