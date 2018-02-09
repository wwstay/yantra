from __future__ import print_function


class Alexa():
    def __init__(self):
        self.APPLICATION_ID = "amzn1.ask.skill.792f0d00-5e7b-4414-b880-59f90d1153bc"

    # --------------- Helpers ----------------------

    def check_application(self, session):
        """ To check requests are from our skill or not """
        if (session['application']['applicationId'] != self.APPLICATION_ID):
            raise ValueError("Invalid Application ID")

    # --------------- Helpers that build all of the responses ----------------------

    def build_speechlet_response(self, title, output, reprompt_text, should_end_session):
        return {
            'shouldEndSession': should_end_session,
            'outputSpeech': {
                'type': 'PlainText',
                'text': output
            },
            'reprompt': {
                'outputSpeech': {
                    'type': 'PlainText',
                    'text': reprompt_text
                }
            },
            'card': {
                'type': 'Simple',
                'title': "WWStay - " + title,
                'content': output
            }
        }

    def build_delegate_response(self, session_attributes):
        return {
            'version': '1.0',
            'sessionAttributes': session_attributes,
            'response': {
                'directives': [{
                    "type": "Dialog.Delegate"
                }]
            }
        }

    def build_response(self, session_attributes, speechlet_response):
        return {
            'version': '1.0',
            'sessionAttributes': session_attributes,
            'response': speechlet_response
        } 

    # --------------- Functions that control the skill's behavior ------------------

    def get_welcome_response(self):

        session_attributes = {}
        card_title = "Welcome"
        speech_output = "Welcome to the WWStay. " \
                        "WWStay helps you to find accommodation globally. " \
                        "Please tell me where would you like to stay by saying, " \
                        "I need a stay in new york."
        # If the user either does not reply to the welcome message or says something
        # that is not understood, they will be prompted again with this text.
        reprompt_text = "Please tell me where would you like to stay by saying, " \
                        "I need a stay in new york."
        should_end_session = False
        return self.build_response(session_attributes, self.build_speechlet_response(
            card_title, speech_output, reprompt_text, should_end_session))

    def handle_session_end_request(self):
        card_title = "Session Ended"
        speech_output = "Thank you for trying WWStay. " \
                        "Have a nice day! "
        # Setting this to true ends the session and exits the skill.
        should_end_session = True
        return self.build_response({}, self.build_speechlet_response(
            card_title, speech_output, None, should_end_session))

    def _get_slot_value(self, intent, slot_name):
        if slot_name in intent['slots']:
            if 'value' in intent['slots'][slot_name]:
                return intent['slots'][slot_name]['value']
        return None

    def handle_hotel_book_request(self, intent, session):
        """ Sets data in the session and prepares the speech to reply to the user. """

        card_title = intent['name']
        session_attributes = {}
        should_end_session = False

        location = self._get_slot_value(intent, 'location')
        fromDate = self._get_slot_value(intent, 'fromDate')
        toDate = self._get_slot_value(intent, 'toDate')
        duration = self._get_slot_value(intent, 'duration')

        session_attributes = {
            "location": location,
            "fromDate": fromDate,
            "toDate": toDate,
            "duration": duration,
        }

        if location and fromDate and (duration or toDate):
            speech_output = "We have received your request to stay at " + location + \
                            " from " + fromDate + ((" for " + duration + " nights") if duration else (" to " + toDate)) + ". We will get back with quotations. Bye."
            should_end_session = True
            return self.build_response(session_attributes, self.build_speechlet_response(
                card_title, speech_output, None, should_end_session))
        else:
            return self.build_delegate_response(session_attributes)

    # --------------- Events ------------------

    def on_session_started(self, session_started_request, session):
        """ Called when the session starts """

        print("on_session_started requestId=" + session_started_request['requestId'] +
              ", sessionId=" + session['sessionId'])

    def on_launch(self, launch_request, session):
        """ Called when the user launches the skill without specifying what they want """

        # Dispatch to your skill's launch
        return self.get_welcome_response()

    def on_intent(self, intent_request, session):
        """ Called when the user specifies an intent for this skill """

        intent = intent_request['intent']
        intent_name = intent_request['intent']['name']

        # Dispatch to your skill's intent handlers
        if intent_name == "HotelBook":
            return self.handle_hotel_book_request(intent, session)
        elif intent_name == "AMAZON.HelpIntent":
            return self.get_welcome_response()
        elif intent_name == "AMAZON.CancelIntent" or intent_name == "AMAZON.StopIntent":
            return self.handle_session_end_request()
        else:
            raise ValueError("Invalid intent")

    def on_session_ended(self, session_ended_request, session):
        """ Called when the user ends the session.

        Is not called when the skill returns should_end_session=true
        """
        print("on_session_ended requestId=" + session_ended_request['requestId'] +
              ", sessionId=" + session['sessionId'])
        # add cleanup logic here

    # --------------- Main handler ------------------

    def handler(self, event):
        """ Route the incoming request based on type (LaunchRequest, IntentRequest,
        etc.) The JSON body of the request is provided in the event parameter.
        """
        event_session = event['session']
        event_request = event['request']
        event_type = event['request']['type']

        self.check_application(event_session)

        if event_type == "LaunchRequest":
            return self.on_launch(event_request, event_session)
        elif event_type == "IntentRequest":
            return self.on_intent(event_request, event_session)
        elif event_type == "SessionEndedRequest":
            return self.on_session_ended(event_request, event_session)
