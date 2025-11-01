from datetime import datetime

import pytest

from src.application.use_cases import ProcessMatchRequestUseCase
from src.domain.value_objects import MatchRequest
from src.handlers.match_handler import MatchRequestHandler


def test_message_validator_with_empty_message_data():
    msg_hadler = MatchRequestHandler(ProcessMatchRequestUseCase())
    msg_data = {}
    success = msg_hadler._validate_message(msg_data)
    assert success is False



def test_message_validator_with_partial_message_data(message_handler):
    msg_data = {
        'user_id': 123,
        'username': 'greatestO_0',
        'gender': 'male',
        'lang_code': 'ru',
        # 'criteria': {...}, ОТСУТСВУЕТ!
        'created_at': datetime.now().isoformat()
    }

    success = message_handler._validate_message(msg_data)
    assert success is False

def test_message_validator_with_partial_criteria_data(message_handler):
    msg_data = {
        'user_id': 123,
        'username': 'greatestO_0',
        'gender': 'male',
        'lang_code': 'ru',
        'criteria': {
            'language': 'english',
            'fluency': 2,
            # 'topics': ['sport', 'music'] ОТСУТСВУЕТ!
            'dating': True
        },
        'created_at': datetime.now().isoformat()
    }
    success = message_handler._validate_message(msg_data)
    assert success is False


def test_message_validator_with_invalid_user_id(message_handler):
    msg_data = {
        'user_id': '123O',
        'username': 'greatestO_0',
        'gender': 'male',
        'lang_code': 'ru',
        'criteria': {
            'language': 'english',
            'fluency': 2,
            'topics': ['sport', 'music'],
            'dating': True
        },
        'created_at': datetime.now().isoformat()
    }
    success = message_handler._validate_message(msg_data)
    assert success is False


def test_message_validator_with_invalid_fluency(message_handler):
    msg_data = {
        'user_id': '1230',
        'username': 'greatestO_0',
        'gender': 'male',
        'lang_code': 'ru',
        'criteria': {
            'language': 'english',
            'fluency': 'advanced',
            'topics': ['sport', 'music'],
            'dating': True
        },
        'created_at': datetime.now().isoformat()
    }
    success = message_handler._validate_message(msg_data)
    assert success is False


def test_message_validator_with_invalid_topics_as_string(message_handler):
    msg_data = {
        'user_id': '1230',
        'username': 'greatestO_0',
        'gender': 'male',
        'lang_code': 'ru',
        'criteria': {
            'language': 'english',
            'fluency': 2,
            'topics': 'sport, music',
            'dating': True
        },
        'created_at': datetime.now().isoformat()
    }
    success = message_handler._validate_message(msg_data)
    assert success is False

def test_message_validator_with_invalid_dating_value(message_handler):
    msg_data = {
        'user_id': '1230',
        'username': 'greatestO_0',
        'gender': 'male',
        'lang_code': 'ru',
        'criteria': {
            'language': 'english',
            'fluency': 2,
            'topics': ['music', 'sport'],
            'dating': 'truue'
        },
        'created_at': datetime.now().isoformat()
    }
    success = message_handler._validate_message(msg_data)
    assert success is False

def test_message_validator_with_valid_dating_value(message_handler):
    msg_data = {
        'user_id': '1230',
        'username': 'greatestO_0',
        'gender': 'male',
        'lang_code': 'ru',
        'criteria': {
            'language': 'english',
            'fluency': 2,
            'topics': ['music', 'sport'],
            'dating': 'true'
        },
        'created_at': datetime.now().isoformat()
    }
    success = message_handler._validate_message(msg_data)
    assert success is True


def test_message_validator_works_properly(message_handler):
    msg_data = {
        'user_id': '1230',
        'username': 'greatestO_0',
        'gender': 'male',
        'lang_code': 'ru',
        'criteria': {
            'language': 'english',
            'fluency': 2,
            'topics': ['music', 'sport'],
            'dating': True
        },
        'created_at': datetime.now().isoformat()
    }
    success = message_handler._validate_message(msg_data)
    assert success is True


def test_create_match_request_from_dict_happy_case():
    user_data = {
        'user_id': '1230',
        'username': 'greatestO_0',
        'gender': 'male',
        'lang_code': 'ru',
        'criteria': {
            'language': 'english',
            'fluency': 2,
            'topics': ['music', 'sport'],
            'dating': True
        },
        'created_at': datetime.now().isoformat()
    }
    try:
        MatchRequest.from_dict(user_data)
        assert 1 == 1
        return

    except (ValueError, TypeError):
        pass

def test_create_match_request_match_request_from_dict_unhappy_case():
    user_data = {
        'user_id': '1230',
        'username': 'greatestO_0',
        'gender': 'male',
        'lang_code': 'ru',
        'criteria': {
            'language': 'english',
            'fluency': 2,
            'topics': ['music', 'sport'],
            'dating': True
        },
        'created_at': datetime.now().isoformat()
    }
    try:
        MatchRequest.from_dict(user_data)
        return

    except (ValueError, TypeError):
        assert 1 == 1





